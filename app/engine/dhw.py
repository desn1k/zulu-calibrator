"""DHW at the CTP: which meter is the target, and the test parameters of the DHW heat exchangers
for the scheme families calibrated so far.

docs/algorithm.md: «Шаг 1», «ГВС ЦТП — по столбцам» (parallel, 2-st. mixed, 2-st. sequential),
examples Чернышевского (scheme 12), Береговая (3), Верхняя (5), Пионерская (6).
"""

import math
from dataclasses import dataclass, field
from typing import Literal

from app.engine import config
from app.engine.meters import consumer_kind, meter_for, pct
from app.engine.model import Consumer, CtpFact

Source = Literal["houses", "ctp"]


@dataclass(frozen=True)
class HousesDhw:
    draw_off: float  # Σ (G1 − G2)
    supply: float  # Σ G1
    circulation: float  # Σ G2 of objects with circulation
    circulation_t: float | None  # flow-weighted T2 of the circulating objects
    heat: float | None  # Σ Q_GVS
    count: int


def houses_dhw(consumers: list[Consumer]) -> HousesDhw:
    """DHW house meters (a multi-input building counts once)."""
    seen: set[str] = set()
    draw = supply = circ = circ_t = heat = 0.0
    has_heat, n = False, 0
    for c in consumers:
        if consumer_kind(c.scheme) != "dhw":
            continue
        m = meter_for(c)
        if m is None or m.G1 is None:
            continue
        if c.guid:
            if c.guid in seen:
                continue
            seen.add(c.guid)
        n += 1
        draw += m.draw_off or 0.0
        supply += m.G1
        if m.G2 and m.T2 is not None:
            circ += m.G2
            circ_t += m.G2 * m.T2
        if m.Q is not None:
            heat += m.Q
            has_heat = True
    return HousesDhw(
        draw_off=draw, supply=supply, circulation=circ,
        circulation_t=circ_t / circ if circ else None, heat=heat if has_heat else None, count=n,
    )  # fmt: skip


def unmetered_supply(
    consumers: list[Consumer], ctp_supply: float | None, houses: HousesDhw
) -> float | None:
    """DHW objects without a meter: the rest of the CTP DHW supply meter (G1 − Σ G1 metered)."""
    has_unmetered = any(
        consumer_kind(c.scheme) == "dhw" and (meter_for(c) is None or meter_for(c).G1 is None)
        for c in consumers
    )
    if not has_unmetered or not ctp_supply:
        return None
    rest = ctp_supply - houses.supply
    return rest if rest > 0 else None


@dataclass(frozen=True)
class DhwTarget:
    """Target of the CTP DHW: draw-off, circulation, supply temperature and heat."""

    source: Source
    draw_off: float | None  # Gр, t/h
    circulation: float  # Gц, t/h (0 = no circulation from the CTP)
    circulation_t: float | None  # Tц
    t_supply: float | None  # Tгв
    heat: float | None  # Qгв, Gcal/h
    reason: str
    notes: tuple[str, ...] = ()

    @property
    def supply(self) -> float | None:  # Gп
        return None if self.draw_off is None else self.draw_off + self.circulation


def ctp_balance_heat(fact: CtpFact) -> float | None:
    """DHW heat by the CTP balance: Q inlet − Q heating."""
    if fact.inlet and fact.heating and fact.inlet.Q is not None and fact.heating.Q is not None:
        return fact.inlet.Q - fact.heating.Q
    return None


