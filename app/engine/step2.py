"""Step 2: DHW circulation of the houses.

docs/algorithm.md: «Шаг 2 — циркуляция ГВС домов» (Kcirc mode «по среднему расходу»), example
Береговая (circulation model check, Tcirc from two runs), example Чернышевского (no circulation
from the CTP → Kcirc = 0, step skipped).
"""

from app.engine import config
from app.engine.meters import consumer_kind, meter_for
from app.engine.model import DISTRUST_FIELD, Consumer, Recommendation, Snapshot, StepResult

STEP2_DO_NOT_TOUCH = ["Kgv", "Tgv домов", "Hgv2_ras / Hgv2_obr ЦТП"]
STEP2_SKIPPED = "Циркуляции от ЦТП нет → Kcirc = 0, шаг 2 пропускается."


def model_gcirc(c: Consumer) -> float | None:
    """Circulation in Zulu: Gcirc = Kcirc/100 · Ggv · √(H_ras / Hcirc) (example Береговая)."""
    kcirc, ggv, h_ras, hcirc = c.num("Kcirc"), c.num("Ggv"), c.num("H_ras"), c.num("Hcirc")
    if None in (kcirc, ggv, h_ras, hcirc) or hcirc <= 0 or h_ras < 0:
        return None
    return kcirc / 100.0 * ggv * (h_ras / hcirc) ** 0.5


def loop_cooling(c: Consumer) -> float | None:
    """Cooling in the loop in the model: T at the object − circulation return."""
    t1, t2 = c.num("T1_t"), c.num("T2_t")
    return None if t1 is None or t2 is None else t1 - t2


def tcirc_by_two_runs(
    tcirc1: float, cool1: float, tcirc2: float, cool2: float, cool_target: float
) -> float | None:
    """Tcirc changes only the loop cooling; linear between two runs."""
    if tcirc1 == tcirc2 or cool1 == cool2:
        return None
    return tcirc1 + (cool_target - cool1) * (tcirc2 - tcirc1) / (cool2 - cool1)


def step2(
    snap: Snapshot, previous: Snapshot | None = None, circulation: bool | None = None
) -> StepResult:
    res = StepResult(step="2", do_not_touch=list(STEP2_DO_NOT_TOUCH))
    if circulation is False:
        res.notes.append(STEP2_SKIPPED)
        for c in snap.consumers:
            if consumer_kind(c.scheme) == "dhw" and c.num("Kcirc"):
                res.rows.append(Recommendation(str(c.sys), "Kcirc", c.get("Kcirc"), 0,
                                               STEP2_SKIPPED))  # fmt: skip
        return res
    res.notes.append(
        "Kcirc 200–800 % — нормально для суточных данных: циркуляция идёт круглосуточно. "
        "Режим Kcirc — «по среднему расходу»."
    )
    prev = {c.sys: c for c in previous.consumers} if previous else {}
    for c in snap.consumers:
        if consumer_kind(c.scheme) != "dhw":
            continue
        m = meter_for(c)
        sys = str(c.sys)
        if c.get(DISTRUST_FIELD):
            res.notes.append(f"Sys {sys}: прибор помечен «не доверять» — пропущен.")
            continue
        if m is None or not m.G2:
            res.notes.append(f"Sys {sys}: тупиковый объект (нет циркуляции по прибору) — пропущен.")
            continue

        if tcirc_only(c, m.G2, m.T2):
            tcirc_rows(res, c, prev.get(c.sys), m.G2, m.T2)
            continue
        doc_rows(res, c, m.G2, m.T2)
    return res


def tcirc_only(c: Consumer, g2: float, t2: float | None) -> bool:
    """The model circulation matches the meter and the loop cooling is close → keep Kcirc / Hcirc
    (check only) and tune Tcirc (example Береговая). Otherwise the step 2 procedure."""
    g = c.num("Gcirc")
    cool = loop_cooling(c)
    if not g or t2 is None or cool is None or c.num("T1_t") is None:
        return False
    if abs(g / g2 - 1.0) * 100.0 > config.STEP2_GCIRC_PCT:
        return False
    target = c.num("T1_t") - t2
    return target > 0 and cool >= config.STEP2_TCIRC_ONLY_COOLING_SHARE * target


