"""Real Zulu input: the CTP card pasted from Zulu and the consumer query export (xlsx / csv).

CTP card: one `Field<TAB>value` line per field (2+ spaces also separate), empty values allowed,
decimal comma or dot. The meter blocks of the CTP come in the same card: `*_TS` inlet, `*_OT`
heating, `*_GVS` DHW at the CTP, `*_SV` ventilation. `Adres` and other address fields are dropped.

Consumers: rows with the real Zulu column names (header row of the export). The browser has
already dropped `Name`, `Bld`, `Adres`, `FIAS_*`, `UUTE_Name`; they are dropped here again.
`Regul_G` / `Regul_T` come as text labels and are mapped to the Zulu codes.
"""

import csv
import io
import re
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
from app.engine.parsers.common import (
    is_private,
    is_private_card,
    parse_date,
    to_float,
    to_value,
)

# Text labels of the export → Zulu codes (docs/algorithm.md, «Сброс к базе» and «Схемы
# потребителей»). Only labels seen in real exports are listed; an unknown label stops the import
# instead of being guessed.
REGUL_LABELS: dict[str, dict[str, int]] = {
    "Regul_G": {"без регулятора": 0},
    "Regul_T": {"без регулятора": 0, "регулятор температуры": 1},
}

_SEPARATOR = re.compile(r"\t| {2,}")


class ParseError(ValueError):
    """Input that cannot be read; the message is shown to the user (never contains addresses)."""


def parse_ctp_card(text: str) -> dict[str, Any]:
    """Field → value. Values are numbers where numeric, text otherwise, None when empty."""
    card: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.strip("\r\n")
        if not line.strip():
            continue
        parts = _SEPARATOR.split(line.strip(), maxsplit=1)
        key = parts[0].strip()
        if not key or is_private_card(key):
            continue
        card[key] = to_value(parts[1]) if len(parts) > 1 else None
    if "N_schem" not in card:
        raise ParseError(
            "Карточка ЦТП не распознана: нет поля N_schem (строки «Поле<TAB>значение»)."
        )
    return card


def map_regul(name: str, value: Any) -> Any:
    if value is None or isinstance(value, int | float):
        return value
    labels = REGUL_LABELS.get(name)
    if labels is None:
        return value
    code = labels.get(str(value).strip().lower())
    if code is None:
        raise ParseError(
            f"Неизвестная подпись {name}: «{value}». Сообщите её, чтобы добавить код Zulu."
        )
    return code


def parse_consumer_rows(rows: list[dict[str, Any]]) -> list[Consumer]:
    consumers = []
    for n, row in enumerate(rows, start=2):  # row 1 is the header
        fields = {}
        for key, value in row.items():
            key = str(key).strip()
            if not key or is_private(key):
                continue
            v = to_value(value)
            fields[key] = map_regul(key, v) if key in REGUL_LABELS else v
        if not any(v is not None for v in fields.values()):
            continue  # empty line at the end of an export
        sys = fields.get("Sys")
        if not isinstance(sys, int):
            raise ParseError(f"Строка {n} выгрузки потребителей: нет Sys.")
        scheme = fields.get("N_schem")
        consumers.append(
            Consumer(
                sys=sys,
                guid=str(fields["GUID"]) if fields.get("GUID") is not None else None,
                scheme=int(scheme) if isinstance(scheme, int | float) else 0,
                fields=fields,
            )
        )
    if not consumers:
        raise ParseError("В выгрузке потребителей нет строк с Sys.")
    return consumers


def read_consumer_csv(text: str) -> list[dict[str, Any]]:
    """Rows of a csv export (`,` or `;`), header row first. Used for csv files and in tests."""
    text = text.lstrip("﻿")
    first = text.split("\n", 1)[0]
    delimiter = ";" if first.count(";") > first.count(",") else ","
    return list(csv.DictReader(io.StringIO(text), delimiter=delimiter))


def _block(card: dict[str, Any], suffix: str) -> dict[str, float | None]:
    return {
        k: to_float(card.get(f"{k}_{suffix}")) for k in ("G1", "G2", "T1", "T2", "P1", "P2", "Q")
    }


def _any(values: dict[str, float | None]) -> bool:
    return any(v is not None for v in values.values())


def fact_from_card(card: dict[str, Any]) -> CtpFact:
    """CTP meter facts from the card blocks; a block with no values is «нет прибора»."""
    ts, ot, gvs, sv = (_block(card, s) for s in ("TS", "OT", "GVS", "SV"))
    inlet = InletFact(**ts) if _any(ts) else None
    heating = (
        HeatingFact(
            G3=ot["G1"], G4=ot["G2"], T3=ot["T1"], T4=ot["T2"], P3=ot["P1"], P4=ot["P2"],
            Q=ot["Q"],
        )
        if _any(ot)
        else None
    )  # fmt: skip
    dhw = (
        DhwFact(
            Gp=gvs["G1"], Gc=gvs["G2"], Tgv=gvs["T1"], Tc=gvs["T2"], Pp=gvs["P1"], Pc=gvs["P2"],
            Q=gvs["Q"],
        )
        if _any(gvs)
        else None
    )  # fmt: skip
    vent = VentFact(**sv) if _any(sv) else None
    thv = to_float(card.get("Thv"))
    mode = Mode(tnv=to_float(card.get("Tnv")), thv=5.0 if thv is None else thv)
    return CtpFact(inlet=inlet, heating=heating, dhw=dhw, mode=mode, vent=vent)


def parse_zulu(
    card_text: str | None,
    rows: list[dict[str, Any]],
    previous: Snapshot | None = None,
) -> tuple[Snapshot, CtpFact | None]:
    """Snapshot of one verification run. Without a card (consumers only) the previous card is
    reused with a warning; the fact is None then (nothing new to pre-fill)."""
    consumers = parse_consumer_rows(rows)
    warnings: list[str] = []
    if card_text and card_text.strip():
        card = parse_ctp_card(card_text)
        fact = fact_from_card(card)
        ctp_name = card.pop("Name", None)
        if previous is not None and previous.card == card:
            warnings.append(
                "Карточка ЦТП совпадает с предыдущей — возможно, вставлена старая карточка; "
                "результаты ЦТП взяты из неё."
            )
    elif previous is not None:
        card, fact, ctp_name = dict(previous.card), None, previous.ctp_name
        warnings.append(
            "Карточка ЦТП не обновлена — взята из предыдущей выгрузки; результаты ЦТП "
            "(Gsum_pod, T2_t …) могут быть устаревшими."
        )
    else:
        raise ParseError("Вставьте карточку ЦТП из Zulu.")

    ctp_name = ctp_name or consumers[0].get("CtpName") or ""
    first = consumers[0].fields
    tnv = to_float(card.get("Tnv"))
    if tnv is None:
        tnv = to_float(first.get("Tnv"))
    snap = Snapshot(
        ctp_name=str(ctp_name).strip(),
        card=card,
        consumers=consumers,
        measured_on=parse_date(card.get("DateMea")) or parse_date(first.get("DateMea")),
        tnv=tnv,
        warnings=warnings,
    )
    return snap, fact