def choose_dhw_target(
    fact: CtpFact,
    consumers: list[Consumer],
    circulation: bool | None = None,
) -> DhwTarget:
    """Which DHW meter is the target (check 7, approved rules of 2026-10-15).

    - The CTP DHW meter disagrees with the CTP balance (inlet − heating) by more than the
      tolerance while the building sum agrees → the building sum (G1 − G2) is the target.
    - A CTP DHW meter with only a supply channel overstates the heat when there is circulation
      (it counts circulation water as heated from Tхв) → heat target = draw-off + loop cooling.
    `circulation` is the user's answer «есть ли циркуляция от ЦТП» (None = by the CTP meter).
    """
    dhw, thv = fact.dhw, fact.mode.thv
    houses = houses_dhw(consumers)
    balance = ctp_balance_heat(fact)
    t_supply = dhw.Tgv if dhw and dhw.Tgv is not None else None
    meter_has_circ = bool(dhw and dhw.Gc)
    if circulation is None:
        circulation = meter_has_circ
    notes: list[str] = []

    if dhw and meter_has_circ and dhw.Gp is not None:
        # Full CTP meter: draw-off from the CTP unless the user chose the houses (check 7).
        circ, circ_t = dhw.Gc or 0.0, dhw.Tc
        reason = "прибор ГВС ЦТП (подача и циркуляция)"
    elif circulation:
        circ, circ_t = houses.circulation, houses.circulation_t
        reason = "дома (у прибора ГВС ЦТП нет канала циркуляции)"
    else:
        circ, circ_t = 0.0, None
        reason = "дома: циркуляции от ЦТП нет (Kcirc = 0, шаг 2 пропускается)"

    draw = houses.draw_off if houses.count else None
    rest = unmetered_supply(consumers, dhw.Gp if dhw else None, houses)
    if draw is not None and rest:
        draw += rest
        notes.append(f"ГВС-объекты без прибора: остаток прибора ГВС ЦТП {rest:.1f} т/ч в разбор.")
    heat = None
    if draw is not None and t_supply is not None:
        heat = (draw * (t_supply - thv) + circ * (t_supply - (circ_t or t_supply))) / 1000.0

    meter_q = dhw.Q if dhw else None
    if meter_q is not None and balance:
        meter_dev = pct(meter_q, balance)
        houses_dev = pct(houses.heat, balance) if houses.heat is not None else None
        if (
            abs(meter_dev) > config.TOLERANCE_PCT
            and houses_dev is not None
            and abs(houses_dev) <= config.DHW_HOUSES_AGREE_PCT
        ):
            notes.append(
                f"Прибор ГВС ЦТП {meter_q:.3f} Гкал/ч не сходится с балансом ввод − отопление "
                f"{balance:.3f} ({meter_dev:+.1f} %), сумма домов {houses.heat:.3f} сходится "
                f"({houses_dev:+.1f} %) → цель по домам, прибор ГВС ЦТП — в группу учёта."
            )
    if dhw and not meter_has_circ and circulation and dhw.Q is not None and heat is not None:
        notes.append(
            f"Прибор ГВС ЦТП только с подачей считает циркуляцию как воду, нагретую от "
            f"{thv:g} °C: {dhw.Q:.3f} вместо ≈{heat:.3f} Гкал/ч. Цель по теплу ГВС = разбор + "
            "остывание в кольце."
        )
    return DhwTarget(
        source="houses" if not meter_has_circ else "ctp",
        draw_off=draw if not meter_has_circ else (dhw.Gp - dhw.Gc),
        circulation=circ,
        circulation_t=circ_t,
        t_supply=t_supply,
        heat=heat if not meter_has_circ else (dhw.Q if dhw.Q is not None else heat),
        reason=reason,
        notes=tuple(notes),
    )


@dataclass
class DhwParams:
    """Test parameters to enter (unrounded) and the values the page shows."""

    values: dict[str, float]
    shown: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)


