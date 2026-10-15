"""Step criteria, evaluated on a fresh export after the verification run.

docs/algorithm.md: «Критерии шага 1…5», «Ловушки» (identical exports).
"""

from app.engine import config
from app.engine.dhw import DhwTarget
from app.engine.meters import consumer_kind, meter_for
from app.engine.model import DISTRUST_FIELD, Criterion, CtpFact, Snapshot
from app.engine.schemes import ctp_scheme
from app.engine.targets import HeatingTargets, model_heat


def by_pct(
    key: str, title: str, model: float | None, fact: float | None, limit: float
) -> Criterion:
    if model is None or not fact:
        return Criterion(key, title, model, fact, None, limit, "%", False)
    dev = (model / fact - 1.0) * 100.0
    return Criterion(key, title, model, fact, dev, limit, "%", abs(dev) <= limit + 1e-9)


def by_abs(
    key: str, title: str, model: float | None, fact: float | None, limit: float
) -> Criterion:
    if model is None or fact is None:
        return Criterion(key, title, model, fact, None, limit, "°C", False)
    dev = model - fact
    return Criterion(key, title, model, fact, dev, limit, "°C", abs(dev) <= limit + 1e-9)


FIRST_CONTOUR_NOTE = "первый контур / прибор"


def by_temp(
    key: str,
    title: str,
    model: float | None,
    fact: float | None,
    supply_model: float | None,
    supply_fact: float | None,
) -> Criterion:
    """«Допуск» for a return temperature: ±4 % of the value when the model supply is within 1 °C
    of the meter; otherwise ±4 % on ΔT (supply − return), and the shift of the absolute T2 is
    reported as «первый контур / прибор»."""
    limit = config.TEMP_TOLERANCE_PCT
    if model is None or not fact:
        return Criterion(key, f"{title} ±{limit:g} %", model, fact, None, limit, "%", False)
    if (
        supply_model is None
        or supply_fact is None
        or abs(supply_model - supply_fact) <= config.TEMP_SUPPLY_MATCH_C
    ):
        c = by_pct(key, f"{title} ±{limit:g} %", model, fact, limit)
        return c
    dt_model, dt_fact = supply_model - model, supply_fact - fact
    title = f"{title}: ΔT (подача − обратка) ±{limit:g} %"
    if not dt_fact:
        return Criterion(key, title, dt_model, dt_fact, None, limit, "%", False)
    dev = (dt_model / dt_fact - 1.0) * 100.0
    note = (
        f"подача модели {supply_model:.1f} против прибора {supply_fact:.1f} °C, "
        f"T2 {model - fact:+.1f} °C — {FIRST_CONTOUR_NOTE}"
    )
    return Criterion(key, title, dt_model, dt_fact, dev, limit, "%", abs(dev) <= limit + 1e-9, note)


