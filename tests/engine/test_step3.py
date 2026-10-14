"""Step 3: CTP inlet washer (algorithm «Шаг 3»)."""

import pytest

from app.engine.step3 import (
    correct_washer,
    flow_sensitivity_pct,
    step3,
    washer_from_scratch,
)

from .conftest import imported


def test_inlet_within_2_percent_keeps_installed_washer(fact) -> None:
    # it3: Gsum_pod 98.53 vs meter 98.4 (+0.1 %) — Ø72 stays (README: «уже стояла, оставлена»)
    res = step3(imported("it3_step2").snapshot, fact)
    assert res.rows == []
    assert any("72" in n for n in res.notes)


def test_washer_from_scratch() -> None:
    # ΔH_ЦТП = 10 − 0; ΔHш = 10 − 10·(100/110)² = 1.7355; d = 10·(100² / 1.7355)^¼
    w = washer_from_scratch(h_ras=10.0, dh_washer=0.0, g_fact=100.0, g_model=110.0)
    assert w.dh == pytest.approx(1.7355, abs=1e-4)
    assert w.d == pytest.approx(87.1, abs=0.05)


def test_no_washer_needed_when_model_flow_is_not_above_fact() -> None:
    w = washer_from_scratch(h_ras=10.0, dh_washer=0.0, g_fact=100.0, g_model=95.0)
    assert w.d is None
    assert "не нужна" in w.note


def test_correction_of_installed_washer() -> None:
    # building washer 33523 from it6 (README): 17.5 → 16.7
    w = correct_washer(d=17.5, h_ras=12.929, dh_washer=9.837, g_fact=8.9, g_model=9.605)
    assert w.d == pytest.approx(16.7, abs=0.05)


def test_correction_removes_washer_when_head_is_not_enough() -> None:
    w = correct_washer(d=40.0, h_ras=5.0, dh_washer=0.5, g_fact=150.0, g_model=100.0)
    assert w.d is None
    assert "убрать" in w.note


def test_sensitivity_example_from_algorithm() -> None:
    # Ø72, ΔHш 3.1 of 5.0 m: ±1 mm ≈ ±1.7 % of inlet flow
    assert flow_sensitivity_pct(d=72, dh_washer=3.1, h_ras=5.0) == pytest.approx(1.7, abs=0.05)


def test_step3_corrects_inlet_washer_when_flow_is_off(fact) -> None:
    snap = imported("it3_step2").snapshot
    card = dict(snap.card, Gsum_pod=104.0)  # +5.7 % vs 98.4
    res = step3(snap.__class__(ctp_name=snap.ctp_name, card=card, consumers=snap.consumers), fact)
    rows = {r.field: r.enter for r in res.rows}
    assert rows.get("Regul_G", 5) == 5  # already 5 in the card
    assert rows["Dshb_pod_u"] < 72
    assert rows.get("Nshb_pod_u", 1) == 1
