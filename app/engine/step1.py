"""Step 1: CTP scheme, heating HX, DHW stages, Kgv.

docs/algorithm.md: «Шаг 1 — схема ЦТП, ТО отопления, ступени ГВС, Kgv» (1.1 scheme, 1.2 test
parameters for scheme 2, 1.3 Kgv of DHW objects).
"""

from dataclasses import dataclass, field
from typing import Literal

from app.engine import config
from app.engine.dhw import (
    DhwTarget,
    choose_dhw_target,
    hgv2_rows_values,
    mixed_dependent_params,
    parallel_params,
    sequential_params,
    stage2_correction,
)
from app.engine.meters import consumer_kind, meter_for
from app.engine.model import CTP_TARGET, Consumer, CtpFact, Recommendation, Snapshot, StepResult
from app.engine.schemes import Scheme, ctp_scheme
from app.engine.validity import assess

KGV_BY_HEAT_NOTE = "по теплу (расход не измерен)"
DRAW_OFF_HINT = "T2 ввода физически не опустится до факта — допустимо принять с отклонением"

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
HEAD_FIELDS = {"Hgv2_obr", "Hgv2_ras"}


def round_field(name: str, value: float) -> float:
    if name in HEAT_FIELDS:
        return round(value, config.ROUND_Q)
    if name in FLOW_FIELDS:
        return round(value, config.ROUND_G)
    if name in HEAD_FIELDS:
        return round(value, config.ROUND_H)
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

    The inlet T2 is balanced first (1.2, approved): T2_bal = T1 − 1000·(Qсо + Q_i_niz + Q_i_verh)/G
    and T12_niz = T2_bal. The page shows both T2_bal and the meter T2 (README: 57.2 vs 57.0).
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


KgvMode = Literal["auto", "formula", "model"]
KGV_MODE_TITLES = {
    "auto": "автоматически: по расходу модели, если ГВС в модели жива, иначе формула 1.3",
    "formula": "всегда формула 1.3 (по Tgv объекта)",
    "model": "всегда по расходу модели: Kgv·(G1 − G2)ф / Ggv",
}
KGV_ALIVE_NOTE = "ГВС в модели жива: по расходу модели"
KGV_DEAD_NOTE = "ГВС в модели не работает: формула 1.3"


def dhw_alive(c: Consumer, meter_t1: float | None) -> bool:
    """«DHW alive» in the model run (approved 2026-10-15): Ggv > 0 and Tgv_t ≥ (T1_GVS of the
    meter, or Tgv without a meter) − 10 °C. A cold DHW (junk HX parameters) is not alive."""
    ggv, t_model = c.num("Ggv"), c.num("Tgv_t")
    if t_model is None:
        t_model = c.num("T1_t")
    ref = meter_t1 if meter_t1 is not None else c.num("Tgv")
    if not ggv or ggv <= 0 or t_model is None or ref is None:
        return False
    return t_model >= ref - config.KGV_ALIVE_GAP_C


def unmetered_dhw_draw(consumers: list[Consumer], ctp_supply: float | None) -> dict[int, float]:
    """DHW objects without a meter get the rest of the CTP DHW supply meter (dead-end objects):
    G_rest = G1_GVS ЦТП − Σ G1 of the metered DHW objects, split by Qgv_sred."""
    dhw = [c for c in consumers if consumer_kind(c.scheme) == "dhw"]
    unmetered = [c for c in dhw if meter_for(c) is None or meter_for(c).G1 is None]
    if not unmetered or not ctp_supply:
        return {}
    metered = sum(meter_for(c).G1 for c in dhw if c not in unmetered)
    rest = ctp_supply - metered
    load = sum(c.num("Qgv_sred") or 0.0 for c in unmetered)
    if rest <= 0 or load <= 0:
        return {}
    return {c.sys: rest * (c.num("Qgv_sred") or 0.0) / load for c in unmetered}


def model_dhw_temperature(c: Consumer, thv: float) -> float | None:
    """DHW temperature of the object Zulu used for its draw-off Ggv = 1000·Qgv_sred·Kgv/(T − Thv)
    (falls back to T1_t)."""
    ggv, qgv, kgv = c.num("Ggv"), c.num("Qgv_sred"), c.num("Kgv")
    if ggv and qgv and kgv:
        return thv + 1000.0 * qgv * kgv / ggv
    return c.num("T1_t")


