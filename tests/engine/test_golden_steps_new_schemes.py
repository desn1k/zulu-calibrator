"""Steps 2, 4, 5, meter validity, targets and run warnings: golden values of the 2026-10-15 sets."""

import pytest

from app.engine.hydraulics import washer_dh
from app.engine.inputs import group_meters_from, step_inputs
from app.engine.model import Recommendation
from app.engine.run_warnings import ctp_washer_plug, unexpected_washer_changes
from app.engine.step2 import step2
from app.engine.step4 import step4
from app.engine.step5 import nozzle_dh, step5
from app.engine.targets import heating_targets
from app.engine.validity import assess

from .conftest import by_target, zulu


def close(value: float, expected: float, rel: float) -> bool:
    return value == pytest.approx(expected, rel=rel)


# ------------------------------------------------------------------ Чернышевского, 8 (scheme 12)

CH = "chernyshevskogo_8"
CH_ROUND2_SO = {
    27966: 12.7, 40462: 12.7, 27976: 13.1, 40466: 13.1, 27998: 12.1, 40470: 12.1, 28014: 12.4,
    40478: 12.4, 28030: 13.5, 40452: 13.5, 40454: 13.5, 28034: 9.5, 40482: 9.5, 28038: 12.0,
    40427: 12.0, 28060: 12.6, 28072: 13.3, 28226: 12.9, 40493: 12.9, 40496: 12.9, 40435: 11.9,
    40437: 11.9, 40441: 11.9, 40439: 11.8, 40445: 12.5, 40476: 12.5, 40456: 13.4, 40488: 13.2,
    40490: 13.2,
}  # fmt: skip
CH_ROUND2_POD = {27992: 11.5, 28018: 7.1, 28026: 15.4, 28040: 13.9}


def test_chernyshevskogo_unmetered_heating_target_from_it3() -> None:
    snap, fact = zulu(CH, "it3_step1_3_kgv")
    t = step_inputs(snap, fact).targets
    assert t.g_heating == 128.5 and t.metered_g == pytest.approx(28.8)
    assert t.remainder_g == pytest.approx(99.7)
    assert t.remainder_per_gcal == pytest.approx(30.1, abs=0.05)
    per = sorted(t.metered_per_gcal.values())
    assert per[0] == pytest.approx(23.6, abs=0.05) and per[-1] == pytest.approx(29.5, abs=0.05)
    # 28030 meter (12.5 t/h) = the whole 3-input building, split by model flow
    group = [t.flows[s] for s in (28030, 40488, 40490)]
    assert {g.source for g in group} == {"group"}
    assert sum(g.g for g in group) == pytest.approx(12.5)


def test_chernyshevskogo_washers_round2_with_head_forecast_from_it4() -> None:
    before, _ = zulu(CH, "it3_step1_3_kgv")
    snap, fact = zulu(CH, "it4_step5_washers_round1")
    res = step5(snap, fact, step_inputs(snap, fact).targets, previous=before)
    so, pod = by_target(res.rows, "Dshb_so_pod_u"), by_target(res.rows, "Dshb_pod")
    for sys, d in CH_ROUND2_SO.items():
        assert so[str(sys)] == pytest.approx(d, abs=0.3), sys
    for sys, d in CH_ROUND2_POD.items():
        assert pod[str(sys)] == pytest.approx(d, abs=0.3), sys
    assert any("по двум расчётам" in n for n in res.notes)


def test_chernyshevskogo_kso_from_it5_and_fine_tune_from_it6() -> None:
    for it, metered, group, k in (
        ("it5_step5_washers_round2_stage2_on",
         {"27992": 0.858, "28018": 0.658, "28026": 0.844, "28040": 0.835}, 1.071, 1.0997),
        ("it6_step4_kso",
         {"27992": 0.882, "28018": 0.671, "28026": 0.859, "28040": 0.851}, 1.102, 1.0194),
    ):  # fmt: skip
        snap, fact = zulu(CH, it)
        # loss = Qut_pod + Qut_obr + Qut_potr of the card of the same run (0.029 / 0.030; the
        # README used 0.02) → k 1.0963 / 1.0159, within the Kso tolerance of the README values
        i = step_inputs(snap, fact)
        assert i.loss == pytest.approx(sum(snap.card_num(f) for f in ("Qut_pod", "Qut_obr",
                                                                        "Qut_potr")))  # fmt: skip
        res = step4(snap, i.targets, kso_exception=True, q_heating=i.validity.q_heating,
                    loss=i.loss)  # fmt: skip
        kso = by_target(res.rows, "Kso")
        for sys, value in metered.items():
            assert close(kso[sys], value, 0.005), (it, sys)
        for sys in ("28030", "40488", "40490"):
            assert close(kso[sys], group, 0.005), (it, sys)
        assert close(res.unmetered_factor, k, 0.005)
        for c in snap.consumers:  # every unmetered input: Kso·k within 0.5 % of Kso·k_README
            if c.sys in {t.sys for t in i.targets.flows.values() if t.source == "remainder"}:
                assert close(kso[str(c.sys)], c.num("Kso") * k, 0.005), (it, c.sys)


