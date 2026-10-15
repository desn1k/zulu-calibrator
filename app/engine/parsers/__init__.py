"""Input parsers behind one interface: `parse_upload(payload, previous) -> ParsedInput`.

Formats (the browser sends JSON, see app/static/import.js):

- Zulu (`{"format": "zulu", "card": "<CTP card text>", "consumers": [{column: value}, ...]}`):
  the CTP card pasted from Zulu and the consumer query export (xlsx / csv) — parsers/zulu.py;
- legacy: the old offline calculator export (format of tests/fixtures/ogorodnaya_87) —
  parsers/legacy.py.

Private fields are dropped by every parser before anything else sees the data.
"""

from dataclasses import dataclass
from typing import Any

from app.engine.model import CtpFact, Snapshot
from app.engine.parsers.legacy import parse_legacy_export
from app.engine.parsers.zulu import ParseError, parse_zulu

__all__ = ["ParseError", "ParsedInput", "parse_upload"]


@dataclass
class ParsedInput:
    snapshot: Snapshot
    fact: CtpFact | None  # meter facts found in the input; None = nothing new to pre-fill


def parse_upload(data: dict[str, Any], previous: Snapshot | None = None) -> ParsedInput:
    if data.get("format") == "zulu":
        rows = data.get("consumers")
        if not isinstance(rows, list):
            raise ParseError("Нет выгрузки потребителей.")
        card = data.get("card")
        snap, fact = parse_zulu(card if isinstance(card, str) else None, rows, previous)
        return ParsedInput(snap, fact)
    if "дома" not in data or "карточка_ЦТП" not in data:
        raise ParseError("В файле нет карточки ЦТП или списка потребителей.")
    imp = parse_legacy_export(data)
    return ParsedInput(imp.snapshot, imp.fact)