def kgv_rows(
    consumers: list[Consumer],
    mode: KgvMode = "auto",
    tgv_change: tuple[float, float] | None = None,
    ctp_supply: float | None = None,
) -> list[Recommendation]:
    """1.3: Kgv of DHW objects where the model draw-off differs from the house meter by more than
    the tolerance.

    - «auto» (approved 2026-10-15), per object: DHW alive in the model run (Ggv > 0 and
      Tgv_t ≥ T1_GVS − 10 °C) → Kgv·G_цель/Ggv (Zulu's real response); not alive → formula 1.3;
      the branch is shown on the row;
    - «formula» (algorithm 1.3): Kgv = G_цель·(Tgv − Thv)/(1000·Qgv_sred);
    - «model»: always Kgv·G_цель/Ggv.
    `tgv_change` — (Tgv_old, Tgv_new) of the CTP when the same SQL batch changes it: the model
    branch is multiplied by (Tgv_new − Thv)/(Tgv_old − Thv) (approved 2026-10-15).
    Draw-off not measured (G1 − G2 ≤ 0.05 t/h or missing): Kgv = Q_GVS / Qgv_sred, «по теплу
    (расход не измерен)». An unmetered object gets the rest of the CTP DHW supply meter.
    """
    rest = unmetered_dhw_draw(consumers, ctp_supply)
    rows = []
    for c in consumers:
        if consumer_kind(c.scheme) != "dhw":
            continue
        m = meter_for(c)
        qgv_sred, kgv = c.num("Qgv_sred"), c.num("Kgv")
        tgv, thv = c.num("Tgv"), c.num("Thv")
        thv = 5.0 if thv is None else thv
        if not qgv_sred or kgv is None or tgv is None:
            continue
        if m is None and c.sys in rest:
            draw = rest[c.sys]
            note = "остаток прибора ГВС ЦТП"
        elif m is None:
            continue
        else:
            draw, note = m.draw_off, ""

        if draw is None or draw <= config.KGV_NO_FLOW_T_H:
            if m is None or m.Q is None:
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

        alive = dhw_alive(c, m.T1 if m is not None else None)
        use_model = mode == "model" or (mode == "auto" and alive)
        branch = (KGV_ALIVE_NOTE if alive else KGV_DEAD_NOTE) if mode == "auto" else ""
        note = "; ".join(x for x in (note, branch) if x)
        t_obj = model_dhw_temperature(c, thv)
        if use_model and c.num("Ggv") and t_obj is not None and t_obj > thv:
            model_draw = c.num("Ggv")
            if (
                abs(model_draw / draw - 1) * 100.0 <= config.KGV_DRAW_OFF_DIFF_PCT
                and not tgv_change
            ):
                continue
            # Kgv·G_цель/Ggv: Zulu takes the draw-off from heat, so raising the CTP Tgv in the same
            # batch lowers the draw-off at the same Kgv → × (Tgv_new − Thv)/(Tgv_old − Thv).
            new = kgv * draw / model_draw
            shift = ""
            if tgv_change:
                old, new_tgv = tgv_change
                factor = (new_tgv - thv) / (old - thv)
                new *= factor
                shift = (
                    f"; × ({new_tgv:g} − {thv:g})/({old:g} − {thv:g}) = {factor:.4f}: Tgv ЦТП "
                    "меняется в этом же пакете"
                )
            rows.append(
                Recommendation(
                    str(c.sys), "Kgv", c.get("Kgv"), round(new, config.ROUND_KGV),
                    f"1.3: Kgv·Gф/Ggv = {kgv:g}·{draw:.2f}/{model_draw:.3f} (T ГВС в модели "
                    f"{t_obj:.1f}){shift}",
                    note=note,
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
                f"1.3: (G1 − G2)·(Tgv − Thv)/(1000·Qgv_sred), разбор модели {model_draw:.2f} т/ч "
                f"против {draw:.2f} т/ч",
                note=note,
            )
        )  # fmt: skip
    return rows