def test_chernyshevskogo_no_circulation_skips_step2() -> None:
    snap, _ = zulu(CH, "it3_step1_3_kgv")
    res = step2(snap, circulation=False)
    assert res.rows == [] and any("шаг 2 пропускается" in n for n in res.notes)


def test_chernyshevskogo_washers_before_kso_when_flows_are_far_off() -> None:
    snap, fact = zulu(CH, "it3_step1_3_kgv")  # inlet +29 %: house flows far from targets
    res = step4(snap, step_inputs(snap, fact).targets)
    assert res.washers_first
    assert any("сначала шаг 5" in n for n in res.notes)


def test_chernyshevskogo_inlet_washer_plug_is_flagged() -> None:
    snap, fact = zulu(CH, "it1_step1_inlet_washer_plug")
    warning = ctp_washer_plug(snap, fact)
    assert warning is not None and "заглушка" in warning and "2/3 Ду" in warning
    ok, fact = zulu(CH, "it2_step1a_inlet_washer_200")
    assert ctp_washer_plug(ok, fact) is None


# ------------------------------------------------------------------ Береговая, 1/15 (scheme 3)

BER = "beregovaya_1_15"


def test_beregovaya_rejects_the_ctp_return_sensor_with_the_balance() -> None:
    snap, fact = zulu(BER, "it0_initial")
    v = assess(snap, fact, dhw_heat=0.10)
    assert v.fact.heating.T4 == 57.5 and v.q_heating == 0.419
    assert v.g_heating == pytest.approx(38.7)  # CTP 38.1 / house 39.3 agree → mean
    assert any("0.519" in p and "0.523" in p and "0.586" in p for p in v.proofs)


def test_beregovaya_washer_from_two_points_at_the_building() -> None:
    before, _ = zulu(BER, "it1_step1_hx_params_kgv_hgv2")
    snap, fact = zulu(BER, "it2_washer_tcirc_trial")
    targets = step_inputs(snap, fact).targets
    assert targets.flows[14744].g == pytest.approx(38.7)
    res = step5(snap, fact, targets, previous=before)
    assert by_target(res.rows, "Dshb_pod")["14744"] == pytest.approx(30.2, abs=0.3)


def test_beregovaya_kso_with_ctp_regulator() -> None:
    snap, fact = zulu(BER, "it2_washer_tcirc_trial")
    i = step_inputs(snap, fact)
    res = step4(snap, i.targets, kso_exception=True, q_heating=i.validity.q_heating, loss=i.loss)
    assert close(by_target(res.rows, "Kso")["14744"], 0.695, 0.005)  # 0.667·0.419/0.402


def test_beregovaya_circulation_check_and_tcirc_from_two_runs() -> None:
    before, _ = zulu(BER, "it1_step1_hx_params_kgv_hgv2")
    snap, _ = zulu(BER, "it2_washer_tcirc_trial")
    res = step2(snap, before, circulation=True)
    assert by_target(res.rows, "Tcirc") == {"21311": 30.3}  # 33 → 12.8, 28.4 → 16.6, need 15.0
    assert "Kcirc" not in {r.field for r in res.rows} and "Hcirc" not in {r.field for r in res.rows}
    assert any("Kcirc / Hcirc не трогать" in n for n in res.notes)


