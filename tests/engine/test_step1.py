"""Step 1: CTP scheme, heating HX, DHW stages (scheme 2), Kgv (algorithm «Шаг 1»)."""

import dataclasses

import pytest

from app.engine.step1 import (
    DRAW_OFF_HINT,
    KGV_BY_HEAT_NOTE,
    choose_scheme,
    kgv_rows,
    scheme2_test_params,
    step1,
    suggest_free_params,
)

from .conftest import by_target, imported


@pytest.fixture
def params(fact):
    return scheme2_test_params(fact, t22_niz=59.0, t12_verh=57.5)


def test_scheme_by_temperatures(fact) -> None:
    # T2 inlet 57.0 < T4 60.3 → there is a first stage on the return → two-stage, N_schem 2
    assert choose_scheme(fact).n_schem == 2


def test_heating_hx_golden(params) -> None:
    p = params.rounded()
    assert (p["T11_i"], p["T12_i"], p["T21_i"], p["T22_i"]) == (89.2, 61.1, 60.3, 78.5)
    assert (p["G1_i"], p["G2_i"]) == (92.8, 143.4)


def test_stage1_golden(params) -> None:
    p = params.rounded()
    assert (p["T11_i_niz"], p["T12_i_niz"], p["T21_i_niz"], p["T22_i_niz"]) == (60.9, 57.2, 5, 59)
    assert p["Q_i_niz"] == 0.362


def test_stage2_golden(params) -> None:
    p = params.rounded()
    assert (p["T11_i_verh"], p["T12_i_verh"], p["T21_i_verh"], p["T22_i_verh"]) == (
        89.2,
        57.5,
        55.1,
        62.8,
    )
    assert p["Q_i_verh"] == 0.178


def test_stage_flows(params) -> None:
    assert params.draw_off == pytest.approx(6.7)
    assert params.g_verh == pytest.approx(5.6, abs=0.05)


def test_closure(params) -> None:
    # README: G1_i·(T1 − T12_i)/1000 = 2.608 (with the rounded values to enter) vs Qсо 2.610
    assert params.qso == pytest.approx(2.610, abs=5e-4)
    assert params.closure_rounded == pytest.approx(2.608, abs=5e-4)
    assert params.closure_ok
    assert params.t12_i_gap_ok  # T12_i ≥ T21_i + 0.8


def test_suggested_free_params_respect_rules(fact) -> None:
    t22_niz, t12_verh = suggest_free_params(fact)
    p = scheme2_test_params(fact, t22_niz=t22_niz, t12_verh=t12_verh)
    assert p.values["T11_i_niz"] - t22_niz == pytest.approx(2.0, abs=0.05)
    assert t12_verh == pytest.approx(p.values["T21_i_verh"] + 2.0, abs=0.05)
    assert p.closure_ok


def test_kgv_auto_rule_on_ogorodnaya_differs_from_the_session() -> None:
    # 2026-10-15 automatic rule: all metered objects are «alive» (Tgv_t within 10 °C of T1_GVS) →
    # Kgv·G/Ggv. The Огородная session used formula 1.3 (golden test below pins that override).
    # Reported to Andrew: 33553 0.338 vs 0.361 (−6.4 %), 33559 0.295 vs 0.31 (−4.8 %),
    # 33561 0.259 vs 0.25 (+3.6 %); 33567 by heat 0.072 unchanged.
    rows = kgv_rows(imported("it0_initial").snapshot.consumers)
    assert by_target(rows, "Kgv") == {"33553": 0.338, "33559": 0.295, "33561": 0.259,
                                      "33567": 0.072}  # fmt: skip
    assert all("ГВС в модели жива" in r.note for r in rows if r.target != "33567")


def test_kgv_golden_from_it0(fact) -> None:
    # the session's choice: «всегда формула 1.3» (manual override in step 1 settings)
    rows = kgv_rows(imported("it0_initial").snapshot.consumers, "formula")
    kgv = by_target(rows, "Kgv")
    # README gives 2 decimals (0.36 / 0.31 / 0.25 / 0.07); Kgv is now rounded to 3.
    assert kgv == {"33553": 0.361, "33559": 0.31, "33561": 0.25, "33567": 0.072}


def test_kgv_without_measured_flow_falls_back_to_heat() -> None:
    rows = kgv_rows(imported("it0_initial").snapshot.consumers, "formula")
    [row] = [r for r in rows if r.target == "33567"]
    assert row.note == KGV_BY_HEAT_NOTE == "по теплу (расход не измерен)"
    others = [r for r in rows if r.target != "33567"]
    assert all(r.note != KGV_BY_HEAT_NOTE for r in others)


def test_kgv_within_tolerance_is_not_changed() -> None:
    rows = kgv_rows(imported("it0_initial").snapshot.consumers, "formula")
    assert {"33551", "33569", "33573", "33575"}.isdisjoint({r.target for r in rows})


def test_step1_result_on_initial_state(fact) -> None:
    res = step1(
        imported("it0_initial").snapshot, fact, t22_niz=59.0, t12_verh=57.5, kgv_mode="formula"
    )
    ctp = {r.field: (r.current, r.enter) for r in res.rows if r.target == "ЦТП"}

    assert ctp["T12_i_niz"] == (40, 57.2)
    assert ctp["T11_i_niz"] == (70, 60.9)
    assert ctp["Q_i_verh"] == (1.5, 0.178)
    assert "N_schem" not in ctp  # already 2
    assert by_target(res.rows, "Kgv")["33553"] == 0.361

    for field in ("Kso", "Qo_r", "Qgv_sred", "Dshb_pod_u", "Hgv2_ras", "Hgv2_obr"):
        assert field in res.do_not_touch


def test_step1_shows_balanced_and_meter_t2(fact) -> None:
    res = step1(imported("it0_initial").snapshot, fact, t22_niz=59.0, t12_verh=57.5)
    assert res.t2_balanced == pytest.approx(57.19, abs=0.005)
    assert res.t2_meter == 57.0


def test_hint_when_houses_draw_off_is_below_ctp(fact) -> None:
    # check 7: houses 4.7 t/h < CTP 6.7 t/h, draw-off source «дома»
    res = step1(imported("it0_initial").snapshot, fact, t22_niz=59.0, t12_verh=57.5)
    assert DRAW_OFF_HINT in res.notes
    assert DRAW_OFF_HINT == (
        "T2 ввода физически не опустится до факта — допустимо принять с отклонением"
    )


def test_no_hint_when_houses_draw_off_covers_ctp(fact) -> None:
    dhw = dataclasses.replace(fact.dhw, Gc=18.6)  # CTP draw-off 4.5 < houses 4.7
    low = dataclasses.replace(fact, dhw=dhw)
    res = step1(imported("it0_initial").snapshot, low, t22_niz=59.0, t12_verh=57.5)
    assert DRAW_OFF_HINT not in res.notes


def test_step1_has_no_rows_once_entered(fact) -> None:
    res = step1(imported("it2_step1a").snapshot, fact, t22_niz=59.0, t12_verh=57.5)
    assert [r for r in res.rows if r.target == "ЦТП"] == []


def test_ctp_draw_off_target_is_not_implemented_yet(fact) -> None:
    with pytest.raises(NotImplementedError):
        step1(imported("it0_initial").snapshot, fact, draw_off_source="ctp")
