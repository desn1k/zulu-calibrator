"""Step 4: heat of the heating houses — Kso only by explicit exception.

docs/algorithm.md: «Шаги 4–5 — тепло отопления домов и шайбы домов» → «Шаг 4 — варианты»,
«Порядок 4 и 5», examples Чернышевского, Береговая, Верхняя, Пионерская.
Default is variant А (no changes, report the heat deficit). With the «исключение Kso» flag:
variant Б, Kso_нов = Kso · Qфакт / Qмодель — for a metered building by its meter (a multi-input
building by its one meter, one Kso per building), for the unmetered buildings by one factor
k = (Q_heating − Σ Q_metered − network loss) / Σ Q_model of the unmetered ones.
"""

from dataclasses import dataclass, field

from app.engine import config
from app.engine.model import DISTRUST_FIELD, Consumer, Recommendation, Snapshot, StepResult
from app.engine.targets import HeatingTargets, KsoFactor, heat_targets, model_heat

KSO_EXCEPTION_NOTE = "нагрузка в модели ≠ договорной"

STEP4_DO_NOT_TOUCH = [
    "Qo_r",
    "T1_r / T3_r / T2_r домов (вариант В ломает наладочный расчёт)",
    "шайбы домов (шаг 5)",
]


@dataclass(frozen=True)
class HeatDeviation:
    target: str
    model: float
    fact: float
    deviation_pct: float
    from_inlet: bool


@dataclass
class Step4Result(StepResult):
    heat_report: list[HeatDeviation] = field(default_factory=list)
    unmetered_factor: float | None = None
    washers_first: bool = False  # «Порядок 4 и 5»: house flows off by > 20 %


def one_kso(members: list[Consumer], factor: float) -> dict[int, float]:
    """One Kso per building: Kso_new = factor · ΣQ / Σ(Q/Kso) (= Kso·factor when the inputs have
    the same Kso)."""
    q = {c.sys: model_heat(c) or 0.0 for c in members}
    kso = {c.sys: c.num("Kso") or 1.0 for c in members}
    if len(set(kso.values())) == 1:
        return {s: k * factor for s, k in kso.items()}
    base = sum(q[s] / kso[s] for s in q)
    value = factor * sum(q.values()) / base if base else factor
    return dict.fromkeys(q, value)


def max_flow_deviation(snap: Snapshot, targets: HeatingTargets) -> float | None:
    devs = [
        abs(snap.consumer(s).num("Gso") / t.g - 1.0) * 100.0
        for s, t in targets.flows.items()
        if t.g and snap.consumer(s).num("Gso")
    ]
    return max(devs) if devs else None


