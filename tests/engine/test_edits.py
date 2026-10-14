"""Manual consumer fact edits and editable multi-input shares."""

import json

import pytest

from app.engine.criteria import criteria_step5
from app.engine.edits import ConsumerEdit, apply_edits, edited_cells
from app.engine.legacy import parse_legacy_export
from app.engine.meters import meter_checks, meter_for
from app.engine.step4 import step4
from app.engine.step5 import step5

from .conftest import imported, raw


def test_override_changes_the_meter_value() -> None:
    snap = apply_edits(
        imported("it0_initial").snapshot, {33525: ConsumerEdit(overrides={"G1_OT": 12.0})}
    )
    assert meter_for(snap.consumer(33525)).G1 == 12.0
    # the original snapshot is not modified
    assert meter_for(imported("it0_initial").snapshot.consumer(33525)).G1 == 11


def test_override_can_clear_a_value() -> None:
    snap = apply_edits(
        imported("it0_initial").snapshot, {33525: ConsumerEdit(overrides={"Q_OT": None})}
    )
    assert meter_for(snap.consumer(33525)).Q is None


def test_chosen_block_is_used() -> None:
    snap = apply_edits(imported("it0_initial").snapshot, {33525: ConsumerEdit(block="TS")})
    # 33525 has no _TS values → no usable meter
    assert meter_for(snap.consumer(33525)) is None

    snap = apply_edits(imported("it0_initial").snapshot, {33563: ConsumerEdit(block="TS")})
    m = meter_for(snap.consumer(33563))
    assert m.block == "TS" and m.G1 == 37.3


def test_edited_cells_are_reported() -> None:
    edits = {33525: ConsumerEdit(block="OT", overrides={"G1_OT": 12.0}, distrust=False)}
    assert edited_cells(edits) == {(33525, "G1_OT"), (33525, "block")}


def test_distrusted_meter_is_excluded_from_criteria(fact) -> None:
    snap = imported("it6_step4_kso").snapshot
    before = {c.key: c.passed for c in criteria_step5(snap, fact)}
    assert before["Gso:33523"] is False  # +7.9 %

    edited = apply_edits(snap, {33523: ConsumerEdit(distrust=True)})
    after = {c.key for c in criteria_step5(edited, fact)}
    assert "Gso:33523" not in after
    assert "Q_sum:33523" not in after


def test_distrusted_meter_gives_no_recommendations(fact) -> None:
    edited = apply_edits(imported("it6_step4_kso").snapshot, {33523: ConsumerEdit(distrust=True)})
    assert "33523" not in {r.target for r in step5(edited, fact).rows}
    assert "33523" not in {r.target for r in step4(edited, kso_exception=True).rows}
    assert any("не доверять" in n for n in step5(edited, fact).notes)


def test_distrusted_meter_is_left_out_of_the_balance(fact) -> None:
    snap = imported("it0_initial").snapshot
    edited = apply_edits(snap, {33563: ConsumerEdit(distrust=True)})
    before = {c.no: c for c in meter_checks(fact, snap.consumers)}[5].values["sum_heating_G1"]
    after = {c.no: c for c in meter_checks(fact, edited.consumers)}[5].values["sum_heating_G1"]
    assert before - after == pytest.approx(37.3)


def multi_input_snapshot():
    """it6 with 33531 and 33535 rebuilt as two inputs of one house (same GUID, one meter)."""
    data = json.loads(json.dumps(raw("it6_step4_kso")))
    rows = {r["Sys"]: r for r in data["дома"]}
    a, b = rows[33531], rows[33535]
    b["GUID"] = a["GUID"]
    for k in ("G1_OT", "G2_OT", "T1_OT", "T2_OT", "Q_OT"):
        b[k] = a[k] = {"G1_OT": 34.1, "G2_OT": 34.0, "T1_OT": 78.0, "T2_OT": 55.8, "Q_OT": 0.761}[k]
    return parse_legacy_export(data).snapshot


def test_multi_input_house_uses_split_meter_in_steps(fact) -> None:
    snap = multi_input_snapshot()
    # default split by Qo_r: 0.691158 / (0.691158 + 0.805581) = 46.2 % → 15.75 t/h for 33531
    res = step4(snap, kso_exception=True)
    kso = {r.target: r.enter for r in res.rows}
    share = 0.691158 / (0.691158 + 0.805581)
    q_31 = 0.761 * share
    assert kso["33531"] == pytest.approx(round(0.751 * q_31 / 0.3646, 3), abs=1e-3)


def test_multi_input_shares_can_be_edited(fact) -> None:
    snap = multi_input_snapshot()
    guid = snap.consumer(33531).guid
    shares = {f"{guid}:heating": {33531: 0.5, 33535: 0.5}}
    crit = {c.key: c for c in criteria_step5(snap, fact, shares=shares)}
    assert crit["Gso:33531"].fact == pytest.approx(34.1 * 0.5)
    res = step4(snap, kso_exception=True, shares=shares)
    kso = {r.target: r.enter for r in res.rows}
    assert kso["33531"] == pytest.approx(round(0.751 * (0.761 * 0.5) / 0.3646, 3), abs=1e-3)
