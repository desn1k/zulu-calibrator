"""Projects, iterations and the step state machine (DB side; the numbers come from app/engine)."""

import json
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.engine.criteria import (
    criteria_step1,
    criteria_step2,
    criteria_step3,
    criteria_step4,
    criteria_step5,
    results_identical,
)
from app.engine.edits import ConsumerEdit, apply_edits
from app.engine.grouping import Shares
from app.engine.model import Criterion, CtpFact, Snapshot, StepResult
from app.engine.parsers import ParsedInput, ParseError, parse_upload
from app.engine.step1 import step1
from app.engine.step2 import step2
from app.engine.step3 import step3
from app.engine.step4 import step4
from app.engine.step5 import step5
from app.models import ConsumerEditRow, Iteration, Project, StepState
from app.services.serialize import (
    fact_from_dict,
    fact_to_dict,
    snapshot_from_dict,
    snapshot_to_dict,
)

# intake → fact → meter checks → 1 → 2 → 3 → 4 → 5 → summary
STEPS = ["fact", "checks", "1", "2", "3", "4", "5", "summary"]
CALC_STEPS = ["1", "2", "3", "4", "5"]
STEP_TITLES = {
    "fact": "Факт ЦТП",
    "checks": "Проверка приборов",
    "1": "Шаг 1 — схема ЦТП, ТО отопления, ступени ГВС, Kgv",
    "2": "Шаг 2 — циркуляция ГВС домов",
    "3": "Шаг 3 — шайба ввода ЦТП",
    "4": "Шаг 4 — тепло отопления домов (Kso по исключению)",
    "5": "Шаг 5 — шайбы домов",
    "summary": "Итог",
}

STATUS_IN_WORK = "в работе"
STATUS_DONE = "завершён"
STATUS_DONE_WITH_DEVIATIONS = "принят с отклонениями"


class StepError(Exception):
    """A state-machine rule was broken; `status` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


def parse_payload(payload: str, previous: Snapshot | None = None) -> ParsedInput:
    """Data sent by app/static/import.js: Zulu card + consumers, or the old calculator export."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as e:
        raise StepError("Данные импорта не прочитаны — выберите файл ещё раз.", 400) from e
    if not isinstance(data, dict):
        raise StepError("Данные импорта не прочитаны — выберите файл ещё раз.", 400)
    try:
        return parse_upload(data, previous)  # private fields are dropped here
    except ParseError as e:
        raise StepError(str(e), 400) from e


def create_project(session: Session, payload: str) -> Project:
    parsed = parse_payload(payload)
    snap = parsed.snapshot
    fact = parsed.fact or CtpFact(inlet=None, heating=None, dhw=None)
    project = Project(
        ctp_name=snap.ctp_name or "ЦТП без имени",
        measured_on=snap.measured_on,
        status=STATUS_IN_WORK,
        current_step="fact",
        fact=fact_to_dict(fact),
        settings={},
    )
    project.iterations.append(Iteration(number=1, step="intake", snapshot=snapshot_to_dict(snap)))
    session.add(project)
    session.commit()
    return project


def add_iteration(session: Session, project: Project, payload: str, step: str) -> Iteration:
    if step != project.current_step:
        raise StepError("Свежую выгрузку можно загрузить только на открытом шаге.")
    previous = raw_snapshot(project)
    snap = parse_payload(payload, previous).snapshot
    it = Iteration(
        number=len(project.iterations) + 1,
        step=step,
        snapshot=snapshot_to_dict(snap),
        identical_to_previous=previous is not None and results_identical(previous, snap),
    )
    project.iterations.append(it)
    session.commit()
    return it


def raw_snapshot(project: Project, offset: int = 0) -> Snapshot | None:
    """Latest (offset 0) or an earlier export, without manual edits."""
    if len(project.iterations) <= offset:
        return None
    return snapshot_from_dict(project.iterations[-1 - offset].snapshot)


def edits_of(project: Project) -> dict[int, ConsumerEdit]:
    return {
        e.sys: ConsumerEdit(block=e.block, overrides=dict(e.overrides), distrust=e.distrust)
        for e in project.edits
    }


def shares_of(project: Project) -> Shares:
    stored = (project.settings or {}).get("shares") or {}
    return {key: {int(s): float(v) for s, v in group.items()} for key, group in stored.items()}


def effective_snapshot(project: Project, offset: int = 0) -> Snapshot | None:
    snap = raw_snapshot(project, offset)
    return apply_edits(snap, edits_of(project)) if snap else None


def fact_of(project: Project) -> CtpFact:
    return fact_from_dict(project.fact)


def update_settings(session: Session, project: Project, **values: Any) -> None:
    project.settings = {**(project.settings or {}), **values}  # new dict → change is tracked
    session.commit()


