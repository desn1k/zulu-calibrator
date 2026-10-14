"""Units. All pressures in the engine and in Zulu are metres of water column (м вод. ст.)."""

from enum import StrEnum


class PressureUnit(StrEnum):
    M_WATER = "m"  # м вод. ст. (default)
    KGF_CM2 = "kgf_cm2"  # кгс/см², 1 кгс/см² = 10 м вод. ст.


def pressure_to_m(value: float | None, unit: PressureUnit) -> float | None:
    """Convert a pressure from the CTP fact form to metres of water column."""
    if value is None:
        return None
    if unit is PressureUnit.KGF_CM2:
        return value * 10.0
    return value
