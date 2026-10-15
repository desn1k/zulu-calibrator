"""CTP and consumer schemes: heating row × DHW column, and the initial calibration status.

docs/algorithm.md: «Схемы ЦТП — все 41», «Схемы потребителей — все 49», «Сайт» → «Статус схем».
"""

from dataclasses import dataclass
from datetime import date
from typing import Literal

Heating = Literal[
    "independent", "direct", "elevator", "pump_bridge", "pump_supply", "pump_return", "none",
    "regulator",
]  # fmt: skip
Dhw = Literal[
    "none", "parallel", "two_stage_mixed", "two_stage_sequential", "one_stage_sequential",
    "open", "tank", "network",
]  # fmt: skip


@dataclass(frozen=True)
class Scheme:
    n: int
    heating: Heating
    dhw: Dhw


# «Схемы ЦТП — все 41»: rows = heating, columns = DHW.
_CTP_MATRIX: dict[Heating, dict[Dhw, int]] = {
    "independent": {"none": 1, "parallel": 3, "two_stage_mixed": 2, "two_stage_sequential": 15,
                    "one_stage_sequential": 20, "open": 37, "tank": 30},
    "direct": {"parallel": 6, "two_stage_mixed": 5, "two_stage_sequential": 12,
               "one_stage_sequential": 16, "open": 17, "tank": 29},
    "elevator": {"none": 4, "parallel": 11, "two_stage_mixed": 10, "two_stage_sequential": 13,
                 "one_stage_sequential": 18, "open": 36, "tank": 31},
    "pump_bridge": {"none": 7, "parallel": 9, "two_stage_mixed": 8, "two_stage_sequential": 14,
                    "one_stage_sequential": 19, "open": 33, "tank": 32},
    "pump_supply": {"none": 21, "parallel": 23, "two_stage_mixed": 25,
                    "two_stage_sequential": 27, "open": 34, "network": 38},
    "pump_return": {"none": 22, "parallel": 24, "two_stage_mixed": 26,
                    "two_stage_sequential": 28, "open": 35, "network": 39},
}  # fmt: skip

CTP_SCHEMES: dict[int, Scheme] = {
    n: Scheme(n, heating, dhw) for heating, row in _CTP_MATRIX.items() for dhw, n in row.items()
}
CTP_SCHEMES[40] = Scheme(40, "regulator", "none")
CTP_SCHEMES[41] = Scheme(41, "regulator", "none")

# «Схемы потребителей — все 49» (heating row; DHW column where the scheme has one).
_CONSUMER_HEATING: dict[Heating, tuple[int, ...]] = {
    "independent": (1, 3, 8, 10, 14, 16, 20, 22, 31),
    "direct": (4, 28, 32, 33, 35, 45),
    "elevator": (2, 6, 7, 12, 13, 18, 19, 24, 29),
    "pump_bridge": (5, 9, 11, 15, 17, 21, 23, 30, 47),
    "pump_supply": (36, 38, 40, 42),
    "pump_return": (37, 39, 41, 43),
    "none": (25, 26, 27, 34, 46, 48, 49),
}
CONSUMER_HEATING: dict[int, Heating] = {
    n: heating for heating, ns in _CONSUMER_HEATING.items() for n in ns
}


def ctp_scheme(n: int | None) -> Scheme | None:
    return CTP_SCHEMES.get(n) if isinstance(n, int) else None


def consumer_heating(n: int) -> Heating | None:
    return CONSUMER_HEATING.get(n)


def is_elevator(n: int) -> bool:
    return CONSUMER_HEATING.get(n) == "elevator"


# «Статус схем»: initial state. «Calibrated» is set otherwise only by «подтвердить» on a project.
SchemeKind = Literal["ctp", "consumer"]


@dataclass(frozen=True)
class InitialStatus:
    kind: SchemeKind
    n: int
    calibrated_on: date
    project: str


INITIAL_CALIBRATED: tuple[InitialStatus, ...] = (
    InitialStatus("ctp", 2, date(2026, 10, 14), "Огородная, 87"),
    InitialStatus("consumer", 4, date(2026, 10, 14), "Огородная, 87"),
    InitialStatus("consumer", 26, date(2026, 10, 14), "Огородная, 87"),
    InitialStatus("ctp", 12, date(2026, 10, 15), "Чернышевского, 8"),
    InitialStatus("ctp", 3, date(2026, 10, 15), "Береговая, 1/15"),
    InitialStatus("ctp", 5, date(2026, 10, 15), "Верхняя, 24"),
    InitialStatus("ctp", 6, date(2026, 10, 15), "2-я Пионерская, 30/36"),
    InitialStatus("consumer", 2, date(2026, 10, 15), "Верхняя, 24"),
)
