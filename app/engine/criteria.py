"""Step criteria, evaluated on a fresh export after the verification run.

docs/algorithm.md: «Критерии шага 1…5», «Ловушки» (identical exports).
"""

from app.engine import config
from app.engine.grouping import group_consumers, split_multi_input
from app.engine.meters import consumer_kind, meter_for
from app.engine.model import Criterion, CtpFact, Snapshot


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


def criteria_step1(snap: Snapshot, fact: CtpFact) -> list[Criterion]:
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
        by_pct("T2_t", "T2_t ввода ±4 %", snap.card_num("T2_t"),
               inlet.T2 if inlet else None, config.STEP1_INLET_T2_PCT),
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


def house_heat(snap: Snapshot) -> list[Criterion]:
    out = []
    for c in snap.consumers:
        if consumer_kind(c.scheme) != "heating":
            continue
        m = meter_for(c)
        out.append(by_pct(f"Q_sum:{c.sys}", f"Sys {c.sys}: Q_sum ±5 %", c.num("Q_sum"),
                          m.Q if m else None, config.HOUSE_HEAT_PCT))  # fmt: skip
    return out


def criteria_step4(snap: Snapshot) -> list[Criterion]:
    return house_heat(snap)


def criteria_step5(snap: Snapshot, fact: CtpFact) -> list[Criterion]:
    out = []
    for g in group_consumers(snap.consumers):
        if g.kind != "heating":
            continue
        if g.multi_input:
            split = split_multi_input(g)
            for c in g.members:
                fact_g = split[c.sys].G1 if c.sys in split else None
                title = f"Sys {c.sys}: Gso ±5 % (ввод многовводового дома)"
                out.append(by_pct(f"Gso:{c.sys}", title, c.num("Gso"), fact_g,
                                  config.MULTI_INPUT_EACH_PCT))  # fmt: skip
            total_model = sum(c.num("Gso") or 0.0 for c in g.members)
            total_fact = sum(m.G1 or 0.0 for m in split.values())
            out.append(by_pct(f"Gso:group:{g.guid}", "Многовводовый дом: Σ Gso ±2 %",
                              total_model, total_fact, config.MULTI_INPUT_GROUP_PCT))  # fmt: skip
            continue
        [c] = g.members
        m = meter_for(c)
        out.append(by_pct(f"Gso:{c.sys}", f"Sys {c.sys}: Gso ±2 %", c.num("Gso"),
                          m.G1 if m else None, config.HOUSE_FLOW_PCT))  # fmt: skip

    out.append(by_pct("Gsum_pod2", "Gsum_pod2 ЦТП ±1 %", snap.card_num("Gsum_pod2"),
                      fact.heating.G3 if fact.heating else None,
                      config.CTP_SECOND_CIRCUIT_FLOW_PCT))  # fmt: skip
    out.extend(house_heat(snap))
    return out


CARD_RESULT_FIELDS = (
    "Gsum_pod", "Gt_obr", "T1_t", "T2_t", "T3so_t", "T2so_t", "Gsum_pod2", "Qsum",
    "Gverh", "Gniz", "Q_niz", "Q_verh", "H_ras", "dHshb_pod",
)  # fmt: skip
CONSUMER_RESULT_FIELDS = (
    "Gso",
    "Q_sum",
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