def default_t12_verh(t21_verh: float) -> float:
    """T12_verh ≥ T21_verh + 2, rounded up to 0.1 (same rule as scheme 2)."""
    return -(-round((t21_verh + config.STEP1_T12_VERH_MIN_GAP) * 10, 6) // 1) / 10


def sequential_params(
    fact: CtpFact, target: DhwTarget, t22_niz: float | None, t12_verh: float | None
) -> DhwParams:
    """2-st. sequential DHW with direct heating (scheme 12): all inlet flow passes stage I on the
    return. I st.: T11_niz = Tо (heating return), T12_niz = T2, Q_i_niz = G·(Tо − T2)/1000,
    T21_niz = Tхв, T22_niz = Tхв + 1000·Q_i_niz/Gр but not above Tо − 2 (stage I heats with the
    heating return and cannot heat the water above it). II st.: T21_verh = (Gр·T22_niz + Gц·Tц)/Gп,
    T22_verh = Tгв, Q_i_verh = Gп·(Tгв − T21_verh)/1000, T11_verh = T1, T12_verh free."""
    inlet, heating, thv = fact.inlet, fact.heating, fact.mode.thv
    g, t1, t2, t_o = inlet.G1, inlet.T1, inlet.T2, heating.T4
    gr, gc, tgv = target.draw_off, target.circulation, target.t_supply
    gp = gr + gc
    q_niz = g * (t_o - t2) / 1000.0
    res = DhwParams(values={})
    if t22_niz is None:
        by_heat = thv + 1000.0 * q_niz / gr
        cap = math.floor(t_o - config.STEP1_T22_NIZ_GAP)
        t22_niz = min(by_heat, cap)
        if by_heat > cap:
            res.notes.append(
                f"T22_niz по теплу {by_heat:.1f} °C выше обратки отопления {t_o:g} — I ступень "
                f"выше неё воду не нагреет: T22_niz = {t22_niz:g} (на 2 °C ниже, вниз до целого)."
            )
    t21_verh = (gr * t22_niz + gc * (target.circulation_t or 0.0)) / gp
    q_verh = gp * (tgv - t21_verh) / 1000.0
    if t12_verh is None:
        t12_verh = default_t12_verh(t21_verh)
    res.values = {
        "T11_i_niz": t_o, "T12_i_niz": t2, "T21_i_niz": thv, "T22_i_niz": t22_niz,
        "Q_i_niz": q_niz,
        "T11_i_verh": t1, "T12_i_verh": t12_verh, "T21_i_verh": t21_verh, "T22_i_verh": tgv,
        "Q_i_verh": q_verh,
    }  # fmt: skip
    res.shown = {"Gр": gr, "Gп": gp}
    return res


def stage2_correction(
    q_i_verh: float, q_verh_model: float, g_model: float, tgv: float, t21_verh_model: float
) -> float | None:
    """Scheme 12: Zulu passes ≈ ¼ of the test flow through stage II; tune Q_i_verh by the DHW
    temperature at the CTP outlet: Q_new = Q_i_verh · Q_нужно / Q_verh,
    Q_нужно = G_модели·(Tгв − T21_verh)/1000 with the MODEL flow through stage II (G2_verh) —
    the criterion is the outlet temperature and the next run sees the model flow (approved
    2026-10-15)."""
    if not q_verh_model or q_verh_model <= 0:
        return None
    q_needed = g_model * (tgv - t21_verh_model) / 1000.0
    return q_i_verh * q_needed / q_verh_model


def parallel_params(
    fact: CtpFact,
    target: DhwTarget,
    t_o: float | None,
    independent: bool,
    t4: float | None = None,
) -> DhwParams:
    """Parallel DHW («ГВС ЦТП — по столбцам», parallel): T11_niz = T1, T22_niz = Tгв,
    T21_niz = (Gр·Tхв + Gц·Tц)/Gп, Q_i_niz = Qгв; Gгв = [1000·Qгв − G·(Tо − T2)]/(T1 − Tо),
    T12_niz = T1 − 1000·Qгв/Gгв, Gсо = G − Gгв.

    Independent heating: Tо = T12_i, chosen so that T12_niz ≥ T21_niz + 2 (searched upward from
    T21_i + 4 in 0.5 °C steps); T21_i = T4, T22_i = T3, G1_i = Gсо,
    G2_i = Qсо·1000/(T22_i − T21_i) with Qсо = Gсо·(T1 − Tо)/1000.
    Direct heating: Tо = T4 (heating return). `t4` overrides the CTP heating return (a rejected
    CTP sensor is replaced by the building meter)."""
    inlet, heating, thv = fact.inlet, fact.heating, fact.mode.thv
    g, t1, t2 = inlet.G1, inlet.T1, inlet.T2
    t4 = heating.T4 if t4 is None else t4
    gr, gc, tgv, q_gv = target.draw_off, target.circulation, target.t_supply, target.heat
    gp = gr + gc
    t21_niz = (gr * thv + gc * (target.circulation_t or thv)) / gp
    res = DhwParams(values={})

    def solve(to: float) -> tuple[float, float]:
        g_gv = (1000.0 * q_gv - g * (to - t2)) / (t1 - to)
        return g_gv, (t1 - 1000.0 * q_gv / g_gv) if g_gv > 0 else float("-inf")

    def gap_ok(t12_niz: float) -> bool:
        return t12_niz >= t21_niz + config.STEP1_T12_VERH_MIN_GAP - 1e-9

    if t_o is None:
        t_o = t4 + config.PARALLEL_TO_START_GAP if independent else t4
        if independent:
            for _ in range(200):
                if gap_ok(solve(t_o)[1]):
                    break
                t_o += config.PARALLEL_TO_STEP
    g_gv, t12_niz = solve(t_o)
    g_so = g - g_gv
    if independent:
        t3 = heating.T3
        qso = g_so * (t1 - t_o) / 1000.0
        res.values.update({
            "T11_i": t1, "T12_i": t_o, "T21_i": t4, "T22_i": t3, "G1_i": g_so,
            "G2_i": qso * 1000.0 / (t3 - t4),
        })  # fmt: skip
        res.shown["Qсо"] = qso
    res.shown.update({"Tо": t_o, "Gгв": g_gv, "Gсо": g_so, "Gр": gr, "Gп": gp})
    if not gap_ok(t12_niz):
        res.questions.append(
            f"T12_niz {t12_niz:.1f} < T21_niz + 2 ({t21_niz + 2:.1f}) — сдвинуть Tо."
        )
    res.values.update({
        "T11_i_niz": t1, "T12_i_niz": t12_niz, "T21_i_niz": t21_niz, "T22_i_niz": tgv,
        "Q_i_niz": q_gv,
    })  # fmt: skip
    return res


def mixed_dependent_params(
    fact: CtpFact,
    target: DhwTarget,
    g_inlet: float,
    t22_niz: float,
    t12_verh: float | None,
) -> DhwParams:
    """2-st. mixed DHW with dependent heating (scheme 5): step 1.2 with Tо = T4 instead of T12_i
    and G1_i → Gсо (no heating HX). The split comes from the (valid) inlet flow:
    Gверх = 1000·Q_i_verh/(T1 − T12_verh), Gсо = G − Gверх. T12_verh is free (default 40)."""
    inlet, heating, thv = fact.inlet, fact.heating, fact.mode.thv
    t1 = heating.T3 if heating and heating.T3 is not None else inlet.T1
    gr, gc, tgv = target.draw_off, target.circulation, target.t_supply
    gp = gr + gc
    q_niz = gr * (t22_niz - thv) / 1000.0
    t21_verh = (gr * t22_niz + gc * (target.circulation_t or 0.0)) / gp
    q_verh = gp * (tgv - t21_verh) / 1000.0
    if t12_verh is None:
        t12_verh = config.MIXED_T12_VERH_DEFAULT
    g_verh = 1000.0 * q_verh / (t1 - t12_verh)
    t12_niz = inlet.T2
    t11_niz = t12_niz + 1000.0 * q_niz / g_inlet
    res = DhwParams(values={
        "T11_i_niz": t11_niz, "T12_i_niz": t12_niz, "T21_i_niz": thv, "T22_i_niz": t22_niz,
        "Q_i_niz": q_niz,
        "T11_i_verh": t1, "T12_i_verh": t12_verh, "T21_i_verh": t21_verh, "T22_i_verh": tgv,
        "Q_i_verh": q_verh,
    })  # fmt: skip
    res.shown = {"Gверх": g_verh, "Gсо": g_inlet - g_verh, "Gр": gr, "Gп": gp}
    return res


def hgv2_rows_values(card_h_geo: float | None, fact: CtpFact, dead_end: bool) -> dict[str, float]:
    """Hgv2 of the CTP from the DHW meter pressures (м вод. ст.), like Hnz of the heating:
    with circulation Hgv2_obr = H_geo + P2_GVS, Hgv2_ras = P1_GVS − P2_GVS; dead-end
    Hgv2_obr + Hgv2_ras = H_geo + P1_GVS (Hgv2_ras small, default 2 m)."""
    dhw = fact.dhw
    if card_h_geo is None or dhw is None or dhw.Pp is None:
        return {}
    if not dead_end and dhw.Pc is not None:
        return {"Hgv2_obr": card_h_geo + dhw.Pc, "Hgv2_ras": dhw.Pp - dhw.Pc}
    if dead_end:
        ras = config.DEAD_END_HGV2_RAS
        return {"Hgv2_obr": card_h_geo + dhw.Pp - ras, "Hgv2_ras": ras}
    return {}
