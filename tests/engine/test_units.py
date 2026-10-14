import pytest

from app.engine.units import PressureUnit, pressure_to_m


def test_metres_are_kept() -> None:
    assert pressure_to_m(54.8, PressureUnit.M_WATER) == 54.8


def test_kgf_cm2_is_times_ten() -> None:
    assert pressure_to_m(5.48, PressureUnit.KGF_CM2) == pytest.approx(54.8)


def test_missing_value_stays_missing() -> None:
    assert pressure_to_m(None, PressureUnit.KGF_CM2) is None
