"""Step 1 golden values of the 2026-10-15 sets (README of each fixture)."""

import pytest

from app.engine.step1 import step1

from .conftest import by_target, zulu


def ctp(res, snap=None) -> dict:
    """Values of the CTP after this step: the row to enter, else what the card already has."""
    rows = {r.field: r.enter for r in res.rows if r.target == "ЦТП"}
    if snap is None:
        return rows
    return {**{k: v for k, v in snap.card.items() if isinstance(v, int | float)}, **rows}


def near(value: float, expected: float, rel: float) -> bool:
    return value == pytest.approx(expected, rel=rel)


# ------------------------------------------------------------------ Чернышевского, 8 (scheme 12)

CH = "chernyshevskogo_8"
CH_KGV = {
    "28108": 0.261, "28116": 0.208, "28124": 0.205, "28134": 0.089, "28154": 0.276,
    "28166": 0.448, "28184": 0.103, "28190": 0.181, "28196": 0.434, "28198": 0.143,
    "28210": 0.272, "28218": 0.335, "28250": 0.260,
}  # fmt: skip


def test_chernyshevskogo_kgv_by_model_flow_from_it2() -> None:
    snap, fact = zulu(CH, "it2_step1a_inlet_washer_200")
    res = step1(snap, fact, circulation=False)  # automatic rule: every object is alive
    kgv = by_target(res.rows, "Kgv")
    assert all("ГВС в модели жива" in r.note for r in res.rows if r.field == "Kgv")
    assert kgv.keys() == CH_KGV.keys()  # all 13 objects (each off by more than 4 %)
    for sys, expected in CH_KGV.items():
        assert near(kgv[sys], expected, 0.01), sys


def test_chernyshevskogo_sequential_stages_from_it0() -> None:
    snap, fact = zulu(CH, "it0_initial")
    res = step1(snap, fact, t12_verh=60, circulation=False)
    v = ctp(res, snap)
    assert (v["T11_i_niz"], v["T12_i_niz"], v["T21_i_niz"], v["T22_i_niz"]) == (58.2, 53, 5, 56)
    assert v["Q_i_niz"] == 0.673  # all inlet flow passes stage I: 129.5·(58.2 − 53)/1000
    assert (v["T11_i_verh"], v["T12_i_verh"], v["T21_i_verh"], v["T22_i_verh"]) == (
        89.2, 60, 56, 65.8,
    )  # fmt: skip
    assert v["Q_i_verh"] == 0.083  # 8.5·(65.8 − 56)/1000
    assert res.dhw_target.draw_off == pytest.approx(8.5)
    assert res.dhw_target.circulation == 0
    assert any("не сходится с балансом" in n and "цель по домам" in n for n in res.notes)


def test_chernyshevskogo_stage2_tuned_by_dhw_temperature() -> None:
    # Q_i_verh_new = Q_i_verh · Q_needed / Q_verh, Q_needed with the MODEL flow through stage II
    # (approved 2026-10-15). From it6: G2_verh 8.675 → 0.385 (README).
    snap, fact = zulu(CH, "it6_step4_kso")
    v = ctp(step1(snap, fact, t12_verh=60, circulation=False))
    assert set(v) == {"Q_i_verh"}  # stage I and stage II temperatures are already right
    assert near(v["Q_i_verh"], 0.385, 0.01)

    # From it5 the session entered 0.31 (computed with the target 8.5 while the cold DHW
    # inflated the model flow to 9.248); the approved rule gives 0.083·9.248·8.7/1000/0.0198.
    snap, fact = zulu(CH, "it5_step5_washers_round2_stage2_on")
    v = ctp(step1(snap, fact, t12_verh=60, circulation=False))
    assert near(v["Q_i_verh"], 0.083 * 9.248 * (65.8 - 57.1) / 1000 / 0.0198, 0.005)

    snap, fact = zulu(CH, "it7_step4_kso_finetune")
    res = step1(snap, fact, t12_verh=60, circulation=False)
    assert "Q_i_verh" not in ctp(res)  # 65.5 vs 65.8 °C: within 1 °C


# ------------------------------------------------------------------ Береговая, 1/15 (scheme 3)

BER = "beregovaya_1_15"


