"""Validity of the CTP meters before fitting: which channel is the target, with the proof shown.

docs/algorithm.md: «Входные данные и проверка приборов» (a meter that contradicts the balance is
flagged and is not a target), examples Береговая (CTP return sensor) and Верхняя (flow channel):

- one building behind the CTP and the CTP heating return colder than the building outlet by more
  than 2 °C → the CTP return sensor is rejected, the building meter is the target; the flow target
  is the mean of the CTP and building flowmeters when they agree;
- a CTP flow channel that cannot cover the metered buildings is rejected; the accepted channel is
  the one that gives the unmetered buildings the same load factor (fact / design at Tnv) as the
  metered ones.
"""

from dataclasses import dataclass, field, replace

from app.engine import config
from app.engine.grouping import group_consumers
from app.engine.model import CtpFact, Snapshot
from app.engine.targets import group_meter, heating_inputs, kso_qo


@dataclass(frozen=True)
class Channel:
    name: str  # e.g. "G2_TS"
    title: str
    g_heating: float  # heating flow this channel implies, t/h
    q_heating: float | None  # heat of the heating by this channel, Gcal/h
    unmetered_factor: float | None
    rejected: str = ""  # reason, empty when accepted


@dataclass
class Validity:
    fact: CtpFact  # the fact with rejected sensors replaced
    g_heating: float | None  # CTP heating flow the house targets close to
    q_heating: float | None  # heat of the heating the Kso factors close to
    proofs: list[str] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)
    metered_factor: float | None = None
    single_building: bool = False


def design_factor(tnv: float | None, tvso: float, tnv_r: float | None) -> float | None:
    """Share of the design load at the measurement outdoor temperature: (Tв − Tнв)/(Tв − Tнв_р)."""
    if tnv is None or tnv_r is None or tvso == tnv_r:
        return None
    return (tvso - tnv) / (tvso - tnv_r)


def heating_q(g: float, fact: CtpFact) -> float | None:
    h = fact.heating
    if h is None or h.T3 is None or h.T4 is None:
        return None
    return g * (h.T3 - h.T4) / 1000.0


def default_q_heating(fact: CtpFact) -> float | None:
    """Heat of the CTP heating: the meter Q, or G·ΔT when the meter Q is off (check 1)."""
    h = fact.heating
    if h is None:
        return None
    by_dt = heating_q(h.G3, fact) if h.G3 is not None else None
    if h.Q is None:
        return by_dt
    if by_dt and abs(h.Q / by_dt - 1.0) * 100.0 > config.CHECK_HEAT_CLOSE_PCT:
        return by_dt
    return h.Q


def assess(
    snap: Snapshot,
    fact: CtpFact,
    inlet_split: float = 0.0,
    dhw_heat: float | None = None,
    base_kso: dict[int, float] | None = None,
) -> Validity:
    """`inlet_split` — flow of the inlet that does not go to the heating (stage II of a mixed
    scheme, DHW HX of a parallel one) for the inlet channels; `dhw_heat` — DHW heat target;
    `base_kso` — Kso before calibration (first export): the design loads of the channel check."""
    h = fact.heating
    v = Validity(fact=fact, g_heating=h.G3 if h else None, q_heating=default_q_heating(fact))
    groups = [g for g in group_consumers(heating_inputs(snap.consumers))]
    v.single_building = len(groups) == 1

    if v.single_building and h is not None:
        meter, _ = group_meter(groups[0], None)
        rejected = (
            meter is not None
            and meter.T2 is not None
            and h.T4 is not None
            and meter.T2 - h.T4 > config.CTP_RETURN_SENSOR_GAP_C
        )
        if rejected:
            v.fact = replace(fact, heating=replace(h, T4=meter.T2, Q=meter.Q))
            v.q_heating = meter.Q
            inlet = fact.inlet
            inlet_q = (
                inlet.G1 * (inlet.T1 - inlet.T2) / 1000.0
                if inlet and None not in (inlet.G1, inlet.T1, inlet.T2)
                else None
            )
            proof = (
                f"Один дом за ЦТП, а обратка на приборе ЦТП холоднее, чем выходит из дома "
                f"({h.T4:g} против {meter.T2:g} °C) → датчик T2 ЦТП не берём, цель по дому."
            )
            if inlet_q is not None and meter.Q is not None:
                total = meter.Q + (dhw_heat or 0.0)
                proof += (
                    f" Баланс: отопление дома {meter.Q:.3f} + ГВС {dhw_heat or 0.0:.3f} = "
                    f"{total:.3f} ≈ ввод G·ΔT {inlet_q:.3f}"
                )
                if h.Q is not None:
                    proof += f", а прибор отопления ЦТП {h.Q:.3f} больше ввода"
                proof += "."
            v.proofs.append(proof)
        if meter is not None and meter.G1 and h.G3:
            if abs(meter.G1 / h.G3 - 1.0) * 100.0 <= config.TOLERANCE_PCT:
                v.g_heating = (meter.G1 + h.G3) / 2.0
                v.proofs.append(
                    f"Расход отопления: ЦТП {h.G3:g} и дом {meter.G1:g} т/ч сходятся — цель "
                    f"{v.g_heating:.1f} т/ч (среднее)."
                )
            else:
                v.g_heating = meter.G1
        return v

    choose_channel(snap, v, fact, inlet_split, dhw_heat, base_kso or {})
    return v