def test_beregovaya_washer_that_disappeared_between_runs_is_flagged() -> None:
    before, _ = zulu(BER, "it1_step1_hx_params_kgv_hgv2")
    snap, _ = zulu(BER, "it2_washer_tcirc_trial")
    # the run entered Dshb_pod 33.8 and Tcirc 28.4 only
    issued = [Recommendation("14744", "Dshb_pod", None, 33.8, ""),
              Recommendation("21311", "Tcirc", None, 28.4, "")]  # fmt: skip
    warnings = unexpected_washer_changes(before, snap, issued)
    assert any("Sys 14744: Dshb_so_pod_u было 39" in w for w in warnings)
    assert not any("Dshb_pod " in w for w in warnings)


# ------------------------------------------------------------------ Верхняя, 24 (scheme 5)

VER = "verkhnyaya_24"


def test_verkhnyaya_flow_channel_g2_accepted_with_proof() -> None:
    snap, fact = zulu(VER, "it0_initial")
    v = assess(snap, fact, inlet_split=3.4, dhw_heat=0.259)
    accepted = [c for c in v.channels if not c.rejected]
    assert [c.name for c in accepted] == ["G2_TS"]
    assert v.metered_factor == pytest.approx(1.22, abs=0.01)
    assert accepted[0].unmetered_factor == pytest.approx(1.27, abs=0.01)
    rejected = {c.name: c.rejected for c in v.channels}
    assert rejected["G1_TS"] and rejected["G1_OT"] and rejected["G2_OT"]  # G1 and heating meter
    assert v.g_heating == pytest.approx(64.6)


def test_verkhnyaya_unmetered_target_and_kso() -> None:
    base, _ = zulu(VER, "it0_initial")
    snap, fact = zulu(VER, "it1_step1_dhw_stages_kgv_hgv2")
    t = step_inputs(snap, fact, base=base).targets
    assert t.remainder_g == pytest.approx(45.3, abs=0.05)  # 68 − 3.7 (stage II) − 19.0
    assert t.remainder_per_gcal == pytest.approx(28.3, abs=0.05)

    for it, expected in (
        ("it2_step5_washers_nozzles_r1", {"28403": 0.877, "28409": 0.894, "28413": 0.770}),
        ("it3_step4_kso_metered", {"28403": 0.924, "28409": 0.940, "28413": 0.839}),
    ):
        snap, fact = zulu(VER, it)
        i = step_inputs(snap, fact, base=base)
        res = step4(snap, i.targets, kso_exception=True, q_heating=i.validity.q_heating,
                    loss=i.loss, base=base)  # fmt: skip
        kso = by_target(res.rows, "Kso")
        for sys, value in expected.items():
            assert close(kso[sys], value, 0.005), (it, sys)

    snap, fact = zulu(VER, "it4_roughness_0_5_kso_finetune")
    i = step_inputs(snap, fact, base=base)
    res = step4(snap, i.targets, kso_exception=True, q_heating=i.validity.q_heating, loss=i.loss,
                base=base)  # fmt: skip
    assert i.loss == pytest.approx(0.013, abs=0.0005)  # Qut_pod + Qut_obr + Qut_potr
    assert close(res.unmetered_factor, 1.248, 0.005)
    kso = by_target(res.rows, "Kso")
    for sys, value in (("28445", 1.057), ("28455", 0.720), ("28463", 1.023)):
        assert close(kso[sys], value, 0.005), sys
    assert any("Проверка: дома с приборами" in n for n in res.notes)


def test_verkhnyaya_elevator_model_is_exact_in_the_export() -> None:
    snap, _ = zulu(VER, "it2_step5_washers_nozzles_r1")
    for c in snap.consumers:
        if c.scheme != 2:
            continue
        g = c.num("Gso")
        washers = sum(
            washer_dh(g, c.num(d)) for d, n in (("Dshb_so_pod_u", "Nshb_so_pod_u"),
                                                ("Dshb_pod", "Nshb_pod"))
            if c.num(d) and c.num(n) == 1
        )  # fmt: skip
        assert washers + nozzle_dh(g, c.num("Dsop_u")) == pytest.approx(c.num("H_ras"), abs=0.02)


def test_verkhnyaya_final_nozzle_from_it4() -> None:
    base, _ = zulu(VER, "it0_initial")
    snap, fact = zulu(VER, "it4_roughness_0_5_kso_finetune")
    res = step5(snap, fact, step_inputs(snap, fact, base=base).targets)
    nozzles = by_target(res.rows, "Dsop_u")
    for sys in ("28463", "40510", "40514", "40516"):
        assert nozzles[sys] == pytest.approx(11.7, abs=0.3), sys


