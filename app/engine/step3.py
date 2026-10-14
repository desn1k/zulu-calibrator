"""Step 3: CTP inlet washer, and the washer formulas shared with step 5.

docs/algorithm.md: «Шаг 3 — шайба ввода ЦТП» (G t/h, ΔH m, d mm).
"""

from dataclasses import dataclass

from app.engine import config
from app.engine.model import CTP_TARGET, CtpFact, Recommendation, Snapshot, StepResult

STEP3_DO_NOT_TOUCH = ["шайбы домов", "Kso", "Kcirc / Hcirc", "испытательные параметры ТО"]


@dataclass(frozen=True)
class WasherCalc:
    d: float | None  # mm, rounded; None = no washer (not needed or remove)
    dh: float | None  # head the washer takes at the fact flow, m
    note: str = ""


def washer_from_scratch(
    h_ras: float, dh_washer: float, g_fact: float, g_model: float
) -> WasherCalc:
    """«Подбор с нуля»: ΔHш = H_ras − ΔH_sys·(Gф/Gм)², d = 10·(Gф²/ΔHш)^¼.

    ΔH_sys = H_ras − dHshb (resistance without the washer: the CTP, or the house system in step 5).
    """
    if g_model <= g_fact:
        return WasherCalc(None, None, "шайба не нужна: расход ограничен выше (сеть, источник)")
    dh_sys = h_ras - dh_washer
    dh = h_ras - dh_sys * (g_fact / g_model) ** 2
    if dh <= 0:
        return WasherCalc(None, None, "шайба не нужна: напора не хватает и без неё")
    d = 10.0 * (g_fact**2 / dh) ** 0.25
    return washer_result(d, dh)


def correct_washer(
    d: float, h_ras: float, dh_washer: float, g_fact: float, g_model: float
) -> WasherCalc:
    """«Поправка установленной шайбы»:
    ΔHш,нов = H_ras − (H_ras − ΔHш)·(Gф/Gм)², d_нов = d·√(Gф/Gм)·(ΔHш/ΔHш,нов)^¼.
    """
    dh_new = h_ras - (h_ras - dh_washer) * (g_fact / g_model) ** 2
    if dh_new <= 0:
        return WasherCalc(None, dh_new, "убрать шайбу: расхода не хватает и без неё")
    d_new = d * (g_fact / g_model) ** 0.5 * (dh_washer / dh_new) ** 0.25
    return washer_result(d_new, dh_new)


def washer_result(d: float, dh: float) -> WasherCalc:
    d = round(d, config.ROUND_D)
    if d < config.MIN_WASHER_MM:
        return WasherCalc(config.MIN_WASHER_MM, dh, f"диаметр меньше {config.MIN_WASHER_MM:g} мм")
    return WasherCalc(d, dh)


def flow_sensitivity_pct(d: float, dh_washer: float, h_ras: float, dd: float = 1.0) -> float:
    """dG/G ≈ 2·(ΔHш/H_ras)·dd/d, in % for a change of `dd` mm."""
    return 2.0 * (dh_washer / h_ras) * dd / d * 100.0


def inlet_deviation_pct(snap: Snapshot, fact: CtpFact) -> float | None:
    g_model = snap.card_num("Gsum_pod")
    g_fact = fact.inlet.G1 if fact.inlet else None
    if not g_model or not g_fact:
        return None
    return (g_model / g_fact - 1.0) * 100.0


def step3(snap: Snapshot, fact: CtpFact) -> StepResult:
    res = StepResult(step="3", do_not_touch=list(STEP3_DO_NOT_TOUCH))
    card = snap.card
    dev = inlet_deviation_pct(snap, fact)
    if dev is None:
        res.questions.append(
            "Нет расхода ввода (прибор или Gsum_pod) — шайба ввода не подбирается."
        )
        return res
    if card.get("RegulType"):
        res.notes.append(
            "На ЦТП есть регулятор (RegulType ≠ 0) — расход держит он, шайба не нужна."
        )
        return res

    d = card.get("Dshb_pod_u") or None
    n = card.get("Nshb_pod_u") or None
    h_ras, dh = snap.card_num("H_ras"), snap.card_num("dHshb_pod") or 0.0
    if abs(dev) <= config.INLET_FLOW_PCT:
        if d:
            note = f"Шайба ввода Ø{d:g} — оставить: G ввода {dev:+.1f} % от прибора."
            if h_ras:
                note += f" Чувствительность: ±1 мм ≈ ±{flow_sensitivity_pct(d, dh, h_ras):.1f} %."
            res.notes.append(note)
        else:
            res.notes.append(f"G ввода {dev:+.1f} % от прибора — шайба не нужна.")
        return res

    if not h_ras:
        res.questions.append("Нет H_ras ЦТП в выгрузке — шайбу не посчитать.")
        return res
    g_fact, g_model = fact.inlet.G1, snap.card_num("Gsum_pod")
    calc = (
        correct_washer(d, h_ras, dh, g_fact, g_model)
        if d and n
        else washer_from_scratch(h_ras, dh, g_fact, g_model)
    )
    reason = f"Шаг 3: G ввода {dev:+.1f} % от прибора"
    if calc.d is None:
        if d:
            res.rows.append(Recommendation(CTP_TARGET, "Dshb_pod_u", d, None, reason, calc.note))
            res.rows.append(Recommendation(CTP_TARGET, "Nshb_pod_u", n, None, reason, calc.note))
        else:
            res.notes.append(calc.note)
        return res

    if card.get("Regul_G") != 5:
        res.rows.append(
            Recommendation(CTP_TARGET, "Regul_G", card.get("Regul_G"), 5,
                           "5 = общая шайба на вводе, на подающем")
        )  # fmt: skip
    res.rows.append(Recommendation(CTP_TARGET, "Dshb_pod_u", d, calc.d, reason, calc.note))
    if n != 1:
        res.rows.append(Recommendation(CTP_TARGET, "Nshb_pod_u", n, 1, reason))
    res.notes.append("Формула даёт оценку ~5 % (H_ras меняется с расходом) — дальше поправка.")
    return res