@dataclass
class Step1Result(StepResult):
    t2_balanced: float | None = None  # inlet T2 used for the test parameters (1.2)
    t2_meter: float | None = None
    dhw_target: DhwTarget | None = None
    shown: dict[str, float] = field(default_factory=dict)  # Gр, Gп, Tо, Gгв … for the page
    kgv_mode: str = "auto"


def houses_draw_off(consumers: list[Consumer]) -> float:
    total = 0.0
    for c in consumers:
        if consumer_kind(c.scheme) == "dhw":
            m = meter_for(c)
            if m is not None and m.draw_off is not None:
                total += m.draw_off
    return total


def same_value(current, enter: float, name: str) -> bool:
    if not isinstance(current, int | float) or isinstance(current, bool):
        return False
    return round_field(name, float(current)) == enter


def add_ctp_rows(res: "Step1Result", card: dict, values: dict[str, float], reason: str) -> None:
    for name, value in values.items():
        enter = round_field(name, value)
        current = card.get(name)
        if not same_value(current, enter, name):
            res.rows.append(Recommendation(CTP_TARGET, name, current, enter, reason))


def stage2_configured(card: dict, values: dict[str, float]) -> bool:
    """Stage II test temperatures in the card are the computed ones (only Q_i_verh is tuned)."""
    names = ("T11_i_verh", "T12_i_verh", "T21_i_verh", "T22_i_verh")
    return all(same_value(card.get(n), round_field(n, values[n]), n) for n in names)


NEW_SCHEMES = frozenset({3, 5, 6, 12})


def step1(
    snap: Snapshot,
    fact: CtpFact,
    t22_niz: float | None = None,
    t12_verh: float | None = None,
    draw_off_source: Literal["houses", "ctp"] = "houses",
    *,
    kgv_mode: KgvMode = "auto",
    circulation: bool | None = None,
    t_o: float | None = None,
) -> Step1Result:
    """`draw_off_source` is the user's answer to check 7 (target of Kgv); only «дома» for now.
    `circulation` — «есть ли циркуляция от ЦТП» (None: by the CTP DHW meter); `t_o` — Tо of the
    parallel DHW (None: chosen automatically)."""
    if draw_off_source != "houses":
        raise NotImplementedError("Kgv target «верим ЦТП» is not implemented yet")
    res = Step1Result(step="1", do_not_touch=list(STEP1_DO_NOT_TOUCH), kgv_mode=kgv_mode)
    card = snap.card
    n_schem = card.get("N_schem")
    scheme = ctp_scheme(n_schem)
    tgv_change: tuple[float, float] | None = None

    if n_schem in (2, 3) or scheme is None:
        choice = choose_scheme(fact)
        if n_schem != choice.n_schem:
            res.rows.append(
                Recommendation(CTP_TARGET, "N_schem", n_schem, choice.n_schem,
                               f"1.1: {choice.reason}")
            )  # fmt: skip
            n_schem, scheme = choice.n_schem, ctp_scheme(choice.n_schem)

    if n_schem == 2:
        scheme2_rows(res, snap, fact, t22_niz, t12_verh)
    elif scheme is not None and n_schem in NEW_SCHEMES:
        tgv_change = new_scheme_rows(res, snap, fact, scheme, t22_niz, t12_verh, circulation, t_o)
    else:
        res.notes.append(
            f"Схема {n_schem}: «первая проверка» — испытательные параметры пока не считаются."
        )

    if card.get("Regul_T") != 1 and not (scheme and scheme.dhw == "two_stage_sequential"):
        res.rows.append(
            Recommendation(CTP_TARGET, "Regul_T", card.get("Regul_T"), 1, "1.2: ЦТП держит Tгв")
        )
    for name in ("Hsec_so", "Hsec_niz", "Hsec_verh"):
        if not card.get(name):
            res.questions.append(
                f"{name} = 0 или пусто: поставить всю потерю ТО в Hsec, Nsec = Ngr = 1 "
                "(справка Zulu) — укажите потерю напора ТО."
            )

    ctp_supply = fact.dhw.Gp if fact.dhw else None
    res.rows.extend(kgv_rows(snap.consumers, kgv_mode, tgv_change, ctp_supply))
    return res


