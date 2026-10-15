"""Warnings after a verification run (traps of docs/algorithm.md and the 2026-10-15 examples).

- «Нет шайбы» на ЦТП = большой D (не меньше 2/3 Ду трубы) и N = 1; an empty D with N = 0 (or D = 0
  with N = 1) at the CTP inlet is taken by Zulu as a plug: all the head on the washer, flow ≈ 0
  (example Чернышевского, run 1).
- After every run: a washer field that changed between runs without being in the SQL of the step
  (example Береговая: Dshb_so_pod_u 39 disappeared between runs).
"""

import re
from collections.abc import Iterable

from app.engine.model import CTP_TARGET, CtpFact, Recommendation, Snapshot

PLUG_ADVICE = (
    "«Нет шайбы» на ЦТП = большой D (не меньше 2/3 Ду трубы) и N = 1; пустой D с N = 0 (или D = 0 "
    "с N = 1) Zulu считает заглушкой."
)
WASHER_FIELD = re.compile(r"^[DN]shb_\w+$|^Dsop_u$")


def empty(v) -> bool:
    return v is None or v == 0


def ctp_washer_plug(snap: Snapshot, fact: CtpFact) -> str | None:
    card = snap.card
    d, n = card.get("Dshb_pod_u"), card.get("Nshb_pod_u")
    by_fields = (empty(d) and n == 0 and card.get("Nshb_pod") == 1) or (d == 0 and n == 1)
    g_model, g_fact = snap.card_num("Gsum_pod"), fact.inlet.G1 if fact.inlet else None
    dh, h_ras = snap.card_num("dHshb_pod"), snap.card_num("H_ras")
    by_result = bool(
        g_model is not None
        and g_fact
        and g_model < 0.1 * g_fact
        and dh
        and h_ras
        and dh > 0.8 * h_ras
    )
    if not (by_fields or by_result):
        return None
    shown = f"Dshb_pod_u {'пусто' if d is None else d}, Nshb_pod_u {n}"
    result = (
        f"; в расчёте dHshb_pod {dh:g} м из {h_ras:g}, G ввода {g_model:g} т/ч" if by_result else ""
    )
    return f"Шайба ввода ЦТП — заглушка ({shown}{result}). {PLUG_ADVICE}"


def norm(v):
    return 0 if v is None else v


def unexpected_washer_changes(
    previous: Snapshot, current: Snapshot, issued: Iterable[Recommendation]
) -> list[str]:
    """Washer fields (D/N of washers, nozzle) that changed between two exports and were not in the
    recommendations of the step."""
    expected = {(r.target, r.field): norm(r.enter) for r in issued}
    out = []

    def check(target: str, label: str, before: dict, after: dict) -> None:
        for name in sorted(set(before) | set(after)):
            if not WASHER_FIELD.match(name):
                continue
            a, b = norm(before.get(name)), norm(after.get(name))
            if a == b:
                continue
            if (target, name) in expected and expected[(target, name)] == b:
                continue
            out.append(
                f"{label}: {name} было {a:g}, стало {b:g} — этой правки не было в SQL шага. "
                "Проверьте, что шайбы на месте."
            )

    check(CTP_TARGET, "ЦТП", previous.card, current.card)
    prev = {c.sys: c for c in previous.consumers}
    for c in current.consumers:
        p = prev.get(c.sys)
        if p is not None:
            check(str(c.sys), f"Sys {c.sys}", p.fields, c.fields)
    return out
