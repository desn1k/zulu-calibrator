"""Step criteria evaluated on a fresh export, and the «identical exports» trap."""

from app.engine.criteria import (
    criteria_step1,
    criteria_step2,
    criteria_step3,
    criteria_step4,
    criteria_step5,
    results_identical,
)

from .conftest import imported


def status(criteria) -> dict[str, bool]:
    return {c.key: c.passed for c in criteria}


def test_step1_criteria_on_it2(fact) -> None:
    s = status(criteria_step1(imported("it2_step1a").snapshot, fact))
    assert s["Gverh"] is True
    assert s["T11_niz"] is True  # 62.1, not ≈ T1
    assert s["T3so_t"] is True  # 78.3 vs 78.5
    assert s["T2so_t"] is False  # 61.45 vs 60.3 — outside ±0.7 °C
    assert s["Gsum_pod2"] is True  # −0.5 %
    assert s["Gsum_pod"] is True  # −1.2 %
    assert s["T2_t"] is False  # +4.1 %, limit ±4 %


def test_step1_criteria_catch_unrecalculated_scheme(fact) -> None:
    # it0: N_schem 2 but Gverh = 0 → result of a parallel scheme
    s = status(criteria_step1(imported("it0_initial").snapshot, fact))
    assert s["Gverh"] is False


def test_step2_criteria_on_it3() -> None:
    crit = criteria_step2(imported("it3_step2").snapshot, previous=imported("it2_step1a").snapshot)
    assert all(c.passed for c in crit), [c for c in crit if not c.passed]
    keys = {c.key for c in crit}
    assert {"Gcirc:33551", "Tcirc:33561", "Q_dhw_ctp"} <= keys


def test_step2_criteria_fail_before_circulation_fix() -> None:
    crit = criteria_step2(imported("it2_step1a").snapshot)
    # Hcirc = 0.1: model circulation cools 1–2 °C instead of 5–12 °C
    assert not status(crit)["Tcirc:33551"]


def test_step3_criteria_on_it3(fact) -> None:
    assert all(c.passed for c in criteria_step3(imported("it3_step2").snapshot, fact))


def test_step4_criteria_on_it6() -> None:
    crit = criteria_step4(imported("it6_step4_kso").snapshot)
    assert len(crit) == 8
    assert all(c.passed for c in crit)


def test_step4_criteria_fail_before_kso() -> None:
    assert not all(c.passed for c in criteria_step4(imported("it5_step3_rollback").snapshot))


def test_step5_criteria_on_it7(fact) -> None:
    crit = criteria_step5(imported("it7_step5_washers").snapshot, fact)
    assert all(c.passed for c in crit), [c for c in crit if not c.passed]
    assert "Gsum_pod2" in {c.key for c in crit}


def test_step5_criteria_fail_on_it6(fact) -> None:
    s = status(criteria_step5(imported("it6_step4_kso").snapshot, fact))
    assert s["Gso:33523"] is False  # +7.9 %


def test_step5_multi_input_house_uses_group_and_per_input_limits(fact) -> None:
    from app.engine.model import Consumer, Snapshot

    meter = {"G1_OT": 20.0, "G2_OT": 19.6, "Q_OT": 0.4, "Q_sum": 0.2}
    house = [  # split by Qo_r: 15 / 5 t/h; model 15.6 (+4 %) and 4.8 (−4 %): each within ±5 %
        Consumer(sys=1, guid="g", scheme=4, fields={"Qo_r": 0.3, "Gso": 15.6, **meter}),
        Consumer(sys=2, guid="g", scheme=4, fields={"Qo_r": 0.1, "Gso": 4.8, **meter}),
    ]
    snap = imported("it7_step5_washers").snapshot
    s = status(criteria_step5(Snapshot(ctp_name="x", card=snap.card, consumers=house), fact))
    assert s["Gso:1"] is True and s["Gso:2"] is True
    assert s["Gso:group:g"] is True  # Σ 20.4 vs 20.0 = +2.0 %


def test_identical_results_trap() -> None:
    # it5 reverted the rejected graph trial: results identical to it3
    assert results_identical(
        imported("it3_step2").snapshot, imported("it5_step3_rollback").snapshot
    )
    assert not results_identical(imported("it2_step1a").snapshot, imported("it3_step2").snapshot)