def scheme2_rows(
    res: Step1Result, snap: Snapshot, fact: CtpFact, t22_niz: float | None, t12_verh: float | None
) -> None:
    card = snap.card
    if fact.dhw is None or fact.inlet is None or fact.heating is None:
        res.questions.append("Для шага 1.2 нужны приборы ввода, отопления и ГВС ЦТП.")
        return
    if t22_niz is None or t12_verh is None:
        s22, s12 = suggest_free_params(fact)
        t22_niz = s22 if t22_niz is None else t22_niz
        t12_verh = s12 if t12_verh is None else t12_verh
    p = scheme2_test_params(fact, t22_niz, t12_verh)
    res.t2_balanced, res.t2_meter = p.t2_balanced, p.t2_meter
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
    # «Если верим домам, а разбор ЦТП больше, I ступень физически не охладит обратку до факта»
    if houses_draw_off(snap.consumers) < p.draw_off:
        res.notes.append(DRAW_OFF_HINT)


def mixed_inlet_flow(fact: CtpFact, channels) -> float | None:
    """Valid inlet flow of a mixed scheme: the accepted inlet channel, else G1 (or G2)."""
    inlet = fact.inlet
    for ch in channels:
        if not ch.rejected and ch.name in ("G1_TS", "G2_TS"):
            return inlet.G1 if ch.name == "G1_TS" else inlet.G2
    return inlet.G1 if inlet.G1 is not None else inlet.G2


def new_scheme_rows(
    res: Step1Result,
    snap: Snapshot,
    fact: CtpFact,
    scheme: Scheme,
    t22_niz: float | None,
    t12_verh: float | None,
    circulation: bool | None,
    t_o: float | None,
) -> tuple[float, float] | None:
    """Schemes 3, 5, 6, 12. Returns (Tgv_old, Tgv_new) when this batch changes the CTP Tgv."""
    card, n = snap.card, scheme.n
    if fact.inlet is None or fact.heating is None or fact.dhw is None:
        res.questions.append("Для шага 1 нужны приборы ввода, отопления и ГВС ЦТП.")
        return None
    target = choose_dhw_target(fact, snap.consumers, circulation)
    res.dhw_target = target
    res.notes.append(f"Цель ГВС: {target.reason}.")
    res.notes.extend(target.notes)
    if target.draw_off is None or target.t_supply is None or target.heat is None:
        res.questions.append("Нет разбора ГВС по домам или Tгв прибора ЦТП — шаг 1 не посчитать.")
        return None
    if not target.circulation:
        res.do_not_touch.append("Kcirc / Hcirc / Tcirc (циркуляции от ЦТП нет, шаг 2 пропускается)")

    reason = f"1.2: схема {n}"
    dead_end = not target.circulation
    if scheme.dhw == "two_stage_mixed":
        # Split of the inlet between stage II and heating: first with the computed stage II
        # flow, then the channel check uses it.
        guess = mixed_dependent_params(
            fact, target, fact.inlet.G2 or fact.inlet.G1 or 0.0,
            t22_niz if t22_niz is not None else fact.mode.thv + 20.0, t12_verh,
        )  # fmt: skip
        validity = assess(snap, fact, inlet_split=guess.shown["Gверх"], dhw_heat=target.heat)
    else:
        validity = assess(snap, fact, dhw_heat=target.heat)
    eff = validity.fact
    res.notes.extend(validity.proofs)

    if scheme.dhw == "two_stage_sequential":
        p = sequential_params(eff, target, t22_niz, t12_verh)
        if stage2_configured(card, p.values):
            stage1 = {k: v for k, v in p.values.items() if k.endswith("_niz")}
            add_ctp_rows(res, card, stage1, reason)
            stage2_tuning(res, snap, target)
        else:
            add_ctp_rows(res, card, p.values, reason)
            res.notes.append(
                "II ступень в схеме 12 видно по T ГВС на выходе ЦТП, а не по T1 отопления; "
                "через неё Zulu пропускает около четверти испытательного расхода — Q_i_verh "
                "подбирается по T ГВС после расчёта."
            )
    elif scheme.dhw == "parallel":
        p = parallel_params(eff, target, t_o, scheme.heating == "independent")
        add_ctp_rows(res, card, p.values, reason)
    elif scheme.dhw == "two_stage_mixed":
        if t22_niz is None:
            res.questions.append("Задайте T22_niz (свободный параметр I ступени).")
            t22_niz = round(eff.mode.thv + 20.0, 1)
        g_inlet = mixed_inlet_flow(eff, validity.channels) or 0.0
        p = mixed_dependent_params(eff, target, g_inlet, t22_niz, t12_verh)
        add_ctp_rows(res, card, p.values, reason)
    else:
        return None
    res.shown.update(p.shown)
    res.notes.extend(p.notes)
    res.questions.extend(p.questions)

    tgv_change: tuple[float, float] | None = None
    tgv_card = snap.card_num("Tgv")
    if tgv_card is None or round(tgv_card, 1) != round(target.t_supply, 1):
        res.rows.append(
            Recommendation(CTP_TARGET, "Tgv", card.get("Tgv"), round(target.t_supply, 1),
                           "Tgv = Tгв прибора ЦТП")
        )  # fmt: skip
        if tgv_card is not None:
            tgv_change = (tgv_card, target.t_supply)

    hgv2 = hgv2_rows_values(snap.card_num("H_geo"), eff, dead_end)
    if hgv2:
        now = (snap.card_num("Hgv2_obr") or 0.0) + (snap.card_num("Hgv2_ras") or 0.0)
        need = hgv2["Hgv2_obr"] + hgv2["Hgv2_ras"]
        if not dead_end or abs(now - need) > config.HGV2_SUM_TOL_M:
            why = (
                "тупиковая ГВС: Hgv2_obr + Hgv2_ras = H_geo + P1_GVS"
                if dead_end
                else "Hgv2_obr = H_geo + P2_GVS, Hgv2_ras = P1_GVS − P2_GVS"
            )
            add_ctp_rows(res, card, hgv2, why)
        res.do_not_touch = [f for f in res.do_not_touch if not f.startswith("Hgv2")]
    dhw_return_pressure_check(res, snap)
    return tgv_change


