"""Engine records ↔ JSON-able dicts for the database."""

import dataclasses
from datetime import date
from typing import Any

from app.engine.model import (
    Consumer,
    CtpFact,
    DhwFact,
    HeatingFact,
    InletFact,
    Mode,
    Snapshot,
    VentFact,
)
from app.engine.units import PressureUnit


def snapshot_to_dict(snap: Snapshot) -> dict[str, Any]:
    return {
        "ctp_name": snap.ctp_name,
        "card": snap.card,
        "consumers": [
            {"sys": c.sys, "guid": c.guid, "scheme": c.scheme, "fields": c.fields}
            for c in snap.consumers
        ],
        "measured_on": snap.measured_on.isoformat() if snap.measured_on else None,
        "tnv": snap.tnv,
        "warnings": list(snap.warnings),
    }


def snapshot_from_dict(d: dict[str, Any]) -> Snapshot:
    return Snapshot(
        ctp_name=d["ctp_name"],
        card=d["card"],
        consumers=[Consumer(**c) for c in d["consumers"]],
        measured_on=date.fromisoformat(d["measured_on"]) if d.get("measured_on") else None,
        tnv=d.get("tnv"),
        warnings=list(d.get("warnings") or []),
    )


def fact_to_dict(fact: CtpFact) -> dict[str, Any]:
    d = dataclasses.asdict(fact)
    d["mode"]["pressure_unit"] = str(fact.mode.pressure_unit)
    return d


def fact_from_dict(d: dict[str, Any] | None) -> CtpFact:
    d = d or {}
    mode = dict(d.get("mode") or {})
    if "pressure_unit" in mode:
        mode["pressure_unit"] = PressureUnit(mode["pressure_unit"])
    return CtpFact(
        inlet=InletFact(**d["inlet"]) if d.get("inlet") else None,
        heating=HeatingFact(**d["heating"]) if d.get("heating") else None,
        dhw=DhwFact(**d["dhw"]) if d.get("dhw") else None,
        mode=Mode(**mode),
        vent=VentFact(**d["vent"]) if d.get("vent") else None,
    )