def criteria_step1(
    snap: Snapshot, fact: CtpFact, dhw: DhwTarget | None = None, t4: float | None = None
) -> list[Criterion]:
    """Step 1 criteria by scheme. Scheme 2 (algorithm «Критерии шага 1»): Gverh > 0, T11_niz not
    ≈ T1, T3so_t / T2so_t ±0,7 °C, Gsum_pod2 ±2 %, G ввода ±2 %, T2_t ввода (temperature rule).
    Schemes of 2026-10-15: DHW at the CTP outlet ±1 °C, draw-off of the DHW objects ±4 %, DHW heat
    ±4 % (parallel), Gverh > 0 (two-stage), heating temperatures and G ввода only with an
    independent heating (CTP pumps); with direct heating the inlet closes by the house washers.
    `dhw` — the DHW target; `t4` — the heating return used (a rejected CTP sensor replaced)."""
    scheme = ctp_scheme(snap.card.get("N_schem"))
    if scheme is None or scheme.n == 2 or dhw is None:
        return criteria_step1_scheme2(snap, fact)
    inlet, heating = fact.inlet, fact.heating
    out = []
    two_stage = scheme.dhw in ("two_stage_mixed", "two_stage_sequential")
    if two_stage:
        gverh = snap.card_num("Gverh")
        out.append(Criterion("Gverh", "Gverh > 0 (II ступень работает)", gverh, None, None, 0.0,
                             "", bool(gverh and gverh > 0)))  # fmt: skip
    t_out = snap.card_num("T22_verh" if two_stage else "T22_niz")
    out.append(by_abs("T_dhw", f"T ГВС на выходе ЦТП ±{config.STEP1_DHW_TEMP_C:g} °C", t_out,
                      dhw.t_supply, config.STEP1_DHW_TEMP_C))  # fmt: skip
    draw = sum(c.num("Ggv") or 0.0 for c in snap.consumers if consumer_kind(c.scheme) == "dhw")
    out.append(by_pct("draw_off", f"Разбор ГВС-объектов (Σ Ggv) ±{config.TOLERANCE_PCT:g} %",
                      draw or None, dhw.draw_off, config.TOLERANCE_PCT))  # fmt: skip
    if scheme.dhw == "parallel":
        out.append(by_pct("Q_dhw", f"Тепло ГВС ЦТП (Q_niz) ±{config.TOLERANCE_PCT:g} %",
                          snap.card_num("Q_niz"), dhw.heat, config.TOLERANCE_PCT))  # fmt: skip
    if scheme.heating == "independent" and heating is not None:
        out.append(by_abs("T3so_t", "T3so_t (подача отопления) ±0,7 °C", snap.card_num("T3so_t"),
                          heating.T3, config.STEP1_HEATING_TEMP_C))  # fmt: skip
        ret = heating.T4 if t4 is None else t4
        out.append(by_abs("T2so_t", "T2so_t (обратка отопления) ±0,7 °C", snap.card_num("T2so_t"),
                          ret, config.STEP1_HEATING_TEMP_C))  # fmt: skip
        out.append(by_pct("Gsum_pod", "G ввода ±2 %", snap.card_num("Gsum_pod"),
                          inlet.G1 if inlet else None, config.INLET_FLOW_PCT))  # fmt: skip
    out.append(by_temp("T2_t", "T2_t ввода", snap.card_num("T2_t"), inlet.T2 if inlet else None,
                       snap.card_num("T1_t"), inlet.T1 if inlet else None))  # fmt: skip
    return out


def criteria_step1_scheme2(snap: Snapshot, fact: CtpFact) -> list[Criterion]:
    inlet, heating = fact.inlet, fact.heating
    gverh = snap.card_num("Gverh")
    t11_niz, t1_model = snap.card_num("T11_niz"), snap.card_num("T1_t")
    t1 = t1_model if t1_model is not None else (inlet.T1 if inlet else None)
    not_t1 = t11_niz is not None and t1 is not None
    not_t1 = not_t1 and abs(t11_niz - t1) > config.STEP1_T11_NIZ_NOT_T1_C
    return [
        Criterion("Gverh", "Gverh > 0 (расчёт по схеме 2, не по параллельной)", gverh, None,
                  None, 0.0, "", bool(gverh and gverh > 0)),
        Criterion("T11_niz", "T11_niz — расчётная, не ≈ T1", t11_niz, t1, None,
                  config.STEP1_T11_NIZ_NOT_T1_C, "°C", not_t1),
        by_abs("T3so_t", "T3so_t (подача отопления) ±0,7 °C", snap.card_num("T3so_t"),
               heating.T3 if heating else None, config.STEP1_HEATING_TEMP_C),
        by_abs("T2so_t", "T2so_t (обратка отопления) ±0,7 °C", snap.card_num("T2so_t"),
               heating.T4 if heating else None, config.STEP1_HEATING_TEMP_C),
        by_pct("Gsum_pod2", "Gsum_pod2 (расход 2 контура) ±2 %", snap.card_num("Gsum_pod2"),
               heating.G3 if heating else None, config.STEP1_SECOND_CIRCUIT_FLOW_PCT),
        by_pct("Gsum_pod", "G ввода ±2 %", snap.card_num("Gsum_pod"),
               inlet.G1 if inlet else None, config.INLET_FLOW_PCT),
        by_temp("T2_t", "T2_t ввода", snap.card_num("T2_t"), inlet.T2 if inlet else None,
                snap.card_num("T1_t"), inlet.T1 if inlet else None),
    ]  # fmt: skip