def stage2_tuning(res: Step1Result, snap: Snapshot, target: DhwTarget) -> None:
    """Scheme 12, stage II configured: tune Q_i_verh by T DHW at the CTP outlet."""
    t_out, tgv = snap.card_num("T22_verh"), target.t_supply
    q_i, q_model = snap.card_num("Q_i_verh"), snap.card_num("Q_verh")
    t21 = snap.card_num("T21_verh")
    g_model = snap.card_num("G2_verh")  # model flow through stage II
    if None in (t_out, q_i, q_model, t21) or not g_model:
        return
    if abs(t_out - tgv) <= config.STEP1_DHW_TEMP_C:
        res.notes.append(f"T ГВС на выходе ЦТП {t_out:g} против {tgv:g} °C — II ступень сошлась.")
        return
    new = stage2_correction(q_i, q_model, g_model, tgv, t21)
    if new is None:
        res.questions.append("II ступень не работает (Q_verh = 0) — проверить испытательные.")
        return
    q_needed = g_model * (tgv - t21) / 1000.0
    res.rows.append(
        Recommendation(
            CTP_TARGET, "Q_i_verh", q_i, round(new, config.ROUND_Q),
            f"II ступень: T ГВС {t_out:g} против {tgv:g} °C; Q_i_verh·Q_нужно/Q_verh = "
            f"{q_i:g}·{q_needed:.4f}/{q_model:g}, Q_нужно = G_модели {g_model:g}·"
            f"({tgv:g} − {t21:g})/1000",
        )
    )  # fmt: skip


def dhw_return_pressure_check(res: Step1Result, snap: Snapshot) -> None:
    """Hgv2_obr must keep the DHW return pressure positive at every DHW building — otherwise
    Zulu disconnects the building (example Пионерская)."""
    bad = [
        c.sys
        for c in snap.consumers
        if consumer_kind(c.scheme) == "dhw" and c.num("Pobr") is not None and c.num("Pobr") <= 0
    ]
    if bad:
        res.questions.append(
            f"Давление в обратке ГВС ≤ 0 у Sys {', '.join(map(str, bad))} — Zulu отключит дом: "
            "поднять Hgv2_obr (не ниже H_geo дома + разумный напор)."
        )
