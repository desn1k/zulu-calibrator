"""Everything the steps fit to, from one export: DHW target, valid CTP channel, flow targets of the
heating inputs, heat targets (see app/engine/dhw.py, validity.py, targets.py)."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from app.engine.dhw import DhwTarget, choose_dhw_target
from app.engine.grouping import Shares
from app.engine.meters import Meter
from app.engine.model import CtpFact, Snapshot
from app.engine.schemes import ctp_scheme
from app.engine.targets import (
    HeatingTargets,
    HeatTargets,
    heat_targets,
    heating_targets,
    network_loss,
)
from app.engine.validity import Validity, assess


@dataclass
class StepInputs:
    dhw: DhwTarget | None
    validity: Validity
    targets: HeatingTargets
    heat: HeatTargets
    loss: float | None

    @property
    def unmetered_heat(self) -> float | None:
        k = self.heat.unmetered_factor
        return k.q_fact if k else None


def group_meters_from(settings: Mapping[str, Any] | None) -> dict[str, Meter]:
    """Meters of multi-input buildings entered by hand (until the network export, PR-5):
    {GUID: {"G1": t/h, "Q": Gcal/h, "T1": °C, "T2": °C}}."""
    out = {}
    for guid, v in (settings or {}).items():
        if not isinstance(v, Mapping) or v.get("G1") is None:
            continue
        out[str(guid)] = Meter(
            "OT", T1=v.get("T1"), T2=v.get("T2"), G1=v.get("G1"), G2=v.get("G2"), Q=v.get("Q")
        )
    return out


def step_inputs(
    snap: Snapshot,
    fact: CtpFact,
    circulation: bool | None = None,
    group_meters: Mapping[str, Meter] | None = None,
    shares: Shares | None = None,
    loss: float | None = None,
    base: Snapshot | None = None,
) -> StepInputs:
    """`base` — the first export of the project (Kso before calibration for the channel check)."""
    scheme = ctp_scheme(snap.card.get("N_schem"))
    dhw = choose_dhw_target(fact, snap.consumers, circulation) if fact.dhw else None
    split = 0.0
    if scheme is not None and scheme.dhw == "two_stage_mixed" and scheme.heating == "direct":
        # stage II branch of the inlet (model Gverh of the last run) does not go to the heating
        split = snap.card_num("Gverh") or 0.0
    base_kso = (
        {c.sys: c.num("Kso") for c in base.consumers if c.num("Kso") is not None} if base else None
    )
    validity = assess(snap, fact, inlet_split=split, dhw_heat=dhw.heat if dhw else None,
                      base_kso=base_kso)  # fmt: skip
    targets = heating_targets(snap, validity.g_heating, group_meters, shares)
    if validity.single_building and validity.g_heating:
        # one building: its flow target is the agreed CTP / building flow (validity)
        total = sum(t.g for t in targets.flows.values())
        if total:
            for s, t in list(targets.flows.items()):
                targets.flows[s] = replace(t, g=t.g * validity.g_heating / total)
    loss = network_loss(snap.card) if loss is None else loss
    heat = heat_targets(targets, validity.q_heating, loss)
    return StepInputs(dhw, validity, targets, heat, loss)