def choose_channel(
    snap: Snapshot,
    v: Validity,
    fact: CtpFact,
    inlet_split: float,
    dhw_heat: float | None,
    base_kso: dict[int, float],
) -> None:
    groups = group_consumers(heating_inputs(snap.consumers))
    tnv = fact.mode.tnv if fact.mode.tnv is not None else snap.tnv
    tnv_r = snap.card_num("Tnv_r")
    metered_q = metered_load = unmetered_load = metered_g = 0.0
    has_unmetered = False
    for g in groups:
        meter, _ = group_meter(g, None)
        load = 0.0
        for c in g.members:
            f = design_factor(tnv, c.num("Tvso_r") or 18.0, tnv_r)
            kso = base_kso.get(c.sys)
            design = (c.num("Qo_r") or 0.0) * kso if kso is not None else kso_qo(c)
            load += design * (f or 0.0)
        if meter is not None and meter.G1 and meter.Q is not None:
            metered_q += meter.Q
            metered_g += meter.G1
            metered_load += load
        else:
            unmetered_load += load
            has_unmetered = True
    if not has_unmetered or not metered_load or not unmetered_load:
        return
    v.metered_factor = metered_q / metered_load

    candidates: list[tuple[str, str, float]] = []
    h, inlet = fact.heating, fact.inlet
    if h is not None:
        for name, value in (("G1_OT", h.G3), ("G2_OT", h.G4)):
            if value:
                candidates.append((name, f"отопление ЦТП {name} {value:g}", value))
    if inlet is not None:
        for name, value in (("G1_TS", inlet.G1), ("G2_TS", inlet.G2)):
            if value:
                g_heat = value - inlet_split
                title = f"ввод {name} {value:g}" + (f" − {inlet_split:.1f}" if inlet_split else "")
                candidates.append((name, title, g_heat))

    for name, title, g_heat in candidates:
        q = heating_q(g_heat, fact)
        rest = None if q is None else q - metered_q
        factor = None if rest is None else rest / unmetered_load
        reason = ""
        if g_heat <= metered_g or (rest is not None and rest <= 0):
            reason = "не покрывает дома с приборами"
        elif (
            factor is not None
            and v.metered_factor
            and abs(factor / v.metered_factor - 1.0) * 100.0 > config.CHANNEL_FACTOR_MAX_DIFF_PCT
        ):
            reason = "дома без приборов получают не тот коэффициент к нагрузке"
        v.channels.append(Channel(name, title, g_heat, q, factor, reason))

    default = next((c for c in v.channels if c.name == "G1_OT"), None)
    if default is not None and not default.rejected:
        return  # the CTP heating meter is consistent — nothing to change
    good = [c for c in v.channels if not c.rejected and c.unmetered_factor is not None]
    if not good:
        v.proofs.append("Ни один канал расхода ЦТП не даёт домам без приборов разумной нагрузки.")
        return
    best = min(good, key=lambda c: abs(c.unmetered_factor / v.metered_factor - 1.0))
    v.g_heating = best.g_heating
    if best.name.endswith("_TS") and inlet is not None:
        inlet_q = (
            (best.g_heating + inlet_split) * (inlet.T1 - inlet.T2) / 1000.0
            if None not in (inlet.T1, inlet.T2)
            else None
        )
        v.q_heating = inlet_q - (dhw_heat or 0.0) if inlet_q is not None else best.q_heating
    else:
        v.q_heating = best.q_heating
    lines = [f"Дома с приборами: факт / расчётная нагрузка при Tнв = ×{v.metered_factor:.2f}."]
    for c in v.channels:
        f = f"×{c.unmetered_factor:.2f}" if c.unmetered_factor is not None else "—"
        verdict = (
            f"отброшен: {c.rejected}" if c.rejected else ("принят" if c is best else "возможен")
        )
        lines.append(
            f"{c.title} → отопление {c.g_heating:.1f} т/ч, дома без приборов {f} — {verdict}."
        )
    v.proofs.append(" ".join(lines))
