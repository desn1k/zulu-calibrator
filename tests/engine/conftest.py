import json
from functools import cache
from pathlib import Path

import pytest

from app.engine.legacy import LegacyImport, parse_legacy_export
from app.engine.model import CtpFact, DhwFact, HeatingFact, InletFact, Mode

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ogorodnaya_87"


@cache
def raw(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def imported(name: str) -> LegacyImport:
    return parse_legacy_export(raw(name))


def ogorodnaya_fact() -> CtpFact:
    """CTP meter facts from tests/fixtures/ogorodnaya_87/README.md (entered manually)."""
    return CtpFact(
        inlet=InletFact(G1=98.4, G2=99.7, T1=89.2, T2=57.0, P1=54.8, P2=48.4, Q=3.104),
        heating=HeatingFact(G3=143.4, G4=136.5, T3=78.5, T4=60.3, P3=70.9, P4=53.3, Q=2.610),
        dhw=DhwFact(Gp=23.1, Gc=16.4, Tgv=62.8, Tc=53.5, Pp=None, Pc=None, Q=0.537),
        mode=Mode(tnv=-12.8, t_source=88.7, thv=5.0, data_type="day"),
    )


@pytest.fixture
def fact() -> CtpFact:
    return ogorodnaya_fact()


def by_target(rows, field: str) -> dict:
    """{target: enter} for recommendation rows of one field."""
    return {r.target: r.enter for r in rows if r.field == field}
