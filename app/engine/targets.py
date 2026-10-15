"""Fitting targets of the heating inputs behind a CTP: flow (step 5) and heat (step 4).

docs/algorithm.md: «Источники данных, GUID и неполные приборы» (GUID groups), «Шаги 4–5»,
examples Чернышевского, Верхняя, Пионерская:

- a metered input: its own meter;
- a multi-input building with one meter (one row of the GUID group, or a group meter entered by
  hand — the meter node before the building): the meter is the whole building, the flow target is
  split inside the group by model flow;
- unmetered inputs: the remainder (CTP heating flow − metered buildings) split by Kso·Qo_r;
- heat: Kso of a metered building = Kso·Q_meter/ΣQ_model of the group; unmetered buildings get
  one factor k = (Q_heating − Σ Q_metered − network loss) / Σ Q_model of the unmetered ones.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from app.engine.grouping import Group, Shares, group_consumers, group_key
from app.engine.meters import Meter, consumer_kind, meter_for
from app.engine.model import Consumer, Snapshot

Source = Literal["meter", "group", "remainder"]


def model_heat(c: Consumer) -> float | None:
    """Heat of the consumer in the model: `Qsum` in a Zulu export (`Q_sum` in the old export)."""
    q = c.num("Qsum")
    return q if q is not None else c.num("Q_sum")


def network_loss(card: Mapping[str, Any]) -> float | None:
    """Heat losses of the network after the CTP from the card: Qut_pod + Qut_obr + Qut_potr."""
    parts = [card.get(k) for k in ("Qut_pod", "Qut_obr", "Qut_potr")]
    nums = [float(v) for v in parts if isinstance(v, int | float) and not isinstance(v, bool)]
    return sum(nums) if nums else None


@dataclass(frozen=True)
class FlowTarget:
    sys: int
    g: float
    source: Source
    members: tuple[int, ...] = ()  # inputs sharing one meter (multi-input building)


@dataclass
class MeteredGroup:
    members: list[Consumer]
    meter: Meter
    by_hand: bool  # group meter entered by hand (meter node before the building)

    @property
    def sys_list(self) -> tuple[int, ...]:
        return tuple(c.sys for c in self.members)


@dataclass
class HeatingTargets:
    flows: dict[int, FlowTarget] = field(default_factory=dict)
    metered: list[MeteredGroup] = field(default_factory=list)
    unmetered: list[Consumer] = field(default_factory=list)
    g_heating: float | None = None  # CTP heating flow the targets close to
    metered_g: float = 0.0
    remainder_g: float | None = None
    remainder_per_gcal: float | None = None  # t/h per Gcal/h of Kso·Qo_r
    metered_per_gcal: dict[tuple[int, ...], float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def heating_inputs(consumers: list[Consumer]) -> list[Consumer]:
    return [c for c in consumers if consumer_kind(c.scheme) == "heating"]


def kso_qo(c: Consumer) -> float:
    kso = c.num("Kso")
    return (1.0 if kso is None else kso) * (c.num("Qo_r") or 0.0)


def group_meter(g: Group, by_hand: Mapping[str, Meter] | None) -> tuple[Meter | None, bool]:
    if by_hand and g.guid and g.guid in by_hand:
        return by_hand[g.guid], True
    return next((m for m in (meter_for(c) for c in g.members) if m is not None), None), False


def split_by_model_flow(members: list[Consumer], total: float) -> dict[int, float]:
    flows = {c.sys: c.num("Gso") or 0.0 for c in members}
    s = sum(flows.values())
    if s <= 0:  # no model flow yet: by load
        flows = {c.sys: kso_qo(c) for c in members}
        s = sum(flows.values())
    n = len(members)
    return {sys: total * (v / s if s else 1.0 / n) for sys, v in flows.items()}


def heating_targets(
    snap: Snapshot,
    g_heating: float | None,
    group_meters: Mapping[str, Meter] | None = None,
    shares: Shares | None = None,
) -> HeatingTargets:
    """Flow target of every heating input. `g_heating` is the CTP heating flow to close to
    (the valid meter channel); `group_meters` are meters of multi-input buildings entered by hand
    (GUID → meter); `shares` — the split of a group meter edited by hand (else by model flow)."""
    res = HeatingTargets(g_heating=g_heating)
    for g in group_consumers(heating_inputs(snap.consumers)):
        meter, by_hand = group_meter(g, group_meters)
        if meter is None or not meter.G1:
            res.unmetered.extend(g.members)
            continue
        mg = MeteredGroup(g.members, meter, by_hand)
        res.metered.append(mg)
        res.metered_g += meter.G1
        source: Source = "group" if len(g.members) > 1 or by_hand else "meter"
        edited = (shares or {}).get(group_key(g))
        split = (
            {s: meter.G1 * v for s, v in edited.items()}
            if edited and len(g.members) > 1
            else split_by_model_flow(g.members, meter.G1)
        )
        for sys, gt in split.items():
            res.flows[sys] = FlowTarget(sys, gt, source, mg.sys_list)
        load = sum(kso_qo(c) for c in g.members)
        if load:
            res.metered_per_gcal[mg.sys_list] = meter.G1 / load

    if res.unmetered and g_heating:
        rest = g_heating - res.metered_g
        load = sum(kso_qo(c) for c in res.unmetered)
        res.remainder_g = rest
        if rest <= 0 or load <= 0:
            res.notes.append(
                f"Остаток для домов без приборов {rest:.1f} т/ч ≤ 0 — расход ЦТП не покрывает "
                "дома с приборами: проверить канал расходомера."
            )
        else:
            res.remainder_per_gcal = rest / load
            for c in res.unmetered:
                res.flows[c.sys] = FlowTarget(c.sys, rest * kso_qo(c) / load, "remainder")
            lo_hi = sorted(res.metered_per_gcal.values())
            span = f" (дома с приборами {lo_hi[0]:.1f}–{lo_hi[-1]:.1f})" if lo_hi else ""
            res.notes.append(
                f"Дома без приборов: ({g_heating:.1f} − {res.metered_g:.1f}) = {rest:.1f} т/ч "
                f"по Kso·Qo_r → {res.remainder_per_gcal:.1f} т/ч на Гкал/ч{span}."
            )
    return res


@dataclass(frozen=True)
class KsoFactor:
    members: tuple[int, ...]
    factor: float  # Q_fact / Q_model of the group
    q_fact: float
    q_model: float
    from_inlet: bool = False  # the meter is the _TS block («взят ввод»)


@dataclass
class HeatTargets:
    metered: list[KsoFactor] = field(default_factory=list)
    unmetered_factor: KsoFactor | None = None
    loss: float | None = None
    notes: list[str] = field(default_factory=list)


def heat_targets(
    targets: HeatingTargets, q_heating: float | None, loss: float | None
) -> HeatTargets:
    """Kso factors: metered groups by their meter, unmetered ones by the CTP balance."""
    res = HeatTargets(loss=loss)
    q_metered = 0.0
    for mg in targets.metered:
        if mg.meter.Q is None:
            continue
        q_model = sum(model_heat(c) or 0.0 for c in mg.members)
        q_metered += mg.meter.Q
        if q_model > 0:
            res.metered.append(
                KsoFactor(mg.sys_list, mg.meter.Q / q_model, mg.meter.Q, q_model,
                          mg.meter.from_inlet)
            )  # fmt: skip
    if targets.unmetered and q_heating:
        q_model = sum(model_heat(c) or 0.0 for c in targets.unmetered)
        q_fact = q_heating - q_metered - (loss or 0.0)
        if q_model > 0:
            res.unmetered_factor = KsoFactor(
                tuple(c.sys for c in targets.unmetered), q_fact / q_model, q_fact, q_model
            )
            res.notes.append(
                f"Дома без приборов: k = ({q_heating:.3f} − {q_metered:.3f} − "
                f"{loss or 0.0:.3f}) / {q_model:.4f} = {q_fact / q_model:.4f}."
            )
    return res
