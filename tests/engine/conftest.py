import json
from functools import cache
from pathlib import Path

import pytest

from app.engine.model import CtpFact, DhwFact, HeatingFact, InletFact, Mode, Snapshot
from app.engine.parsers.legacy import LegacyImport, parse_legacy_export
from app.engine.parsers.zulu import fact_from_card, parse_zulu, read_consumer_csv

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


ROOT = Path(__file__).resolve().parents[1] / "fixtures"
ZULU_SETS = ("chernyshevskogo_8", "beregovaya_1_15", "verkhnyaya_24", "pionerskaya_2_30_36")


def zulu_iterations(name: str) -> list[str]:
    return sorted(p.name for p in (ROOT / name).iterdir() if p.is_dir())


@cache
def zulu_raw(name: str, iteration: str) -> tuple[str | None, tuple[dict, ...]]:
    """(card text or None, consumer rows) of one iteration of a real Zulu golden set."""
    folder = ROOT / name / iteration
    card = folder / "ctp_card.tsv"
    text = card.read_text(encoding="utf-8") if card.exists() else None
    rows = read_consumer_csv((folder / "consumers.csv").read_text(encoding="utf-8"))
    return text, tuple(rows)


def zulu(name: str, iteration: str, previous: Snapshot | None = None) -> tuple[Snapshot, CtpFact]:
    """Snapshot and CTP fact of an iteration; the fact comes from the latest card of the set."""
    text, rows = zulu_raw(name, iteration)
    if text is None and previous is None:
        previous = zulu_last_card_snapshot(name)
    snap, fact = parse_zulu(text, [dict(r) for r in rows], previous)
    return snap, fact if fact is not None else fact_from_card(zulu_last_card_snapshot(name).card)


@cache
def zulu_last_card_snapshot(name: str) -> Snapshot:
    """Snapshot of the last iteration that has a CTP card (meter blocks are the same in every
    card of a set; Пионерская has cards only in it4–it6)."""
    for it in reversed(zulu_iterations(name)):
        text, rows = zulu_raw(name, it)
        if text is not None:
            return parse_zulu(text, [dict(r) for r in rows])[0]
    raise LookupError(name)
