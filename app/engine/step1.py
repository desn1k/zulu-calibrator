"""Step 1: CTP scheme, heating HX, DHW stages, Kgv.

docs/algorithm.md: «Шаг 1 — схема ЦТП, ТО отопления, ступени ГВС, Kgv» (1.1 scheme, 1.2 test
parameters for scheme 2, 1.3 Kgv of DHW objects).
"""

from dataclasses import dataclass, field

from app.engine import config
from app.engine.meters import consumer_kind, meter_for
from app.engine.model import CTP_TARGET, Consumer, CtpFact, Recommendation, Snapshot, StepResult

KGV_BY_HEAT_NOTE = "по теплу (расход не измерен)"

STEP1_DO_NOT_TOUCH = [
    "Kso",
    "Qo_r",
    "Qgv_sred",
    "Dshb_pod_u",
    "Dshb_so_pod_u",
    "Hnz_ras",
    "Hnz_obr",
    "Hgv2_ras",
    "Hgv2_obr",
    "утечки 2 контура",
    "Gcalibr_* / Pcalibr_*",
    "T1_r / T3_r / T2_r домов",
]

TEMP_FIELDS = {
    "T11_i", "T12_i", "T21_i", "T22_i",
    "T11_i_niz", "T12_i_niz", "T21_i_niz", "T22_i_niz",
    "T11_i_verh", "T12_i_verh", "T21_i_verh", "T22_i_verh",
}  # fmt: skip
FLOW_FIELDS = {"G1_i", "G2_i"}
HEAT_FIELDS = {"Q_i_niz", "Q_i_verh"}


def round_field(name: str, value: float) -> float:
    if name in HEAT_FIELDS:
        return round(value, config.ROUND_Q)
    if name in FLOW_FIELDS:
        return round(value, config.ROUND_G)
    return round(value, config.ROUND_T)


@dataclass(frozen=True)
class SchemeChoice:
    n_schem: int
    reason: str


def choose_scheme(fact: CtpFact) -> SchemeChoice:
    """1.1: the number is chosen by temperatures, not by the passport."""
    t2 = fact.inlet.T2 if fact.inlet else None
    t4 = fact.heating.T4 if fact.heating else None
    if t2 is not None and t4 is not None and t2 < t4:
        return SchemeChoice(2, f"T2 ввода {t2:g} < T4 {t4:g} → есть I ступень на обратке")
    return SchemeChoice(3, "T2 ввода ≥ T4 → параллельная ГВС")


@dataclass
class TestParams:
    """1.2 result for scheme 2. `values` holds unrounded Zulu fields."""

    values: dict[str, float]
    qso: float
    draw_off: float
    g_verh: float
    t2_meter: float
    t2_balanced: float
    closure: float
    closure_rounded: float
    closure_ok: bool
    t12_i_gap_ok: bool
    t12_verh_ok: bool
    notes: list[str] = field(default_factory=list)

    def rounded(self) -> dict[str, float]:
        return {k: round_field(k, v) for k, v in self.values.items()}


