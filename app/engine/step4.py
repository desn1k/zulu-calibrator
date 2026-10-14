"""Step 4: heat of the heating houses — Kso only by explicit exception.

docs/algorithm.md: «Шаги 4–5 — тепло отопления домов и шайбы домов» → «Шаг 4 — варианты».
Default is variant А (no changes, report the heat deficit). With the «исключение Kso» flag:
variant Б, Kso_нов = Kso · Qфакт / Qмодель.
"""

from dataclasses import dataclass, field

from app.engine import config
from app.engine.meters import consumer_kind, meter_for
from app.engine.model import Recommendation, Snapshot, StepResult

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


def step4(snap: Snapshot, kso_exception: bool = False) -> Step4Result:
    res = Step4Result(step="4", do_not_touch=list(STEP4_DO_NOT_TOUCH))
    for c in snap.consumers:
        if consumer_kind(c.scheme) != "heating":
            continue
        m = meter_for(c)
        q_model = c.num("Q_sum")
        if m is None or not m.Q or not q_model:
            res.questions.append(f"Sys {c.sys}: нет тепла прибора или модели — не сравнить.")
            continue
        dev = (q_model / m.Q - 1.0) * 100.0
        res.heat_report.append(HeatDeviation(str(c.sys), q_model, m.Q, dev, m.from_inlet))

        if kso_exception:
            kso = c.num("Kso")
            if kso is None:
                res.questions.append(f"Sys {c.sys}: нет Kso.")
                continue
            new = round(kso * m.Q / q_model, config.ROUND_KSO)
            src = " (взят ввод)" if m.from_inlet else ""
            res.rows.append(
                Recommendation(
                    str(c.sys), "Kso", c.get("Kso"), new,
                    f"Вариант Б: Kso·Qфакт/Qмодель = {kso:g}·{m.Q:g}/{q_model:g}{src}",
                    note=KSO_EXCEPTION_NOTE,
                )
            )  # fmt: skip

    if res.heat_report:
        sm = sum(h.model for h in res.heat_report)
        sf = sum(h.fact for h in res.heat_report)
        res.notes.append(
            f"Тепло домов: Σ модель {sm:.3f} против Σ факт {sf:.3f} Гкал/ч "
            f"({(sm / sf - 1) * 100:+.1f} %)."
        )
    if kso_exception:
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