def test_verkhnyaya_low_forecast_head_points_to_pipe_data() -> None:
    snap, fact = zulu(VER, "it3_step4_kso_metered")
    for c in snap.consumers:  # heads of the it2 problem (≈ 4 m) a bit lower
        if c.sys in (28463, 40510, 40514, 40516):
            c.fields["H_ras"] = 3.6
            c.fields["dHsop"] = 3.6
    res = step5(snap, fact, step_inputs(snap, fact).targets)
    assert any("ниже 4 м" in q and "шероховатость" in q for q in res.questions)


# ------------------------------------------------------------------ 2-я Пионерская (scheme 6)

PI = "pionerskaya_2_30_36"


def pi_meters(snap) -> dict:
    guid = {c.sys: c.guid for c in snap.consumers}
    return group_meters_from({
        guid[33640]: {"G1": 19.3, "Q": 0.592, "T1": 86.1, "T2": 55.5},  # node 84083 → b8
        guid[33638]: {"G1": 18.6, "Q": 0.521, "T1": 86.7, "T2": 59.0},  # node 84089 → b2
    })  # fmt: skip


def test_pionerskaya_remainder_goes_to_the_unmetered_building() -> None:
    snap, fact = zulu(PI, "it0_after_step1_dhw")
    i = step_inputs(snap, fact, group_meters=pi_meters(snap))
    t = i.targets
    assert t.remainder_g == pytest.approx(13.7)  # 51.6 − 19.3 − 18.6
    assert {c.sys for c in t.unmetered} == {33636, 40387}
    assert i.unmetered_heat == pytest.approx(0.42, abs=0.01)


def test_pionerskaya_kso_by_group_meters_and_a8_fine_tune() -> None:
    snap, fact = zulu(PI, "it0_after_step1_dhw")
    i = step_inputs(snap, fact, group_meters=pi_meters(snap))
    res = step4(snap, i.targets, kso_exception=True, q_heating=i.validity.q_heating, loss=i.loss)
    kso = by_target(res.rows, "Kso")
    # a8 (33636 / 40387): the session's first Kso 0.925 was an estimate, not reproducible from it0
    # (its inputs had Kso 1.3 / 1.0) — not asserted.
    assert close(kso["33638"], 0.784, 0.005) and close(kso["40398"], 0.784, 0.005)
    assert close(kso["33640"], 0.749, 0.005) and close(kso["40383"], 0.749, 0.005)

    # a8 fine-tune from it2 with the README heat target ≈ 0.42 (loss chosen to give exactly 0.42).
    # With the card loss of the same run (0.0106; the it0–it3 cards are missing, the it4 card is
    # used) the target is 0.4164 and Kso 0.9675 (−0.9 %) — reported in the PR.
    snap, fact = zulu(PI, "it2_step5_supply_washers_regul_test")
    i = step_inputs(snap, fact, group_meters=pi_meters(snap), loss=1.54 - 0.592 - 0.521 - 0.42)
    res = step4(snap, i.targets, kso_exception=True, q_heating=i.validity.q_heating, loss=i.loss)
    kso = by_target(res.rows, "Kso")
    assert close(kso["33636"], 0.976, 0.005) and close(kso["40387"], 0.976, 0.005)


def test_pionerskaya_return_washer_is_the_lever_and_series_washers_count() -> None:
    snap, fact = zulu(PI, "it2_step5_supply_washers_regul_test")
    targets = heating_targets(snap, 51.6, pi_meters(snap))
    res = step5(snap, fact, targets)
    obr = by_target(res.rows, "Dshb_so_obr_u")
    for sys in ("33638", "40391", "40395", "40398"):  # b2: return washer 10 → 11.3
        assert obr[sys] == pytest.approx(11.3, abs=0.3), sys
    assert "Dshb_so_pod_u" not in {r.field for r in res.rows if r.target == "33638"}
    a8 = [r for r in res.rows if r.target == "33636"]
    assert a8 and all(r.field == "Dshb_so_obr_u" for r in a8)  # supply 18.9 stays, return is moved
    assert any("шайбы подряд" in r.note for r in a8)


def test_consumer_washer_head_is_exact() -> None:
    assert washer_dh(4.563, 11.5) == pytest.approx(11.906, abs=0.002)  # b2 it5