def test_beregovaya_parallel_dhw_and_heating_hx_from_it0() -> None:
    snap, fact = zulu(BER, "it0_initial")
    res = step1(snap, fact)
    v = ctp(res, snap)
    # Tо = 61.5 (T21_i + 4, first step already gives T12_niz ≥ T21_niz + 2)
    assert (v["T12_i"], v["T21_i"], v["G1_i"], v["G2_i"]) == (61.5, 57.5, 16.7, 38.8)
    assert (v["T11_i_niz"], v["T12_i_niz"], v["T21_i_niz"], v["Q_i_niz"]) == (
        86.8, 44.6, 30.6, 0.1,
    )  # fmt: skip
    assert "T22_i_niz" in v and v["T22_i_niz"] == 61.3
    assert v["Hgv2_obr"] == 112.3  # H_geo 27.3 + P2_GVS 85
    assert "Hgv2_ras" not in ctp(res)  # P1 − P2 = 1.8 already
    assert by_target(res.rows, "Kgv") == {"21311": 0.474}  # DHW 23 °C in the model → 1.3
    assert "ГВС в модели не работает" in next(r.note for r in res.rows if r.field == "Kgv")
    assert res.shown["Gгв"] == pytest.approx(2.37, abs=0.005)
    assert any("датчик T2 ЦТП не берём" in n for n in res.notes)


# ------------------------------------------------------------------ Верхняя, 24 (scheme 5)

VER = "verkhnyaya_24"
VER_KGV = {"28435": 0.658, "28441": 0.330, "28443": 0.205, "28474": 0.373, "28478": 0.293,
           "28484": 0.465}  # fmt: skip


def test_verkhnyaya_mixed_dead_end_dhw_from_it0() -> None:
    snap, fact = zulu(VER, "it0_initial")
    res = step1(snap, fact, t22_niz=26)  # automatic rule: alive; Tgv 60 → 62.7 in the same run
    v = ctp(res, snap)
    assert (v["T11_i_niz"], v["T12_i_niz"], v["T21_i_niz"], v["T22_i_niz"]) == (55.6, 54.2, 5, 26)
    assert v["Q_i_niz"] == 0.095
    assert (v["T11_i_verh"], v["T12_i_verh"], v["T21_i_verh"], v["T22_i_verh"]) == (
        89.2, 40, 26, 62.7,
    )  # fmt: skip
    assert v["Q_i_verh"] == 0.165
    assert res.shown["Gверх"] == pytest.approx(3.4, abs=0.05)
    assert v["Tgv"] == 62.7
    assert (v["Hgv2_obr"], v["Hgv2_ras"]) == (108.4, 2)  # sum = H_geo + P1_GVS
    kgv = by_target(res.rows, "Kgv")
    for sys, expected in VER_KGV.items():  # Kgv·G/Ggv × (62.7 − 5)/(60 − 5): Tgv in the same batch
        assert near(kgv[sys], expected, 0.01), sys
    reasons = [r.reason for r in res.rows if r.field == "Kgv"]
    assert all("× (62.7 − 5)/(60 − 5) = 1.0491" in r for r in reasons)


# ------------------------------------------------------------------ 2-я Пионерская (scheme 6)

PI = "pionerskaya_2_30_36"


def test_pionerskaya_dhw_heat_target_and_kgv_from_it0() -> None:
    snap, fact = zulu(PI, "it0_after_step1_dhw")
    res = step1(snap, fact, circulation=True)
    t = res.dhw_target
    assert t.heat == pytest.approx(0.20, abs=0.01)  # draw-off + loop cooling, not 0.308
    assert any("0.308" in n and "остывание в кольце" in n for n in res.notes)
    assert ctp(res)["Q_i_niz"] == pytest.approx(t.heat, abs=0.001)
    assert ctp(res, snap)["T21_i_niz"] == 22.7
    kgv = by_target(res.rows, "Kgv")
    assert kgv == {"33648": 0.294, "33650": 0.461, "33652": 0.278}  # 33648: CTP meter rest 0.9
    # Tgv_t 18–19 °C in the model (junk HX parameters) → formula 1.3 for every object
    assert all("ГВС в модели не работает" in r.note for r in res.rows if r.field == "Kgv")
