"""Helpers shared by the input parsers: privacy filter and value conversion.

AGENTS.md «Privacy»: consumer Name, Bld, Adres, FIAS and any other address field never pass the
parser. The browser drops them first (app/static/import.js); the server drops them again here.
"""

import re
from datetime import date, datetime
from typing import Any

# Consumer columns that are personal or address data. The CTP card keeps `Name` (the CTP name
# is stored, its address is not), see is_private_card().
PRIVATE_FIELDS = frozenset({"Name", "Bld", "Adres", "FIAS_Adress", "FIAS_ID", "UUTE_Name"})
PRIVATE_PARTS = ("adres", "address", "fias")


def is_private(key: str) -> bool:
    k = key.lower()
    return key in PRIVATE_FIELDS or any(p in k for p in PRIVATE_PARTS)


def is_private_card(key: str) -> bool:
    return key != "Name" and is_private(key)


def strip_private(fields: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in fields.items() if not is_private(k)}


_INT = re.compile(r"^[+-]?\d+$")


def to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip().replace(",", ".").replace("−", "-")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_value(value: Any) -> Any:
    """A pasted / exported cell: None if empty, int or float if numeric (decimal comma or dot),
    the stripped text otherwise."""
    if value is None or isinstance(value, bool | int | float):
        return value
    text = str(value).strip()
    if not text:
        return None
    if _INT.match(text):
        return int(text)
    number = to_float(text)
    return text if number is None else number


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value).strip()[:10], fmt).date()
        except ValueError:
            continue
    return None
