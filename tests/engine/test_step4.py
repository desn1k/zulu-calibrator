"""Step 4: heat of the heating houses, Kso by exception (algorithm «Шаги 4–5»)."""

import pytest

from app.engine.step4 import KSO_EXCEPTION_NOTE
from app.engine.step4 import step4 as step4_engine
from app.engine.targets import heating_targets

from .conftest import by_target, imported


def step4(snap, kso_exception: bool = False):
    return step4_engine(snap, heating_targets(snap, None), kso_exception=kso_exception)


KSO_GOLDEN = {
    "33523": 1.075,
    "33525": 0.849,
    "33531": 0.751,
    "33535": 0.638,
    "33539": 1.018,
    "33563": 0.766,
    "36749": 0.611,
    "36751": 1.365,
}


def test_default_is_variant_a_no_changes_with_deficit_report() -> None:
    res = step4(imported("it5_step3_rollback").snapshot)
    assert res.rows == []
    deficit = {d.target: d.deviation_pct for d in res.heat_report}
    assert len(deficit) == 8
    assert deficit["33523"] == pytest.approx((0.0922 / 0.107 - 1) * 100, abs=0.05)
    assert all(v < 0 for v in deficit.values())


def test_kso_exception_golden_from_it5() -> None:
    res = step4(imported("it5_step3_rollback").snapshot, kso_exception=True)
    assert by_target(res.rows, "Kso") == KSO_GOLDEN
    assert all(r.note == KSO_EXCEPTION_NOTE for r in res.rows)
    assert KSO_EXCEPTION_NOTE == "нагрузка в модели ≠ договорной"


def test_kso_uses_inlet_meter_when_no_heating_meter() -> None:
    res = step4(imported("it5_step3_rollback").snapshot, kso_exception=True)
    [row] = [r for r in res.rows if r.target == "33563"]
    assert "взят ввод" in row.reason


def test_dhw_objects_are_not_part_of_step4() -> None:
    res = step4(imported("it5_step3_rollback").snapshot, kso_exception=True)
    assert "33551" not in {r.target for r in res.rows}