def tcirc_rows(res: StepResult, c: Consumer, prev: Consumer | None, g2: float, t2: float) -> None:
    sys = str(c.sys)
    g_model = model_gcirc(c)
    if g_model is not None:
        res.notes.append(
            f"Sys {sys}: Gcirc = Kcirc/100·Ggv·√(H_ras/Hcirc) = {g_model:.2f} т/ч (Zulu "
            f"{c.num('Gcirc'):g}) против прибора {g2:g} — Kcirc / Hcirc не трогать."
        )
    cool, cool_target = loop_cooling(c), c.num("T1_t") - t2
    tcirc = c.num("Tcirc")
    if tcirc is None or abs(cool - cool_target) <= config.STEP2_TCIRC_C:
        return
    new, how = None, ""
    if prev is not None and prev.num("Tcirc") is not None and loop_cooling(prev) is not None:
        new = tcirc_by_two_runs(prev.num("Tcirc"), loop_cooling(prev), tcirc, cool, cool_target)
        how = (
            f"по двум расчётам: Tcirc {prev.num('Tcirc'):g} → остывание "
            f"{loop_cooling(prev):.1f}, {tcirc:g} → {cool:.1f}; нужно {cool_target:.1f} °C"
        )
    if new is None:
        new = tcirc - (cool_target - cool)  # first trial: one degree of Tcirc per degree
        how = f"проба: остывание {cool:.1f} против {cool_target:.1f} °C"
    res.rows.append(Recommendation(sys, "Tcirc", c.get("Tcirc"), round(new, 1),
                                   f"Tcirc меняет только остывание в кольце, {how}"))  # fmt: skip


def doc_rows(res: StepResult, c: Consumer, g2: float, t2: float | None) -> None:
    sys = str(c.sys)
    qgv_sred, kgv, tgv = c.num("Qgv_sred"), c.num("Kgv"), c.num("Tgv")
    thv = c.num("Thv")
    thv = 5.0 if thv is None else thv
    if not qgv_sred or kgv is None or tgv is None:
        res.questions.append(f"Sys {sys}: нет Qgv_sred / Kgv / Tgv — Kcirc не посчитать.")
        return

    g_gv = 1000.0 * qgv_sred * kgv / (tgv - thv)
    kcirc_new = round(100.0 * g2 / g_gv)
    kcirc, hcirc = c.num("Kcirc"), c.num("Hcirc")
    h_ras, g_model = c.num("H_ras"), c.num("Gcirc")
    placeholder = hcirc is None or hcirc <= config.HCIRC_PLACEHOLDER + 1e-9

    if kcirc is None or abs(kcirc_new - kcirc) > 0.01 * kcirc_new:
        res.rows.append(
            Recommendation(
                sys, "Kcirc", c.get("Kcirc"), kcirc_new,
                f"Kcirc = 100·G2 / Ggv = 100·{g2:g} / {g_gv:.3f}",
            )
        )  # fmt: skip

    if placeholder:
        if h_ras:
            res.rows.append(
                Recommendation(sys, "Hcirc", c.get("Hcirc"), round(h_ras, config.ROUND_H),
                               "Hcirc = H_ras дома из последнего расчёта")
            )  # fmt: skip
        else:
            res.questions.append(f"Sys {sys}: нет H_ras — Hcirc не задать.")
    elif g_model and abs(g_model / g2 - 1) * 100.0 > config.STEP2_GCIRC_PCT:
        new = round(hcirc * (g_model / g2) ** 2, config.ROUND_H)
        res.rows.append(
            Recommendation(
                sys, "Hcirc", c.get("Hcirc"), new,
                f"Gcirc модели {g_model:g} против {g2:g}: Hcirc·(Gм/Gф)²",
            )
        )  # fmt: skip

    if t2 is not None:
        tcirc = c.num("Tcirc")
        if tcirc is None or round(tcirc, 1) != round(t2, 1):
            res.rows.append(
                Recommendation(sys, "Tcirc", c.get("Tcirc"), round(t2, 1),
                               "Tcirc = T2_GVS прибора")
            )  # fmt: skip
