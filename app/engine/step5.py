"""Step 5: building washers, washers in series, elevator nozzles, junk washer fields.

docs/algorithm.md: «Шаги 4–5» → «Шаг 5 — шайбы домов», «Две шайбы подряд», «Порядок 4 и 5»
(two H(G) points at the CTP inlet), «Давления второго контура» п. 3 (head at a house when the
flow changes), «Отопление потребителя — Элеватор», examples Чернышевского (washers from scratch,
unmetered targets), Береговая (two H(G) points at the building), Верхняя (elevators),
Пионерская (series washers, the return washer is the usual lever).
"""

from dataclasses import dataclass

from app.engine import config
from app.engine.hydraulics import head_line, house_head, size_washer, washer_d, washer_dh
from app.engine.model import (
    DISTRUST_FIELD,
    Consumer,
    CtpFact,
    Recommendation,
    Snapshot,
    StepResult,
)
from app.engine.schemes import ctp_scheme, is_elevator
from app.engine.step3 import inlet_deviation_pct
from app.engine.targets import FlowTarget, HeatingTargets

STEP5_DO_NOT_TOUCH = ["Kso", "Qo_r", "T1_r / T3_r / T2_r домов", "шайба ввода ЦТП"]
LOW_HEAD_NOTE = (
    "прогноз напора ниже {:g} м — признак ошибки в трубах модели (например, шероховатость выше "
    "0,5 мм), а не повод раздувать сопла"
)

# Washers on the heating path of a consumer: (D field, N field). The inlet washer of the object
# (Dshb_pod) is in series with the heating washers on a heating-only object.
SO_SUPPLY = ("Dshb_so_pod_u", "Nshb_so_pod_u")
SO_RETURN = ("Dshb_so_obr_u", "Nshb_so_obr_u")
INLET = ("Dshb_pod", "Nshb_pod")
WASHERS = (SO_SUPPLY, SO_RETURN, INLET)


def equivalent_diameter(d1: float, d2: float) -> float:
    """d_экв = (d1⁻⁴ + d2⁻⁴)^(−¼)."""
    return (d1**-4 + d2**-4) ** -0.25


def has_value(v) -> bool:
    return v is not None and v != 0


def heating_only(c: Consumer) -> bool:
    """No other system on this object's inlet (open DHW, ventilation) — the washers duplicate."""
    return not (c.num("Qgv_sred") or c.num("Qsv_r"))


def junk_rows(c: Consumer) -> list[Recommendation]:
    """Nshb without a diameter (or a diameter without Nshb) is junk: clear both fields."""
    rows = []
    for d_name, n_name in (INLET, SO_SUPPLY, SO_RETURN):
        d, n = c.get(d_name), c.get(n_name)
        if has_value(d) == has_value(n):
            continue
        reason = f"{n_name} без {d_name} (или наоборот) — мусор, очистить оба поля"
        for name, value in ((d_name, d), (n_name, n)):
            if has_value(value):
                rows.append(Recommendation(str(c.sys), name, value, None, reason))
    return rows


def installed(c: Consumer) -> dict[tuple[str, str], float]:
    """Washers in place (D > 0 and N = 1) on the heating path."""
    out = {}
    for pair in WASHERS:
        if pair == INLET and not heating_only(c):
            continue
        d, n = c.num(pair[0]), c.num(pair[1])
        if d and n == 1:
            out[pair] = d
    return out


def lever(washers: dict[tuple[str, str], float]) -> tuple[str, str]:
    """Which washer to change: the return washer (usual lever when there are washers in series),
    else the inlet washer of the object when it is the only one, else the supply washer."""
    if SO_RETURN in washers:
        return SO_RETURN
    if INLET in washers and SO_SUPPLY not in washers:
        return INLET
    return SO_SUPPLY