def dhw_ctp_heat(snap: Snapshot) -> float | None:
    q_niz, q_verh = snap.card_num("Q_niz"), snap.card_num("Q_verh")
    if q_niz is None and q_verh is None:
        return None
    return (q_niz or 0.0) + (q_verh or 0.0)


def criteria_step2(
    snap: Snapshot, previous: Snapshot | None = None, fact: CtpFact | None = None
) -> list[Criterion]:
    out = []
    for c in snap.consumers:
        if consumer_kind(c.scheme) != "dhw":
            continue
        m = meter_for(c)
        if m is None or not m.G2:
            continue  # dead-end object
        out.append(by_pct(f"Gcirc:{c.sys}", f"Sys {c.sys}: Gcirc ±10 %", c.num("Gcirc"), m.G2,
                          config.STEP2_GCIRC_PCT))  # fmt: skip
        out.append(by_abs(f"Tcirc:{c.sys}", f"Sys {c.sys}: Tcirc_t ±1,5 °C", c.num("T2_t"), m.T2,
                          config.STEP2_TCIRC_C))  # fmt: skip

    if previous is not None:
        cur, prev = dhw_ctp_heat(snap), dhw_ctp_heat(previous)
        target = fact.dhw.Q if fact and fact.dhw else None
        if cur is None or prev is None:
            passed = False
        elif target is not None:
            passed = abs(cur - target) < abs(prev - target)
        else:
            passed = cur > prev
        out.append(Criterion("Q_dhw_ctp", "Q ГВС ЦТП (Q_niz + Q_verh) растёт к факту", cur, target,
                             None, 0.0, "", passed))  # fmt: skip
    return out


def criteria_step3(snap: Snapshot, fact: CtpFact) -> list[Criterion]:
    return [
        by_pct("Gsum_pod", "G ввода ±2 % от прибора", snap.card_num("Gsum_pod"),
               fact.inlet.G1 if fact.inlet else None, config.INLET_FLOW_PCT)
    ]  # fmt: skip


def house_heat(
    snap: Snapshot, targets: HeatingTargets, unmetered_heat: float | None = None
) -> list[Criterion]:
    """Heat of each metered building ±4 % (a multi-input building as a whole, by its one meter);
    the unmetered buildings together against their heat target when it is known."""
    by_sys = {c.sys: c for c in snap.consumers}
    out = []
    limit = config.HOUSE_HEAT_PCT
    for mg in targets.metered:
        if mg.meter.Q is None:
            continue
        model = sum(model_heat(by_sys[s]) or 0.0 for s in mg.sys_list)
        if len(mg.sys_list) == 1:
            [s] = mg.sys_list
            out.append(by_pct(f"Q_sum:{s}", f"Sys {s}: Q ±{limit:g} %", model, mg.meter.Q, limit))
        else:
            label = "/".join(map(str, mg.sys_list))
            out.append(by_pct(f"Q_sum:group:{mg.sys_list[0]}", f"Дом {label}: ΣQ ±{limit:g} %",
                              model, mg.meter.Q, limit))  # fmt: skip
    if unmetered_heat and targets.unmetered:
        model = sum(model_heat(c) or 0.0 for c in targets.unmetered)
        out.append(by_pct("Q_sum:unmetered", f"Дома без приборов: ΣQ ±{limit:g} %", model,
                          unmetered_heat, limit))  # fmt: skip
    return out


