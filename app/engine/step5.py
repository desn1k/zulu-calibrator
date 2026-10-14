"""Step 5: building washers on the heating system, washers in series, junk washer fields.

docs/algorithm.md: «Шаги 4–5» → «Шаг 5 — шайбы домов» and «Две шайбы подряд».
"""

from app.engine import config
from app.engine.grouping import Shares, house_meters
from app.engine.meters import consumer_kind
from app.engine.model import (
    DISTRUST_FIELD,
    Consumer,
    CtpFact,
    Recommendation,
    Snapshot,
    StepResult,
)
from app.engine.step3 import correct_washer, inlet_deviation_pct, washer_from_scratch

STEP5_DO_NOT_TOUCH = ["Kso", "Qo_r", "T1_r / T3_r / T2_r домов", "шайба ввода ЦТП"]


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
    for d_name, n_name in (("Dshb_pod", "Nshb_pod"), ("Dshb_so_pod_u", "Nshb_so_pod_u")):
        d, n = c.get(d_name), c.get(n_name)
        if has_value(d) == has_value(n):
            continue
        reason = f"{n_name} без {d_name} (или наоборот) — мусор, очистить оба поля"
        for name, value in ((d_name, d), (n_name, n)):
            if has_value(value):
                rows.append(Recommendation(str(c.sys), name, value, None, reason))
    return rows


def step5(snap: Snapshot, fact: CtpFact, shares: Shares | None = None) -> StepResult:
    res = StepResult(step="5", do_not_touch=list(STEP5_DO_NOT_TOUCH))
    dev = inlet_deviation_pct(snap, fact)
    if dev is None or abs(dev) > config.INLET_FLOW_PCT:
        shown = "нет данных" if dev is None else f"{dev:+.1f} %"
        res.notes.append(
            f"Шайбы домов — только после того, как сошёлся ввод ЦТП (шаг 3): G ввода {shown}. "
            "До этого H_ras домов неверный."
        )
        return res

    meters = house_meters(snap.consumers, shares)
    for c in snap.consumers:
        if consumer_kind(c.scheme) != "heating":
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
        n_codes = [c.num(k) for k in ("Nshb_so_pod_u", "Nshb_pod")]
        if any(n is not None and n < 0 for n in n_codes):
            res.questions.append(f"Sys {sys}: Nshb < 0 (отключение / дроссель по Kv) — проверить.")
            continue

        junk = junk_rows(c)
        res.rows.extend(junk)
        m = meters.get(c.sys)
        g_model, h_ras = c.num("Gso"), c.num("H_ras")
        if m is None or not m.G1:
            res.notes.append(f"Sys {sys}: нет прибора — общий множитель kG (не отработано).")
            continue
        if not g_model or not h_ras:
            res.questions.append(f"Sys {sys}: нет Gso / H_ras в выгрузке.")
            continue

        off_pct = (g_model / m.G1 - 1.0) * 100.0
        d_so = c.num("Dshb_so_pod_u")
        n_so = c.num("Nshb_so_pod_u")
        dh_so = c.num("dHshb_so_pod") or 0.0
        reason = f"Gso {g_model:g} против прибора {m.G1:g} ({off_pct:+.1f} %)"

        if abs(off_pct) > config.WASHER_CHANGE_PCT:
            calc = (
                correct_washer(d_so, h_ras, dh_so, m.G1, g_model)
                if d_so and n_so == 1
                else washer_from_scratch(h_ras, dh_so, m.G1, g_model)
            )
            if calc.d is None:
                if d_so:
                    res.rows.append(Recommendation(sys, "Dshb_so_pod_u", c.get("Dshb_so_pod_u"),
                                                   None, reason, calc.note))  # fmt: skip
                    res.rows.append(Recommendation(sys, "Nshb_so_pod_u", c.get("Nshb_so_pod_u"),
                                                   None, reason, calc.note))  # fmt: skip
                else:
                    res.notes.append(f"Sys {sys}: {calc.note}.")
                continue
            res.rows.append(
                Recommendation(
                    sys, "Dshb_so_pod_u", c.get("Dshb_so_pod_u"), calc.d, reason, calc.note
                )
            )
            if n_so != 1:
                res.rows.append(
                    Recommendation(sys, "Nshb_so_pod_u", c.get("Nshb_so_pod_u"), 1, reason)
                )
            continue

        # Flow within ±2 %: two washers in series on a heating-only object → one on the SO.
        d_in, n_in = c.num("Dshb_pod"), c.num("Nshb_pod")
        if d_so and n_so == 1 and d_in and n_in == 1 and heating_only(c):
            d_eq = round(equivalent_diameter(d_so, d_in), config.ROUND_D)
            why = f"Две шайбы подряд (Ø{d_so:g} на СО и Ø{d_in:g} на вводе) → одна на СО, d_экв"
            res.rows.append(Recommendation(sys, "Dshb_so_pod_u", c.get("Dshb_so_pod_u"), d_eq, why))
            res.rows.append(Recommendation(sys, "Dshb_pod", c.get("Dshb_pod"), None, why))
            res.rows.append(Recommendation(sys, "Nshb_pod", c.get("Nshb_pod"), None, why))

    res.notes.append(
        "Шайба с малым dHshb_so_pod (< 2 м) резко реагирует на диаметр; меняем только при "
        "|Gм/Gф − 1| > 2 %."
    )
    return res