def step4(
    snap: Snapshot,
    targets: HeatingTargets,
    kso_exception: bool = False,
    q_heating: float | None = None,
    loss: float | None = None,
    base: Snapshot | None = None,
) -> Step4Result:
    """`targets` — flow targets (groups, unmetered); `q_heating` — heat of the CTP heating to close
    the unmetered factor to; `loss` — network loss; `base` — the first export (Kso before
    calibration) for the cross-check of the unmetered factor."""
    res = Step4Result(step="4", do_not_touch=list(STEP4_DO_NOT_TOUCH))
    by_sys = {c.sys: c for c in snap.consumers}
    heat = heat_targets(targets, q_heating, loss)
    res.notes.extend(heat.notes)

    dev = max_flow_deviation(snap, targets)
    if dev is not None and dev > config.STEPS_5_BEFORE_4_PCT:
        res.washers_first = True
        msg = (
            f"Расходы домов врут до {dev:.0f} % (> {config.STEPS_5_BEFORE_4_PCT:g} %) — сначала "
            "шаг 5 (шайбы), потом шаг 4: Kso, посчитанный при неверном расходе, уедет после шайб."
        )
        if snap.card.get("Regul_T") == 1:
            msg += " На ЦТП регулятор температуры (Regul_T = 1): тепло от расхода не зависит, Kso "
            msg += "можно считать и до шайб."
        res.notes.append(msg)

    rows: list[Recommendation] = []
    for f in heat.metered:
        members = [by_sys[s] for s in f.members]
        if any(c.get(DISTRUST_FIELD) for c in members):
            res.notes.append(
                f"Sys {', '.join(map(str, f.members))}: прибор «не доверять» — пропущен."
            )
            continue
        label = "/".join(map(str, f.members))
        res.heat_report.append(
            HeatDeviation(label, f.q_model, f.q_fact, (f.q_model / f.q_fact - 1) * 100.0,
                          f.from_inlet)
        )  # fmt: skip
        if kso_exception:
            rows.extend(kso_rows(members, f, unmetered=False))

    k = heat.unmetered_factor
    if k is not None:
        res.unmetered_factor = k.factor
        members = [by_sys[s] for s in k.members]
        res.heat_report.append(
            HeatDeviation("без приборов", k.q_model, k.q_fact,
                          (k.q_model / k.q_fact - 1) * 100.0, False)
        )  # fmt: skip
        cross_check(res, heat.metered, k, by_sys, base)
        if kso_exception:
            for g in group_by_guid(members):
                rows.extend(kso_rows(g, k, unmetered=True))
    elif targets.unmetered:
        res.questions.append(
            "Дома без приборов: нет тепла отопления ЦТП для общего множителя k — не сравнить."
        )

    if res.heat_report:
        sm = sum(h.model for h in res.heat_report)
        sf = sum(h.fact for h in res.heat_report)
        res.notes.append(
            f"Тепло домов: Σ модель {sm:.3f} против Σ факт {sf:.3f} Гкал/ч "
            f"({(sm / sf - 1) * 100:+.1f} %)."
        )
    if kso_exception:
        res.rows.extend(rows)
        res.notes.append(
            "Kso подгоняет одну точку Tнв; расчётный расход дома растёт → нужен шаг 5. "
            "Проверяется только вторым замером."
        )
    else:
        res.notes.append(
            "Вариант А (по умолчанию): ничего не менять, недобор тепла остаётся. "
            "Kso меняется только с флажком «исключение Kso»."
        )
    return res


def group_by_guid(members: list[Consumer]) -> list[list[Consumer]]:
    groups: dict[str, list[Consumer]] = {}
    for c in members:
        groups.setdefault(c.guid or f"sys:{c.sys}", []).append(c)
    return list(groups.values())


def kso_rows(members: list[Consumer], f: KsoFactor, unmetered: bool) -> list[Recommendation]:
    out = []
    for sys, value in one_kso(members, f.factor).items():
        c = next(c for c in members if c.sys == sys)
        kso = c.num("Kso") or 1.0
        new = round(value, config.ROUND_KSO)
        if c.num("Kso") is not None and round(kso, config.ROUND_KSO) == new:
            continue
        reason = (
            f"Дома без приборов: Kso·k = {kso:g}·{f.factor:.4f}"
            if unmetered
            else f"Вариант Б: Kso·Qфакт/Qмодель = {kso:g}·{f.q_fact:g}/{f.q_model:.4f}"
        )
        if len(members) > 1:
            reason += " (один Kso на дом)"
        if f.from_inlet:
            reason += " (взят ввод)"
        out.append(Recommendation(str(sys), "Kso", c.get("Kso"), new, reason,
                                  note=KSO_EXCEPTION_NOTE))  # fmt: skip
    return out


def cross_check(
    res: Step4Result,
    metered: list[KsoFactor],
    k: KsoFactor,
    by_sys: dict[int, Consumer],
    base: Snapshot | None,
) -> None:
    """The unmetered factor is cross-checked with the factor the metered buildings needed."""
    if not metered:
        return
    base_kso = {c.sys: c.num("Kso") for c in base.consumers} if base else {}

    def total_factor(sys: int, now: float) -> float:
        b = base_kso.get(sys)
        kso = by_sys[sys].num("Kso")
        return now * kso / b if b and kso else now

    met = sorted(total_factor(f.members[0], f.factor) for f in metered)
    unm = total_factor(k.members[0], k.factor)
    res.notes.append(
        f"Проверка: дома с приборами ×{met[0]:.3f}…×{met[-1]:.3f}, дома без приборов "
        f"×{unm:.3f}" + (" (к исходному Kso)." if base else ".")
    )