@dataclass(frozen=True)
class HeadForecast:
    """Forecast of the head at the houses for the target flow."""

    p_now: float | None = None  # ΔP at the CTP outlet now
    p_new: float | None = None  # forecast ΔP at the target total flow
    g_now: float | None = None
    g_target: float | None = None
    two_points: bool = False
    single_building: bool = False
    note: str = ""

    def head(self, c: Consumer, g_target: float, prev: Consumer | None) -> float:
        h = c.num("H_ras")
        if self.single_building and prev is not None:
            line = head_line(prev.num("Gso") or 0.0, prev.num("H_ras") or 0.0,
                             c.num("Gso") or 0.0, h)  # fmt: skip
            if line is not None:
                return line.at(g_target)
        if self.two_points and self.p_now is not None and self.p_new is not None:
            return house_head(h, self.p_now, self.p_new, self.g_now, self.g_target)
        return h


def outlet_dp(snap: Snapshot) -> float | None:
    hp, ho = snap.card_num("Hout_pod"), snap.card_num("Hout_obr")
    return None if hp is None or ho is None else hp - ho


def head_forecast(
    snap: Snapshot, previous: Snapshot | None, fact: CtpFact, single_building: bool
) -> HeadForecast:
    """«Напор у домов растёт, когда общий расход падает: второй круг считают по двум точкам H(G)
    на вводе ЦТП» — ΔP at the CTP outlet vs the total flow through two runs, then the loss to
    each house scales with the square of the flow («Давления второго контура» п. 3)."""
    if single_building:
        return HeadForecast(single_building=True, note="напор у дома — по двум точкам H(G) дома")
    if previous is None:
        return HeadForecast()
    scheme = ctp_scheme(snap.card.get("N_schem"))
    independent = scheme is not None and scheme.heating == "independent"
    g_key = "Gsum_pod2" if independent else "Gsum_pod"
    g_target = (
        (fact.heating.G3 if fact.heating else None)
        if independent
        else ((fact.inlet.G1 or fact.inlet.G2) if fact.inlet else None)
    )
    g1, g2 = previous.card_num(g_key), snap.card_num(g_key)
    p1, p2 = outlet_dp(previous), outlet_dp(snap)
    if None in (g1, g2, p1, p2, g_target):
        return HeadForecast()
    line = head_line(g1, p1, g2, p2)
    if line is None:
        return HeadForecast()
    p_new = line.at(g_target)
    return HeadForecast(
        p_now=p2, p_new=p_new, g_now=g2, g_target=g_target, two_points=True,
        note=(
            f"Прогноз напора по двум расчётам: ΔP после ЦТП {p1:.2f} м при {g1:.1f} т/ч и "
            f"{p2:.2f} м при {g2:.1f} т/ч → {p_new:.2f} м при {g_target:.1f} т/ч."
        ),
    )  # fmt: skip