def scheme2_test_params(fact: CtpFact, t22_niz: float, t12_verh: float) -> TestParams:
    """1.2 for scheme 2. Free parameters: T22_niz and T12_verh.

    The inlet T2 is the measurement «сведённый в баланс» (step 1 intro): the value that makes the
    inlet heat G·(T1 − T2) equal to Qсо + Q_i_niz + Q_i_verh. With it the stage I outlet T12_niz,
    T11_niz and T12_i follow the README golden values (57.2 / 60.9 / 61.1 for meter T2 = 57.0).
    """
    inlet, heating, dhw, thv = fact.inlet, fact.heating, fact.dhw, fact.mode.thv
    if inlet is None or heating is None or dhw is None:
        raise ValueError("step 1.2 needs inlet, heating and DHW facts of the CTP")

    g, t1, t2 = inlet.G1, inlet.T1, inlet.T2
    g3, t3, t4 = heating.G3, heating.T3, heating.T4
    gp, gc, tgv, tc = dhw.Gp, dhw.Gc, dhw.Tgv, dhw.Tc

    qso = g3 * (t3 - t4) / 1000.0
    gr = gp - gc
    q_niz = gr * (t22_niz - thv) / 1000.0
    t21_verh = (gr * t22_niz + gc * tc) / gp
    q_verh = gp * (tgv - t21_verh) / 1000.0

    t2_bal = t1 - 1000.0 * (qso + q_niz + q_verh) / g
    t12_niz = t2_bal
    t11_niz = t12_niz + 1000.0 * q_niz / g
    g_verh = 1000.0 * q_verh / (t1 - t12_verh)
    g1_i = g - g_verh
    t12_i = (g * t11_niz - g_verh * t12_verh) / g1_i

    values = {
        "T11_i": t1,
        "T12_i": t12_i,
        "T21_i": t4,
        "T22_i": t3,
        "G1_i": g1_i,
        "G2_i": g3,
        "T11_i_niz": t11_niz,
        "T12_i_niz": t12_niz,
        "T21_i_niz": thv,
        "T22_i_niz": t22_niz,
        "Q_i_niz": q_niz,
        "T11_i_verh": t1,
        "T12_i_verh": t12_verh,
        "T21_i_verh": t21_verh,
        "T22_i_verh": tgv,
        "Q_i_verh": q_verh,
    }
    closure = g1_i * (t1 - t12_i) / 1000.0
    r = {k: round_field(k, v) for k, v in values.items()}
    closure_rounded = r["G1_i"] * (t1 - r["T12_i"]) / 1000.0

    notes = []
    if t2 is not None and abs(t2 - t2_bal) >= 0.05:
        notes.append(
            f"T2 ввода сведена в баланс: {t2_bal:.1f} °C (прибор {t2:g}), "
            "так тепло ввода = Qсо + Q_i_niz + Q_i_verh."
        )
    return TestParams(
        values=values,
        qso=qso,
        draw_off=gr,
        g_verh=g_verh,
        t2_meter=t2,
        t2_balanced=t2_bal,
        closure=closure,
        closure_rounded=closure_rounded,
        # Checked on the values to enter in Zulu (rounded), as in the README example.
        closure_ok=abs(closure_rounded - qso) / qso * 100.0 <= config.STEP1_CLOSURE_PCT,
        t12_i_gap_ok=r["T12_i"] >= r["T21_i"] + config.STEP1_T12_I_MIN_GAP - 1e-9,
        t12_verh_ok=r["T12_i_verh"] >= r["T21_i_verh"] + config.STEP1_T12_VERH_MIN_GAP - 1e-9,
        notes=notes,
    )


