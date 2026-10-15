"""Real Zulu formats: CTP card pasted from Zulu and the consumer query export."""

import dataclasses
import json
from datetime import date

import pytest

from app.engine.parsers import ParseError, parse_upload
from app.engine.parsers.common import PRIVATE_FIELDS
from app.engine.parsers.zulu import (
    fact_from_card,
    parse_consumer_rows,
    parse_ctp_card,
    parse_zulu,
    read_consumer_csv,
)

from .conftest import ZULU_SETS, zulu, zulu_iterations, zulu_raw

SCHEMES = {
    "chernyshevskogo_8": 12,
    "beregovaya_1_15": 3,
    "verkhnyaya_24": 5,
    "pionerskaya_2_30_36": 6,
}


@pytest.mark.parametrize("name", ZULU_SETS)
def test_every_iteration_of_the_golden_sets_parses(name: str) -> None:
    previous = None
    for it in zulu_iterations(name):
        snap, fact = zulu(name, it, previous)
        assert snap.card["N_schem"] == SCHEMES[name]
        assert snap.measured_on == date(2026, 2, 10)
        assert snap.tnv == -12.8
        assert snap.ctp_name.startswith("ЦТП ")
        assert snap.consumers and all(isinstance(c.sys, int) for c in snap.consumers)
        assert fact.inlet is not None and fact.heating is not None
        previous = snap


def test_card_meter_blocks_become_the_ctp_fact() -> None:
    snap, fact = zulu("chernyshevskogo_8", "it7_step4_kso_finetune")
    i, h, d = fact.inlet, fact.heating, fact.dhw
    assert (i.G1, i.G2, i.T1, i.T2, i.P1, i.P2, i.Q) == (129.5, 132.4, 89.2, 53, 68.8, 55.9, 4.571)
    assert (h.G3, h.G4, h.T3, h.T4, h.P3, h.P4, h.Q) == (
        128.5,
        128.2,
        89.2,
        58.2,
        66.6,
        56.3,
        4.012,
    )
    assert (d.Gp, d.Gc, d.Tgv, d.Tc, d.Pp, d.Q) == (4.7, None, 65.8, None, 58.3, 0.285)
    assert fact.vent is None  # `_SV` block empty
    assert fact.mode.tnv == -12.8
    assert snap.ctp_name == "ЦТП Чернышевского. 8"
    assert "Name" not in snap.card


def test_card_accepts_spaces_decimal_comma_and_empty_values() -> None:
    text = (
        "Name\tЦТП Тест\nN_schem  12\nH_geo\t40,23\nT1_TS    89,2\nPodpit\t\nKb\n"
        "Adres\tул. Секретная, 1\n"
    )
    card = parse_ctp_card(text)
    assert card["N_schem"] == 12
    assert card["H_geo"] == 40.23
    assert card["T1_TS"] == 89.2
    assert card["Podpit"] is None and card["Kb"] is None
    assert "Adres" not in card
    assert fact_from_card(card).inlet.T1 == 89.2


def test_card_without_n_schem_is_rejected() -> None:
    with pytest.raises(ParseError):
        parse_ctp_card("просто текст\nбез полей")


def test_regul_labels_are_mapped_to_codes() -> None:
    snap, _ = zulu("pionerskaya_2_30_36", "it2_step5_supply_washers_regul_test")
    values = {(c.get("Regul_G"), c.get("Regul_T")) for c in snap.consumers}
    assert values <= {(0, 0), (0, 1), (None, None), (0, None), (None, 0), (None, 1)}
    assert (0, 0) in values  # b2 «Без регулятора» test run
    assert (0, 1) in values  # «Регулятор температуры»


def test_unknown_regul_label_stops_the_import() -> None:
    rows = [{"Sys": "1", "N_schem": "4", "Regul_T": "Что-то новое"}]
    with pytest.raises(ParseError, match="Regul_T"):
        parse_consumer_rows(rows)


def test_semicolon_csv_with_decimal_comma() -> None:
    rows = read_consumer_csv("﻿Sys;N_schem;Qo_r;Name\n101;4;0,22;ул. Секретная\n")
    [c] = parse_consumer_rows(rows)
    assert (c.sys, c.scheme, c.get("Qo_r")) == (101, 4, 0.22)
    assert "Name" not in c.fields


def test_consumers_only_reuses_the_previous_card_with_a_warning() -> None:
    previous, _ = zulu("chernyshevskogo_8", "it6_step4_kso")
    _, rows = zulu_raw("chernyshevskogo_8", "it7_step4_kso_finetune")
    snap, fact = parse_zulu(None, [dict(r) for r in rows], previous)
    assert fact is None
    assert snap.card == previous.card
    assert snap.ctp_name == previous.ctp_name
    assert any("не обновлена" in w for w in snap.warnings)


def test_consumers_only_without_any_card_is_rejected() -> None:
    _, rows = zulu_raw("pionerskaya_2_30_36", "it0_after_step1_dhw")
    with pytest.raises(ParseError):
        parse_zulu(None, [dict(r) for r in rows])


def test_a_card_identical_to_the_previous_one_is_flagged() -> None:
    # README verkhnyaya_24: the it3 card is a duplicate of it2.
    it2, _ = zulu("verkhnyaya_24", "it2_step5_washers_nozzles_r1")
    it3, _ = zulu("verkhnyaya_24", "it3_step4_kso_metered", it2)
    assert any("совпадает с предыдущей" in w for w in it3.warnings)
    it4, _ = zulu("verkhnyaya_24", "it4_roughness_0_5_kso_finetune", it3)
    assert not it4.warnings


def test_parse_upload_dispatches_zulu_and_legacy() -> None:
    text, rows = zulu_raw("beregovaya_1_15", "it0_initial")
    parsed = parse_upload({"format": "zulu", "card": text, "consumers": [dict(r) for r in rows]})
    assert parsed.snapshot.card["N_schem"] == 3
    assert parsed.fact is not None and parsed.fact.dhw.Gc == 2.1
    with pytest.raises(ParseError):
        parse_upload({"что-то": 1})


PRIVATE_VALUE = "Секретная"


@pytest.mark.parametrize("name", ZULU_SETS)
def test_private_fields_never_pass_the_zulu_parser(name: str) -> None:
    for it in zulu_iterations(name):
        text, rows = zulu_raw(name, it)
        rows = [
            {
                **r,
                "Name": f"ул. {PRIVATE_VALUE}, 1",
                "Bld": "корп. 2",
                "Adres": f"г. Город, ул. {PRIVATE_VALUE}, 1",
                "FIAS_Adress": f"{PRIVATE_VALUE} ФИАС",
                "FIAS_ID": "0c5b2444-70a0-4932-980c-b4dc0d3f02b5",
                "UUTE_Name": f"УУТЭ {PRIVATE_VALUE}",
            }
            for r in rows
        ]
        if text is not None:
            text += f"Adres\tул. {PRIVATE_VALUE}, 3\nFIAS_Adress\t{PRIVATE_VALUE}\n"
            snap, _ = parse_zulu(text, rows)
        else:
            snap, _ = zulu(name, it)  # card reused from another iteration
            snap, _ = parse_zulu(None, rows, snap)
        dumped = json.dumps(dataclasses.asdict(snap), ensure_ascii=False, default=str)
        assert PRIVATE_VALUE not in dumped
        assert "0c5b2444" not in dumped
        for key in PRIVATE_FIELDS:
            assert f'"{key}"' not in dumped
