"""Step 2: DHW circulation of the houses.

docs/algorithm.md: «Шаг 2 — циркуляция ГВС домов» (Kcirc mode «по среднему расходу»).
"""

from app.engine import config
from app.engine.meters import consumer_kind, meter_for
from app.engine.model import Recommendation, Snapshot, StepResult

STEP2_DO_NOT_TOUCH = ["Kgv", "Tgv домов", "Hgv2_ras / Hgv2_obr ЦТП"]


def step2(snap: Snapshot) -> StepResult:
    res = StepResult(step="2", do_not_touch=list(STEP2_DO_NOT_TOUCH))
    res.notes.append(
        "Kcirc 200–800 % — нормально для суточных данных: циркуляция идёт круглосуточно. "
        "Режим Kcirc — «по среднему расходу»."
    )
    for c in snap.consumers:
        if consumer_kind(c.scheme) != "dhw":
            continue
        m = meter_for(c)
        sys = str(c.sys)
        if m is None or not m.G2:
            res.notes.append(f"Sys {sys}: тупиковый объект (нет циркуляции по прибору) — пропущен.")
            continue

        qgv_sred, kgv, tgv = c.num("Qgv_sred"), c.num("Kgv"), c.num("Tgv")
        thv = c.num("Thv")
        thv = 5.0 if thv is None else thv
        if not qgv_sred or kgv is None or tgv is None:
            res.questions.append(f"Sys {sys}: нет Qgv_sred / Kgv / Tgv — Kcirc не посчитать.")
            continue

        g_gv = 1000.0 * qgv_sred * kgv / (tgv - thv)
        kcirc_new = round(100.0 * m.G2 / g_gv)
        kcirc, hcirc = c.num("Kcirc"), c.num("Hcirc")
        h_ras, g_model = c.num("H_ras"), c.num("Gcirc")
        placeholder = hcirc is None or hcirc <= config.HCIRC_PLACEHOLDER + 1e-9

        if kcirc is None or abs(kcirc_new - kcirc) > 0.01 * kcirc_new:
            res.rows.append(
                Recommendation(
                    sys, "Kcirc", c.get("Kcirc"), kcirc_new,
                    f"Kcirc = 100·G2 / Ggv = 100·{m.G2:g} / {g_gv:.3f}",
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
        elif g_model and abs(g_model / m.G2 - 1) * 100.0 > config.STEP2_GCIRC_PCT:
            new = round(hcirc * (g_model / m.G2) ** 2, config.ROUND_H)
            res.rows.append(
                Recommendation(
                    sys, "Hcirc", c.get("Hcirc"), new,
                    f"Gcirc модели {g_model:g} против {m.G2:g}: Hcirc·(Gм/Gф)²",
                )
            )  # fmt: skip

        if m.T2 is not None:
            tcirc = c.num("Tcirc")
            if tcirc is None or round(tcirc, 1) != round(m.T2, 1):
                res.rows.append(
                    Recommendation(sys, "Tcirc", c.get("Tcirc"), round(m.T2, 1),
                                   "Tcirc = T2_GVS прибора")
                )  # fmt: skip
    return res