def step5(
    snap: Snapshot,
    fact: CtpFact,
    targets: HeatingTargets,
    previous: Snapshot | None = None,
) -> StepResult:
    """`targets` — flow target of every heating input (metered, group, remainder);
    `previous` — the export before (two H(G) points for the head forecast)."""
    res = StepResult(step="5", do_not_touch=list(STEP5_DO_NOT_TOUCH))
    scheme = ctp_scheme(snap.card.get("N_schem"))
    if scheme is None or scheme.heating == "independent":
        # With CTP pumps the house heads are wrong until the inlet is within ±4 % (APPROVED
        # 2026-10-15: Береговая sized the washer at −2.4 %).
        dev = inlet_deviation_pct(snap, fact)
        if dev is None or abs(dev) > config.TOLERANCE_PCT:
            shown = "нет данных" if dev is None else f"{dev:+.1f} %"
            res.notes.append(
                f"Шайбы домов — только после того, как сошёлся ввод ЦТП (шаг 3): G ввода {shown}. "
                "До этого H_ras домов неверный."
            )
            return res
    res.notes.extend(targets.notes)
    single = len({t.members or (t.sys,) for t in targets.flows.values()}) == 1 and all(
        t.source != "remainder" for t in targets.flows.values()
    )
    forecast = head_forecast(snap, previous, fact, single)
    if forecast.note and (forecast.two_points or (forecast.single_building and previous)):
        res.notes.append(forecast.note)
    prev = {c.sys: c for c in previous.consumers} if previous else {}

    low_heads: list[int] = []
    for c in snap.consumers:
        t = targets.flows.get(c.sys)
        if t is None:
            continue
        sys = str(c.sys)
        if c.get(DISTRUST_FIELD):
            res.notes.append(f"Sys {sys}: прибор помечен «не доверять» — пропущен.")
            continue
        if c.num("Regul_G"):
            res.notes.append(
                f"Sys {sys}: есть регулятор (Regul_G = {c.get('Regul_G')}) — пропущен."
            )
            continue
        n_codes = [c.num(n) for _, n in WASHERS]
        if any(n is not None and n < 0 for n in n_codes):
            res.questions.append(f"Sys {sys}: Nshb < 0 (отключение / дроссель по Kv) — проверить.")
            continue
        res.rows.extend(junk_rows(c))
        g_model, h_ras = c.num("Gso"), c.num("H_ras")
        if not g_model or h_ras is None:
            res.questions.append(f"Sys {sys}: нет Gso / H_ras в выгрузке.")
            continue
        h_new = forecast.head(c, t.g, prev.get(c.sys))
        g_pred = predicted_flow(c, h_new)
        off_pct = (g_pred / t.g - 1.0) * 100.0
        src = {"meter": "прибор", "group": "прибор дома, по расходу модели",
               "remainder": "остаток ЦТП по Kso·Qo_r"}[t.source]  # fmt: skip
        reason = f"Gso {g_model:g} против цели {t.g:.2f} т/ч ({src}, {off_pct:+.1f} %)"
        if abs(g_pred - g_model) > 1e-9:
            reason += f"; при прогнозе напора {h_new:.2f} м расход станет {g_pred:.2f} т/ч"
        if abs(off_pct) <= config.WASHER_CHANGE_PCT:
            series_rows(res, c)
            continue
        if h_new < config.MIN_FORECAST_HEAD_M:
            low_heads.append(c.sys)
        if is_elevator(c.scheme):
            elevator_rows(res, c, t, h_new, reason)
        else:
            washer_rows(res, c, t, h_new, reason)

    if low_heads:
        res.questions.append(
            f"Sys {', '.join(map(str, low_heads))}: "
            + LOW_HEAD_NOTE.format(config.MIN_FORECAST_HEAD_M)
            + "."
        )
    res.notes.append(
        "Шайба с малым dHshb_so_pod (< 2 м) резко реагирует на диаметр; меняем только при "
        "|Gм/Gф − 1| > 2 %."
    )
    return res


def predicted_flow(c: Consumer, h_new: float) -> float:
    """Flow of the house at the forecast head with its washers (and nozzle) as they are:
    H = (S + Σ 1/(d/10)⁴ [+ (9.6/dс)⁴])·G² with S from the last run."""
    g, h = c.num("Gso"), c.num("H_ras")
    if not g or not h or h_new == h:
        return g
    resistance = h / g**2  # all of it: house, washers, nozzle
    return (h_new / resistance) ** 0.5 if h_new > 0 else g


def series_rows(res: StepResult, c: Consumer) -> None:
    """Flow within ±2 %: two washers in series on a heating-only object (inlet + SO supply) →
    one on the SO with the equivalent diameter."""
    sys = str(c.sys)
    d_so, n_so = c.num("Dshb_so_pod_u"), c.num("Nshb_so_pod_u")
    d_in, n_in = c.num("Dshb_pod"), c.num("Nshb_pod")
    if d_so and n_so == 1 and d_in and n_in == 1 and heating_only(c):
        d_eq = round(equivalent_diameter(d_so, d_in), config.ROUND_D)
        why = f"Две шайбы подряд (Ø{d_so:g} на СО и Ø{d_in:g} на вводе) → одна на СО, d_экв"
        res.rows.append(Recommendation(sys, "Dshb_so_pod_u", c.get("Dshb_so_pod_u"), d_eq, why))
        res.rows.append(Recommendation(sys, "Dshb_pod", c.get("Dshb_pod"), None, why))
        res.rows.append(Recommendation(sys, "Nshb_pod", c.get("Nshb_pod"), None, why))


