"""Import of the old calculator export (format of the golden fixtures)."""

import dataclasses
import json
from datetime import date

from app.engine.parsers.common import PRIVATE_FIELDS
from app.engine.parsers.legacy import parse_legacy_export

from .conftest import imported, raw

ITERATIONS = [
    "it0_initial",
    "it1_step1",
    "it2_step1a",
    "it3_step2",
    "it4_step3_graph_trial_rejected",
    "it5_step3_rollback",
    "it6_step4_kso",
    "it7_step5_washers",
]


def test_import_reads_card_consumers_and_measurement() -> None:
    imp = imported("it0_initial")
    snap = imp.snapshot

    assert snap.ctp_name == "ЦТП Огородная, 87"
    assert snap.measured_on == date(2026, 2, 10)
    assert snap.tnv == -12.8
    assert snap.card["N_schem"] == 2
    assert len(snap.consumers) == 16
    assert sorted({c.scheme for c in snap.consumers}) == [4, 26]

    c = snap.consumer(33525)
    assert c.guid == "bea0ba13-c700-11e5-80e5-005056a05192"
    assert c.get("G1_OT") == 11


def test_import_prefills_ctp_fact_from_stored_inputs() -> None:
    fact = imported("it0_initial").fact

    assert fact.inlet is not None and fact.heating is not None
    assert (fact.inlet.G1, fact.inlet.G2, fact.inlet.T1, fact.inlet.T2) == (98.4, 99.7, 89.2, 57.0)
    assert (fact.inlet.P1, fact.inlet.P2, fact.inlet.Q) == (54.8, 48.4, 3.104)
    assert (fact.heating.G3, fact.heating.G4, fact.heating.T3, fact.heating.T4) == (
        143.4,
        136.5,
        78.5,
        60.3,
    )
    assert fact.dhw is None  # DHW facts are not stored in the old export
    assert fact.mode.tnv == -12.8
    assert fact.mode.thv == 5.0


def test_private_fields_are_dropped_everywhere() -> None:
    for name in ITERATIONS:
        snap = imported(name).snapshot
        for key in snap.card:
            assert key not in PRIVATE_FIELDS
            assert "adres" not in key.lower()
        for c in snap.consumers:
            for key in c.fields:
                assert key not in PRIVATE_FIELDS
                assert "adres" not in key.lower()

        dumped = json.dumps(dataclasses.asdict(snap), ensure_ascii=False, default=str)
        for key in PRIVATE_FIELDS:
            assert f'"{key}"' not in dumped


def test_private_values_are_dropped_even_when_present() -> None:
    data = json.loads(json.dumps(raw("it0_initial")))
    data["дома"][0]["Name"] = "ул. Секретная, 1"
    data["дома"][0]["Bld"] = "корп. 2"
    data["дома"][0]["Adres_full"] = "г. Город, ул. Секретная, 1"
    data["карточка_ЦТП"]["Adres"] = "ул. Секретная, 3"

    snap = parse_legacy_export(data).snapshot
    dumped = json.dumps(dataclasses.asdict(snap), ensure_ascii=False, default=str)
    assert "Секретная" not in dumped