def suggest_free_params(fact: CtpFact) -> tuple[float, float]:
    """Starting values: T22_niz 2 °C below T11_niz, T12_verh = T21_verh + 2 (rounded up to 0.1).

    With the balanced inlet T2, T11_niz = T1 − (1000·Qсо + Gп·Tгв − Gр·T22_niz − Gц·Tц)/G is linear
    in T22_niz, so the gap condition is solved directly.
    """
    inlet, heating, dhw = fact.inlet, fact.heating, fact.dhw
    g, t1 = inlet.G1, inlet.T1
    qso = heating.G3 * (heating.T3 - heating.T4) / 1000.0
    gr = dhw.Gp - dhw.Gc
    a = t1 - (1000.0 * qso + dhw.Gp * dhw.Tgv - dhw.Gc * dhw.Tc) / g
    t22_niz = round((a - config.STEP1_T22_NIZ_GAP) / (1.0 - gr / g), 1)
    t21_verh = (gr * t22_niz + dhw.Gc * dhw.Tc) / dhw.Gp
    t12_verh = -(-round((t21_verh + config.STEP1_T12_VERH_MIN_GAP) * 10, 6) // 1) / 10
    return t22_niz, t12_verh


def kgv_rows(consumers: list[Consumer]) -> list[Recommendation]:
    """1.3: Kgv of DHW objects where the model draw-off differs from the house meter by > 10 %.

    Kgv = (G1 − G2)·(Tgv − Thv)/(1000·Qgv_sred). If the draw-off is not measured
    (G1 − G2 ≤ 0.05 t/h or missing): Kgv = Q_GVS / Qgv_sred, «по теплу (расход не измерен)».
    The draw-off target is the house meters (the user's choice in check 7).
    """
    rows = []
    for c in consumers:
        if consumer_kind(c.scheme) != "dhw":
            continue
        m = meter_for(c)
        qgv_sred, kgv = c.num("Qgv_sred"), c.num("Kgv")
        tgv, thv = c.num("Tgv"), c.num("Thv")
        thv = 5.0 if thv is None else thv
        if m is None or not qgv_sred or kgv is None or tgv is None:
            continue

        draw = m.draw_off
        if draw is None or draw <= config.KGV_NO_FLOW_T_H:
            if m.Q is None:
                continue
            model_heat = qgv_sred * kgv
            if m.Q and abs(model_heat / m.Q - 1) * 100.0 <= config.KGV_DRAW_OFF_DIFF_PCT:
                continue
            new = round(m.Q / qgv_sred, config.ROUND_KGV)
            rows.append(
                Recommendation(
                    str(c.sys), "Kgv", c.get("Kgv"), new,
                    f"1.3: Kgv = Q_GVS / Qgv_sred = {m.Q:g} / {qgv_sred:g}",
                    note=KGV_BY_HEAT_NOTE,
                )
            )  # fmt: skip
            continue

        model_draw = 1000.0 * qgv_sred * kgv / (tgv - thv)
        if abs(model_draw / draw - 1) * 100.0 <= config.KGV_DRAW_OFF_DIFF_PCT:
            continue
        new = round(draw * (tgv - thv) / (1000.0 * qgv_sred), config.ROUND_KGV)
        rows.append(
            Recommendation(
                str(c.sys), "Kgv", c.get("Kgv"), new,
                f"1.3: разбор модели {model_draw:.2f} т/ч против прибора {draw:.2f} т/ч",
            )
        )  # fmt: skip
    return rows


def same_value(current, enter: float, name: str) -> bool:
    if not isinstance(current, int | float) or isinstance(current, bool):
        return False
    return round_field(name, float(current)) == enter


def step1(
    snap: Snapshot,
    fact: CtpFact,
    t22_niz: float | None = None,
    t12_verh: float | None = None,
) -> StepResult:
    res = StepResult(step="1", do_not_touch=list(STEP1_DO_NOT_TOUCH))
    card = snap.card

    choice = choose_scheme(fact)
    if card.get("N_schem") != choice.n_schem:
        res.rows.append(
            Recommendation(CTP_TARGET, "N_schem", card.get("N_schem"), choice.n_schem,
                           f"1.1: {choice.reason}")
        )  # fmt: skip

    if choice.n_schem != 2:
        res.notes.append(
            f"Схема {choice.n_schem}: расчёт испытательных параметров пока только для 2."
        )
    elif fact.dhw is None or fact.inlet is None or fact.heating is None:
        res.questions.append("Для шага 1.2 нужны приборы ввода, отопления и ГВС ЦТП.")
    else:
        if t22_niz is None or t12_verh is None:
            s22, s12 = suggest_free_params(fact)
            t22_niz = s22 if t22_niz is None else t22_niz
            t12_verh = s12 if t12_verh is None else t12_verh
        p = scheme2_test_params(fact, t22_niz, t12_verh)
        for name, enter in p.rounded().items():
            current = card.get(name)
            if not same_value(current, enter, name):
                res.rows.append(Recommendation(CTP_TARGET, name, current, enter, "1.2: схема 2"))
        res.notes.extend(p.notes)
        res.notes.append(
            f"Замыкание: G1_i·(T1 − T12_i)/1000 = {p.closure_rounded:.3f} против Qсо {p.qso:.3f}"
            + ("" if p.closure_ok else " — не сходится, сдвинуть T22_niz / T12_verh")
        )
        if not p.t12_i_gap_ok:
            res.questions.append("T12_i < T21_i + 0,8 — сдвинуть T22_niz / T12_verh.")
        if not p.t12_verh_ok:
            res.questions.append("T12_verh должна быть ≥ T21_verh + 2.")

    if card.get("Regul_T") != 1:
        res.rows.append(
            Recommendation(CTP_TARGET, "Regul_T", card.get("Regul_T"), 1, "1.2: ЦТП держит Tгв")
        )
    for name in ("Hsec_so", "Hsec_niz", "Hsec_verh"):
        if not card.get(name):
            res.questions.append(
                f"{name} = 0 или пусто: поставить всю потерю ТО в Hsec, Nsec = Ngr = 1 "
                "(справка Zulu) — укажите потерю напора ТО."
            )

    res.rows.extend(kgv_rows(snap.consumers))
    return res
