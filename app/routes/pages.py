from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory=Path(__file__).resolve().parent.parent / "templates")

router = APIRouter()


def ru(value: Any, digits: int | None = None) -> str:
    """Number for display and for copying into Zulu: decimal comma, no trailing zeros."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        v = round(value, 6 if digits is None else digits)
        text = repr(v)
        if "e" in text:
            text = f"{v:.6f}".rstrip("0")
        if text.endswith(".0"):
            text = text[:-2]
        return text.rstrip("0").rstrip(".").replace(".", ",") if "." in text else text
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return str(value)


templates.env.filters["ru"] = ru


def value_digits(key: str) -> int:
    """Decimals of a criterion value: 3 for heat (Gcal/h), 1 for t/h, °C, m and %."""
    return 3 if key.startswith("Q") else 1


templates.env.filters["value_digits"] = value_digits


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")