def criteria_step4(
    snap: Snapshot, targets: HeatingTargets, unmetered_heat: float | None = None
) -> list[Criterion]:
    return house_heat(snap, targets, unmetered_heat)


def criteria_step5(
    snap: Snapshot,
    fact: CtpFact,
    targets: HeatingTargets,
    unmetered_heat: float | None = None,
) -> list[Criterion]:
    """Gso of every heating input against its target: own meter ±2 %, an input of a multi-input
    building ±4 % and the building ±2 %, an unmetered input (remainder) ±4 %; Gsum_pod2 ±1 %;
    heat of the buildings does not go away. Inputs without a target are left out."""
    by_sys = {c.sys: c for c in snap.consumers}
    out = []
    groups_done: set[tuple[int, ...]] = set()
    for sys, t in targets.flows.items():
        c = by_sys.get(sys)
        if c is None or c.get(DISTRUST_FIELD):
            continue
        if t.source == "meter":
            out.append(by_pct(f"Gso:{sys}", f"Sys {sys}: Gso ±{config.HOUSE_FLOW_PCT:g} %",
                              c.num("Gso"), t.g, config.HOUSE_FLOW_PCT))  # fmt: skip
            continue
        if t.source == "remainder":
            limit = config.TOLERANCE_PCT
            out.append(by_pct(f"Gso:{sys}", f"Sys {sys}: Gso ±{limit:g} % (без прибора, остаток)",
                              c.num("Gso"), t.g, limit))  # fmt: skip
            continue
        limit = config.MULTI_INPUT_EACH_PCT
        out.append(by_pct(f"Gso:{sys}", f"Sys {sys}: Gso ±{limit:g} % (ввод многовводового дома)",
                          c.num("Gso"), t.g, limit))  # fmt: skip
        if t.members not in groups_done:
            groups_done.add(t.members)
            members = [by_sys[s] for s in t.members if s in by_sys]
            total_model = sum(m.num("Gso") or 0.0 for m in members)
            total_fact = sum(targets.flows[s].g for s in t.members if s in targets.flows)
            guid = members[0].guid if members else t.members[0]
            out.append(by_pct(f"Gso:group:{guid}", "Многовводовый дом: Σ Gso ±2 %",
                              total_model, total_fact, config.MULTI_INPUT_GROUP_PCT))  # fmt: skip

    g_heat = targets.g_heating or (fact.heating.G3 if fact.heating else None)
    out.append(by_pct("Gsum_pod2", "Gsum_pod2 ЦТП ±1 %", snap.card_num("Gsum_pod2"), g_heat,
                      config.CTP_SECOND_CIRCUIT_FLOW_PCT))  # fmt: skip
    out.extend(house_heat(snap, targets, unmetered_heat))
    return out


CARD_RESULT_FIELDS = (
    "Gsum_pod", "Gt_obr", "T1_t", "T2_t", "T3so_t", "T2so_t", "Gsum_pod2", "Qsum",
    "Gverh", "Gniz", "Q_niz", "Q_verh", "H_ras", "dHshb_pod",
)  # fmt: skip
CONSUMER_RESULT_FIELDS = (
    "Gso",
    "Q_sum",
    "Qsum",
    "T1_t",
    "T2_t",
    "Gcirc",
    "H_ras",
    "Tvso_t",
    "dHshb_so_pod",
)


def results_identical(a: Snapshot, b: Snapshot) -> bool:
    """«Два соседних JSON идентичны по результатам → правка не внесена или расчёт не запущен»."""
    if any(a.card.get(k) != b.card.get(k) for k in CARD_RESULT_FIELDS):
        return False
    b_by_sys = {c.sys: c for c in b.consumers}
    if b_by_sys.keys() != {c.sys for c in a.consumers}:
        return False
    return all(
        c.get(k) == b_by_sys[c.sys].get(k) for c in a.consumers for k in CONSUMER_RESULT_FIELDS
    )