def save_fact(session: Session, project: Project, fact: CtpFact) -> None:
    project.fact = fact_to_dict(fact)
    if project.current_step == "fact":
        project.current_step = "checks"
    session.commit()


def save_edits(session: Session, project: Project, edits: dict[int, ConsumerEdit]) -> None:
    rows = {e.sys: e for e in project.edits}
    for sys, e in edits.items():
        row = rows.get(sys)
        if e.empty:
            if row is not None:
                project.edits.remove(row)
            continue
        if row is None:
            row = ConsumerEditRow(sys=sys)
            project.edits.append(row)
        row.block, row.overrides, row.distrust = e.block, dict(e.overrides), e.distrust
    session.commit()


def can_open(project: Project, step: str) -> bool:
    return STEPS.index(step) <= STEPS.index(project.current_step)


@dataclass
class StepView:
    step: str
    result: StepResult | None
    criteria: list[Criterion] = field(default_factory=list)
    identical: bool = False
    iteration: Iteration | None = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)  # import warnings of the latest export

    @property
    def passed(self) -> bool:
        return self.result is not None and all(c.passed for c in self.criteria)


def step_view(project: Project) -> dict[str, Any]:
    settings = project.settings or {}
    return {
        "t22_niz": settings.get("t22_niz"),
        "t12_verh": settings.get("t12_verh"),
        "kso_exception": bool(settings.get("kso_exception")),
    }


def compute_step(project: Project, step: str) -> StepView:
    """Recommendations from the latest export (with manual edits) and the step criteria on it."""
    snap = effective_snapshot(project)
    if snap is None:
        return StepView(step, None, message="Нет выгрузки.")
    fact, shares, s = fact_of(project), shares_of(project), step_view(project)
    last = project.iterations[-1]
    view = StepView(step, None, identical=last.identical_to_previous, iteration=last)
    view.warnings = list(snap.warnings)
    try:
        if step == "1":
            view.result = step1(snap, fact, s["t22_niz"], s["t12_verh"])
            view.criteria = criteria_step1(snap, fact)
        elif step == "2":
            view.result = step2(snap)
            view.criteria = criteria_step2(snap, previous=effective_snapshot(project, 1), fact=fact)
        elif step == "3":
            view.result = step3(snap, fact)
            view.criteria = criteria_step3(snap, fact)
        elif step == "4":
            view.result = step4(snap, kso_exception=s["kso_exception"], shares=shares)
            # Variant А changes nothing, so there is nothing to check.
            view.criteria = criteria_step4(snap, shares) if s["kso_exception"] else []
        elif step == "5":
            view.result = step5(snap, fact, shares)
            view.criteria = criteria_step5(snap, fact, shares)
    except (TypeError, ValueError, ZeroDivisionError):
        view.result = None
        view.message = "Не хватает данных факта ЦТП для расчёта — проверьте страницу «Факт ЦТП»."
    return view


def next_step(step: str) -> str:
    return STEPS[STEPS.index(step) + 1]


def finish_step(session: Session, project: Project, step: str, status: str, comment: str) -> None:
    states = {s.step: s for s in project.step_states}
    state = states.get(step)
    if state is None:
        state = StepState(step=step, status=status, comment=comment)
        project.step_states.append(state)
    else:
        state.status, state.comment = status, comment
    project.current_step = next_step(step)
    if project.current_step == "summary":
        accepted = any(s.status == "accepted" for s in project.step_states)
        project.status = STATUS_DONE_WITH_DEVIATIONS if accepted else STATUS_DONE
    session.commit()


def advance(session: Session, project: Project, step: str) -> None:
    if step != project.current_step:
        raise StepError("Этот шаг не открыт.")
    view = compute_step(project, step)
    if not view.passed:
        raise StepError(
            "Критерии шага не сошлись: внесите правки в Zulu, сделайте поверочный расчёт и "
            "загрузите свежую выгрузку — или «принять с отклонением» с комментарием."
        )
    finish_step(session, project, step, "passed", "")


def accept_with_deviation(session: Session, project: Project, step: str, comment: str) -> None:
    if step != project.current_step:
        raise StepError("Этот шаг не открыт.")
    if not comment.strip():
        raise StepError("Комментарий обязателен для «принять с отклонением».", 400)
    finish_step(session, project, step, "accepted", comment.strip())


def leave_checks(session: Session, project: Project) -> None:
    if project.current_step == "checks":
        project.current_step = "1"
        session.commit()


def list_projects(session: Session) -> list[Project]:
    return list(
        session.scalars(select(Project).order_by(Project.updated_at.desc(), Project.id.desc()))
    )