def washer_rows(res: StepResult, c: Consumer, t: FlowTarget, h_new: float, reason: str) -> None:
    """Washers in series all count: S = (H_ras − ΣΔHшайб)/Gм², ΔH needed = H_new − S·G_цель²;
    the lever washer takes what the others leave at the target flow."""
    sys = str(c.sys)
    g_model, h_ras = c.num("Gso"), c.num("H_ras")
    washers = installed(c)
    dh_now = sum(washer_dh(g_model, d) for d in washers.values())
    pair = lever(washers)
    others = sum(washer_dh(t.g, d) for p, d in washers.items() if p != pair)
    sizing = size_washer(h_new, h_ras, dh_now, g_model, t.g)
    dh_lever = sizing.dh - others
    d_name, n_name = pair
    if dh_lever <= 0:
        if pair in washers:
            note = "убрать шайбу: расхода не хватает и без неё"
            res.rows.append(Recommendation(sys, d_name, c.get(d_name), None, reason, note))
            res.rows.append(Recommendation(sys, n_name, c.get(n_name), None, reason, note))
        else:
            res.notes.append(f"Sys {sys}: {sizing.note or 'шайба не нужна'}.")
        return
    d = round(washer_d(t.g, dh_lever), config.ROUND_D)
    note = ""
    if d < config.MIN_WASHER_MM:
        d, note = config.MIN_WASHER_MM, f"диаметр меньше {config.MIN_WASHER_MM:g} мм"
    if len(washers) > 1:
        note = (note + "; " if note else "") + "шайбы подряд: считаются обе"
    res.rows.append(Recommendation(sys, d_name, c.get(d_name), d, reason, note))
    if c.num(n_name) != 1:
        res.rows.append(Recommendation(sys, n_name, c.get(n_name), 1, reason))


def nozzle_dh(g: float, dc: float) -> float:
    """Elevator nozzle in Zulu: ΔH = G²·(9.6/dс)⁴ (= dHsop)."""
    return g**2 * (9.6 / dc) ** 4


def nozzle_d(g: float, h: float) -> float:
    """dс = 9.6·(G²/H)^¼."""
    return 9.6 * (g**2 / h) ** 0.25


def elevator_rows(res: StepResult, c: Consumer, t: FlowTarget, h_new: float, reason: str) -> None:
    """Elevator: H_ras = ΔHшайбы + ΔHсопла exactly. With the head the washer takes what the nozzle
    leaves; if the head is not enough → remove the washer (D 0, N 0) and size the nozzle
    dс = 9.6·(G²/H)^¼."""
    sys = str(c.sys)
    dc = c.num("Dsop_u")
    if not dc:
        res.questions.append(f"Sys {sys}: элеватор без сопла (Dsop_u) — подобрать по формулам.")
        return
    washers = installed(c)
    pair = lever(washers) if washers else SO_SUPPLY
    others = sum(washer_dh(t.g, d) for p, d in washers.items() if p != pair)
    dh_washer = h_new - nozzle_dh(t.g, dc) - others
    d_name, n_name = pair
    if dh_washer > config.MIN_ELEVATOR_WASHER_DH_M:
        d = round(washer_d(t.g, dh_washer), config.ROUND_D)
        res.rows.append(Recommendation(sys, d_name, c.get(d_name), d, reason,
                                       f"элеватор: сопло Ø{dc:g} остаётся"))  # fmt: skip
        if c.num(n_name) != 1:
            res.rows.append(Recommendation(sys, n_name, c.get(n_name), 1, reason))
        return
    head = h_new - others
    note = "напора не хватает на шайбу: шайбу убрать, сопло по напору"
    if pair in washers:
        res.rows.append(Recommendation(sys, d_name, c.get(d_name), 0, reason, note))
        res.rows.append(Recommendation(sys, n_name, c.get(n_name), 0, reason, note))
    if head <= 0:
        res.questions.append(f"Sys {sys}: напора нет даже на сопло ({head:.1f} м).")
        return
    new_dc = int(nozzle_d(t.g, head) * 10) / 10  # nozzle: round down to 0.1 mm
    new_dc = max(new_dc, config.MIN_WASHER_MM)
    if round(dc, 1) != new_dc:
        res.rows.append(Recommendation(sys, "Dsop_u", c.get("Dsop_u"), new_dc, reason,
                                       f"dс = 9,6·(G²/H)^¼, H = {head:.2f} м"))  # fmt: skip
