"""Step 5: building washers and washers in series (algorithm «Шаги 4–5»)."""

import pytest

from app.engine.model import Consumer, Snapshot
from app.engine.step5 import step5

from .conftest import by_target, imported

WASHERS_FROM_IT6 = {"33523": 16.7, "33539": 24.0, "33525": 21.7, "36749": 36.9}
SERIES_FROM_IT7 = {"33525": 17.5, "33531": 20.0, "33535": 21.5}


def test_washer_corrections_golden_from_it6(fact) -> None:
    res = step5(imported("it6_step4_kso").snapshot, fact)
    corrections = {r.target: r.enter for r in res.rows if r.field == "Dshb_so_pod_u"}
    for sys, d in WASHERS_FROM_IT6.items():
        assert corrections[sys] == pytest.approx(d, abs=0.05), sys
    # houses within ±2 % are not touched by the correction
    assert {"33531", "33535", "33563", "36751"}.isdisjoint(
        {sys for sys in corrections if sys not in SERIES_FROM_IT7}
    )


def test_washers_in_series_golden_from_it7(fact) -> None:
    res = step5(imported("it7_step5_washers").snapshot, fact)
    d_eq = by_target(res.rows, "Dshb_so_pod_u")
    assert d_eq.keys() == SERIES_FROM_IT7.keys()
    for sys, d in SERIES_FROM_IT7.items():
        assert d_eq[sys] == pytest.approx(d, abs=0.05), sys
    # the inlet washer is cleared for each replaced pair
    cleared = {
        r.target for r in res.rows if r.field in ("Dshb_pod", "Nshb_pod") and r.enter is None
    }
    assert SERIES_FROM_IT7.keys() <= cleared


def test_nshb_without_diameter_is_junk_and_cleared(fact) -> None:
    res = step5(imported("it7_step5_washers").snapshot, fact)
    [row] = [r for r in res.rows if r.target == "36751"]
    assert (row.field, row.current, row.enter) == ("Nshb_pod", 1, None)


def test_house_washers_wait_for_ctp_inlet(fact) -> None:
    snap = imported("it6_step4_kso").snapshot
    card = dict(snap.card, Gsum_pod=104.0)  # inlet +5.7 % — step 3 has not converged
    res = step5(Snapshot(ctp_name=snap.ctp_name, card=card, consumers=snap.consumers), fact)
    assert res.rows == []
    assert any("шайба ввода" in n.lower() or "ввод цтп" in n.lower() for n in res.notes)


def test_house_without_washer_gets_one_from_scratch(fact) -> None:
    snap = imported("it7_step5_washers").snapshot
    house = Consumer(
        sys=1,
        guid="g",
        scheme=4,
        fields={
            "Qo_r": 0.2,
            "Kso": 1.0,
            "Regul_G": 0,
            "G1_OT": 10.0,
            "G2_OT": 10.0,
            "Q_OT": 0.2,
            "Gso": 11.0,  # +10 %
            "H_ras": 10.0,
            "dHshb_so_pod": 0.0,
            "Dshb_so_pod_u": None,
            "Nshb_so_pod_u": None,
        },
    )
    res = step5(Snapshot(ctp_name="x", card=snap.card, consumers=[house]), fact)
    rows = {r.field: r.enter for r in res.rows if r.target == "1"}
    # ΔHш = 10 − 10·(10/11)² = 1.7355; d = 10·(10² / 1.7355)^¼ = 27.55
    assert rows["Dshb_so_pod_u"] == pytest.approx(27.6, abs=0.05)
    assert rows["Nshb_so_pod_u"] == 1


def test_house_with_flow_regulator_is_skipped(fact) -> None:
    snap = imported("it6_step4_kso").snapshot
    regulated = [
        Consumer(sys=c.sys, guid=c.guid, scheme=c.scheme, fields=dict(c.fields, Regul_G=1))
        if c.sys == 33523
        else c
        for c in snap.consumers
    ]
    res = step5(Snapshot(ctp_name=snap.ctp_name, card=snap.card, consumers=regulated), fact)
    assert "33523" not in {r.target for r in res.rows}
