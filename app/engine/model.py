"""Engine data records. Zulu field names are used verbatim."""

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from app.engine.units import PressureUnit

CTP_TARGET = "ЦТП"

# Manual edits are applied as these extra consumer fields (see app/engine/edits.py).
BLOCK_FIELD = "_meter_block"  # meter block chosen by the user: "OT", "TS", "GVS", "SV"
DISTRUST_FIELD = "_distrust"  # «не доверять прибору»


@dataclass(frozen=True)
class InletFact:
    """Inlet of the CTP (network side)."""

    G1: float | None = None
    G2: float | None = None
    T1: float | None = None
    T2: float | None = None
    P1: float | None = None
    P2: float | None = None
    Q: float | None = None


@dataclass(frozen=True)
class HeatingFact:
    """Heating after the CTP: G3 supply, G4 return."""

    G3: float | None = None
    G4: float | None = None
    T3: float | None = None
    T4: float | None = None
    P3: float | None = None
    P4: float | None = None
    Q: float | None = None


@dataclass(frozen=True)
class DhwFact:
    """DHW at the CTP: Gp supply (Gп), Gc circulation (Gц)."""

    Gp: float | None = None
    Gc: float | None = None
    Tgv: float | None = None
    Tc: float | None = None
    Pp: float | None = None
    Pc: float | None = None
    Q: float | None = None


@dataclass(frozen=True)
class VentFact:
    """Ventilation at the CTP (`*_SV` block of the card). Stored, not checked yet."""

    G1: float | None = None
    G2: float | None = None
    T1: float | None = None
    T2: float | None = None
    P1: float | None = None
    P2: float | None = None
    Q: float | None = None


@dataclass(frozen=True)
class Mode:
    tnv: float | None = None  # outdoor temperature of the measurement
    t_source: float | None = None  # supply temperature at the source
    thv: float = 5.0  # cold water temperature
    data_type: Literal["day", "hour"] = "day"
    pressure_unit: PressureUnit = PressureUnit.M_WATER  # unit of the fact form only


@dataclass(frozen=True)
class CtpFact:
    """Manual CTP meter facts; a block is None when there is no meter («нет прибора»)."""

    inlet: InletFact | None
    heating: HeatingFact | None
    dhw: DhwFact | None
    mode: Mode = field(default_factory=Mode)
    vent: VentFact | None = None


@dataclass
class Consumer:
    sys: int
    guid: str | None
    scheme: int
    fields: dict[str, Any]

    def get(self, name: str) -> Any:
        return self.fields.get(name)

    def num(self, name: str) -> float | None:
        v = self.fields.get(name)
        return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


@dataclass
class Snapshot:
    """One verification run exported from Zulu: CTP card and consumers."""

    ctp_name: str
    card: dict[str, Any]
    consumers: list[Consumer]
    measured_on: date | None = None
    tnv: float | None = None
    warnings: list[str] = field(default_factory=list)  # import warnings shown on the step page

    def consumer(self, sys: int) -> Consumer:
        for c in self.consumers:
            if c.sys == sys:
                return c
        raise KeyError(sys)

    def card_num(self, name: str) -> float | None:
        v = self.card.get(name)
        return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


@dataclass(frozen=True)
class Recommendation:
    """One row of «объект · поле · сейчас · ввести»."""

    target: str  # CTP_TARGET or the consumer Sys as text
    field: str
    current: Any
    enter: Any  # None means «очистить»
    reason: str
    note: str = ""


@dataclass
class StepResult:
    step: str
    rows: list[Recommendation] = field(default_factory=list)
    do_not_touch: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Criterion:
    key: str  # e.g. "Gsum_pod" or "Gso:33523"
    title: str
    model: float | None
    fact: float | None
    deviation: float | None  # % or °C, see unit
    limit: float
    unit: Literal["%", "°C", ""]
    passed: bool
    note: str = ""  # e.g. «первый контур / прибор» when a temperature is judged by ΔT
