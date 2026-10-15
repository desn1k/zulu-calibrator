"""Import of the old offline calculator export («Собрать файл для разбора»), format of the fixtures.

Personal and address fields are dropped here, before anything else sees the data.
"""

from dataclasses import dataclass
from typing import Any

from app.engine.model import Consumer, CtpFact, DhwFact, HeatingFact, InletFact, Mode, Snapshot
from app.engine.parsers.common import parse_date, strip_private, to_float
from app.engine.units import PressureUnit


@dataclass
class LegacyImport:
    snapshot: Snapshot
    fact: CtpFact  # pre-filled from the stored form inputs; DHW facts are not in the export


def parse_legacy_export(data: dict[str, Any]) -> LegacyImport:
    card = strip_private(data.get("карточка_ЦТП") or {})
    inputs = data.get("все_поля_ввода") or {}
    settings = data.get("настройки") or {}

    consumers = []
    for row in data.get("дома") or []:
        fields = strip_private(row)
        consumers.append(
            Consumer(
                sys=int(fields["Sys"]),
                guid=fields.get("GUID"),
                scheme=int(fields.get("N_schem") or 0),
                fields=fields,
            )
        )

    first = consumers[0].fields if consumers else {}
    tnv = to_float(settings.get("t_замера"))
    if tnv is None:
        tnv = to_float(inputs.get("tnv")) or to_float(first.get("Tnv"))

    snapshot = Snapshot(
        ctp_name=str(data.get("объект") or inputs.get("objName") or first.get("CtpName") or ""),
        card=card,
        consumers=consumers,
        measured_on=parse_date(first.get("DateMea")),
        tnv=tnv,
    )
    return LegacyImport(snapshot=snapshot, fact=fact_from_inputs(inputs, tnv))


def fact_from_inputs(inputs: dict[str, Any], tnv: float | None) -> CtpFact:
    def f(key: str) -> float | None:
        return to_float(inputs.get(key))

    inlet = InletFact(
        G1=f("f_g1"), G2=f("f_g1r"), T1=f("f_t1"), T2=f("f_t2"), P1=f("f_p1"), P2=f("f_p2"),
        Q=f("f_q"),
    )  # fmt: skip
    heating = HeatingFact(
        G3=f("f_g2"), G4=f("f_g2r"), T3=f("f_t3"), T4=f("f_t2s"), P3=f("f_p3"), P4=f("f_p4"),
    )  # fmt: skip
    dhw = DhwFact(Gp=f("gGw"), Gc=f("gGc"), Tgv=f("gTgv"), Tc=f("gTc"))

    unit = PressureUnit.KGF_CM2 if inputs.get("punit") == "kgf" else PressureUnit.M_WATER
    mode = Mode(tnv=tnv, thv=f("dTcold") or 5.0, pressure_unit=unit)
    return CtpFact(
        inlet=inlet if any(v is not None for v in vars(inlet).values()) else None,
        heating=heating if any(v is not None for v in vars(heating).values()) else None,
        dhw=dhw if any(v is not None for v in vars(dhw).values()) else None,
        mode=mode,
    )
