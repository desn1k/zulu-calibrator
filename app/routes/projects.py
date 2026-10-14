"""Pages of a CTP calculation: import, CTP fact, meter checks, steps 1–5, summary, history."""

from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.engine.criteria import CARD_RESULT_FIELDS, CONSUMER_RESULT_FIELDS
from app.engine.edits import ConsumerEdit, edited_cells
from app.engine.grouping import group_consumers, group_key, load_of
from app.engine.meters import BLOCK_KEYS, consumer_kind, meter_checks, meter_for
from app.engine.model import CtpFact, DhwFact, HeatingFact, InletFact, Mode
from app.engine.units import PressureUnit, pressure_to_m
from app.models import Project
from app.routes.pages import ru, templates
from app.services import projects as svc
from app.services.projects import STEP_TITLES, STEPS, StepError

router = APIRouter()

INLET_FIELDS = ["G1", "G2", "T1", "T2", "P1", "P2", "Q"]
HEATING_FIELDS = ["G3", "G4", "T3", "T4", "P3", "P4", "Q"]
DHW_FIELDS = ["Gp", "Gc", "Tgv", "Tc", "Pp", "Pc", "Q"]
FACT_BLOCKS = [
    ("inlet", "Ввод (теплосеть)", INLET_FIELDS),
    ("heating", "Отопление после ЦТП", HEATING_FIELDS),
    ("dhw", "ГВС ЦТП", DHW_FIELDS),
]
FIELD_LABELS = {"Gp": "Gп", "Gc": "Gц", "Tgv": "Tгв", "Tc": "Tц", "Pp": "Pп", "Pc": "Pц"}
BLOCKS = ["OT", "TS", "GVS", "SV"]


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.sessionmaker() as session:
        yield session


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(" ", "").replace(",", ".").replace("−", "-")
    if not text:
        return None
    try:
        return float(text)
    except ValueError as e:
        raise StepError(f"Не число: «{value}».", 400) from e


def load(session: Session, pid: int) -> Project:
    project = session.get(Project, pid)
    if project is None:
        raise HTTPException(404)
    return project


def url_of(project: Project, step: str | None = None) -> str:
    step = step or project.current_step
    if step in ("fact", "checks", "summary"):
        return f"/projects/{project.id}/{step}"
    return f"/projects/{project.id}/steps/{step}"


def redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def render(request: Request, name: str, status_code: int = 200, **ctx: Any) -> HTMLResponse:
    ctx.setdefault("step_titles", STEP_TITLES)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def nav(project: Project) -> list[dict[str, Any]]:
    return [
        {
            "step": s,
            "title": STEP_TITLES[s],
            "url": url_of(project, s),
            "open": svc.can_open(project, s),
            "current": s == project.current_step,
        }
        for s in STEPS
    ]


# ---------------------------------------------------------------- history and import


@router.get("/projects", response_class=HTMLResponse)
def history(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    rows = []
    for p in svc.list_projects(session):
        snap = svc.raw_snapshot(p)
        rows.append(
            {
                "project": p,
                "scheme": snap.card.get("N_schem") if snap else None,
                "step": STEP_TITLES[p.current_step],
                "iterations": len(p.iterations),
            }
        )
    return render(request, "history.html", rows=rows)


@router.get("/projects/new", response_class=HTMLResponse)
def new_project(request: Request) -> HTMLResponse:
    return render(request, "new.html")


@router.post("/projects")
async def create(request: Request, session: Session = Depends(get_session)) -> Response:
    form = await request.form()
    try:
        project = svc.create_project(session, str(form.get("payload") or ""))
    except StepError as e:
        return render(request, "new.html", status_code=e.status, error=str(e))
    return redirect(url_of(project, "fact"))


@router.get("/projects/{pid}")
def resume(pid: int, session: Session = Depends(get_session)) -> RedirectResponse:
    return redirect(url_of(load(session, pid)))


# ---------------------------------------------------------------- CTP fact


def fact_form_values(fact: CtpFact) -> dict[str, Any]:
    unit = fact.mode.pressure_unit
    values: dict[str, Any] = {}
    for block, _, names in FACT_BLOCKS:
        data = getattr(fact, block)
        values[f"{block}_missing"] = data is None
        for n in names:
            v = getattr(data, n) if data else None
            if v is not None and n.startswith("P") and unit is PressureUnit.KGF_CM2:
                v = v / 10.0
            values[f"{block}_{n}"] = v
    m = fact.mode
    values.update(
        mode_tnv=m.tnv, mode_t_source=m.t_source, mode_thv=m.thv,
        mode_data_type=m.data_type, mode_pressure_unit=str(m.pressure_unit),
    )  # fmt: skip
    return values


def fact_from_form(form: Any) -> CtpFact:
    unit = PressureUnit(form.get("mode_pressure_unit") or "m")
    blocks: dict[str, Any] = {}
    for block, _, names in FACT_BLOCKS:
        if form.get(f"{block}_missing"):
            blocks[block] = None
            continue
        values = {}
        for n in names:
            v = to_float(form.get(f"{block}_{n}"))
            values[n] = pressure_to_m(v, unit) if n.startswith("P") else v
        blocks[block] = values if any(v is not None for v in values.values()) else None
    data_type = "hour" if form.get("mode_data_type") == "hour" else "day"
    thv = to_float(form.get("mode_thv"))
    mode = Mode(
        tnv=to_float(form.get("mode_tnv")), t_source=to_float(form.get("mode_t_source")),
        thv=5.0 if thv is None else thv, data_type=data_type, pressure_unit=unit,
    )  # fmt: skip
    return CtpFact(
        inlet=InletFact(**blocks["inlet"]) if blocks["inlet"] else None,
        heating=HeatingFact(**blocks["heating"]) if blocks["heating"] else None,
        dhw=DhwFact(**blocks["dhw"]) if blocks["dhw"] else None,
        mode=mode,
    )


@router.get("/projects/{pid}/fact", response_class=HTMLResponse)
def fact_page(request: Request, pid: int, session: Session = Depends(get_session)) -> HTMLResponse:
    project = load(session, pid)
    return render(
        request, "fact.html", project=project, nav=nav(project), blocks=FACT_BLOCKS,
        labels=FIELD_LABELS, values=fact_form_values(svc.fact_of(project)),
    )  # fmt: skip


@router.post("/projects/{pid}/fact")
async def fact_save(
    request: Request, pid: int, session: Session = Depends(get_session)
) -> Response:
    project = load(session, pid)
    form = await request.form()
    try:
        fact = fact_from_form(form)
    except StepError as e:
        return render(
            request, "fact.html", status_code=e.status, project=project, nav=nav(project),
            blocks=FACT_BLOCKS, labels=FIELD_LABELS, values=dict(form), error=str(e),
        )  # fmt: skip
    svc.save_fact(session, project, fact)
    return redirect(url_of(project, "checks"))


# ---------------------------------------------------------------- meter checks, edits, shares


def default_block(scheme: int) -> str:
    return {"dhw": "GVS", "vent": "SV"}.get(consumer_kind(scheme), "OT")


def checks_context(project: Project, error: str = "") -> dict[str, Any]:
    raw = svc.raw_snapshot(project)
    snap = svc.effective_snapshot(project)
    edits = svc.edits_of(project)
    cells = edited_cells(edits)
    fact = svc.fact_of(project)

    consumers = []
    for raw_c, c in zip(raw.consumers, snap.consumers, strict=True):
        e = edits.get(c.sys, ConsumerEdit())
        auto = meter_for(raw_c)
        shown = e.block or (auto.block if auto else default_block(c.scheme))
        consumers.append(
            {
                "sys": c.sys,
                "scheme": c.scheme,
                "kind": consumer_kind(c.scheme),
                "guid": (c.guid or "")[:8],
                "block": e.block or "",
                "auto": auto.block if auto else "—",
                "shown": shown,
                "cells": [
                    (f"{k}_{shown}", k, c.get(f"{k}_{shown}"), (c.sys, f"{k}_{shown}") in cells)
                    for k in BLOCK_KEYS
                ],
                "distrust": e.distrust,
                "edited_block": (c.sys, "block") in cells,
            }
        )

    shares = svc.shares_of(project)
    groups = []
    for g in group_consumers(snap.consumers):
        if not g.multi_input:
            continue
        key = group_key(g)
        loads = {c.sys: load_of(c, g.kind) for c in g.members}
        total = sum(loads.values()) or 1.0
        stored = shares.get(key)
        groups.append(
            {
                "key": key,
                "kind": g.kind,
                "members": [
                    {
                        "sys": c.sys,
                        "load": loads[c.sys],
                        "share": (stored or {}).get(c.sys, loads[c.sys] / total) * 100.0,
                    }
                    for c in g.members
                ],
                "edited": stored is not None,
            }
        )

    return {
        "project": project,
        "nav": nav(project),
        "checks": meter_checks(fact, snap.consumers, snap.card),
        "consumers": consumers,
        "groups": groups,
        "blocks": BLOCKS,
        "error": error,
    }


@router.get("/projects/{pid}/checks", response_class=HTMLResponse)
def checks_page(request: Request, pid: int, session: Session = Depends(get_session)) -> Response:
    project = load(session, pid)
    if not svc.can_open(project, "checks"):
        return redirect(url_of(project))
    return render(request, "checks.html", **checks_context(project))


@router.post("/projects/{pid}/checks/edits")
async def checks_edits(
    request: Request, pid: int, session: Session = Depends(get_session)
) -> Response:
    project = load(session, pid)
    form = await request.form()
    raw = svc.raw_snapshot(project)
    existing = svc.edits_of(project)
    edits: dict[int, ConsumerEdit] = {}
    try:
        for c in raw.consumers:
            shown = form.get(f"{c.sys}:shown")
            if shown is None:
                continue  # this consumer was not on the submitted form
            old = existing.get(c.sys, ConsumerEdit())
            overrides = {k: v for k, v in old.overrides.items() if not k.endswith(f"_{shown}")}
            for k in BLOCK_KEYS:
                name = f"{k}_{shown}"
                if f"{c.sys}:{name}" not in form:
                    if name in old.overrides:
                        overrides[name] = old.overrides[name]
                    continue
                value = to_float(form.get(f"{c.sys}:{name}"))
                original = c.num(name)
                same = (value is None and original is None) or (
                    value is not None and original is not None and abs(value - original) < 1e-9
                )
                if not same:
                    overrides[name] = value
            block = str(form.get(f"{c.sys}:block") or "") or None
            if block is not None and block not in BLOCKS:
                raise StepError(f"Неизвестный блок прибора: {block}.", 400)
            edits[c.sys] = ConsumerEdit(
                block=block, overrides=overrides, distrust=bool(form.get(f"{c.sys}:distrust"))
            )
    except StepError as e:
        return render(
            request, "checks.html", status_code=e.status, **checks_context(project, str(e))
        )
    svc.save_edits(session, project, edits)
    return redirect(url_of(project, "checks"))


@router.post("/projects/{pid}/checks/shares")
async def checks_shares(
    request: Request, pid: int, session: Session = Depends(get_session)
) -> Response:
    project = load(session, pid)
    form = await request.form()
    snap = svc.effective_snapshot(project)
    stored = dict((project.settings or {}).get("shares") or {})
    try:
        for g in group_consumers(snap.consumers):
            if not g.multi_input:
                continue
            values = {c.sys: to_float(form.get(f"share:{c.sys}")) for c in g.members}
            if any(v is None for v in values.values()):
                raise StepError("Укажите долю каждого ввода.", 400)
            total = sum(values.values())
            if abs(total - 100.0) > 0.1:
                raise StepError(f"Сумма долей должна быть 100 % (сейчас {total:g} %).", 400)
            stored[group_key(g)] = {str(s): v / 100.0 for s, v in values.items()}
    except StepError as e:
        return render(
            request, "checks.html", status_code=e.status, **checks_context(project, str(e))
        )
    svc.update_settings(session, project, shares=stored)
    return redirect(url_of(project, "checks"))


@router.post("/projects/{pid}/checks/next")
def checks_next(pid: int, session: Session = Depends(get_session)) -> RedirectResponse:
    project = load(session, pid)
    svc.leave_checks(session, project)
    return redirect(url_of(project))


# ---------------------------------------------------------------- steps 1–5


def copy_text(rows) -> str:
    """«Копировать»: Sys / field / value, tab-separated, one row per line."""
    return "\n".join(f"{r.target}\t{r.field}\t{ru(r.enter)}" for r in rows)


def step_page(
    request: Request, project: Project, step: str, error: str = "", status_code: int = 200
):
    view = svc.compute_step(project, step)
    states = {s.step: s for s in project.step_states}
    return render(
        request, "step.html", status_code=status_code, project=project, nav=nav(project),
        step=step, title=STEP_TITLES[step], view=view, settings=svc.step_view(project),
        copy=copy_text(view.result.rows) if view.result else "",
        is_current=step == project.current_step, state=states.get(step), error=error,
        iterations=project.iterations,
    )  # fmt: skip


def check_step(step: str) -> None:
    if step not in svc.CALC_STEPS:
        raise HTTPException(404)


@router.get("/projects/{pid}/steps/{step}", response_class=HTMLResponse)
def step_get(
    request: Request, pid: int, step: str, session: Session = Depends(get_session)
) -> Response:
    check_step(step)
    project = load(session, pid)
    if not svc.can_open(project, step):
        return redirect(url_of(project))
    return step_page(request, project, step)


@router.post("/projects/{pid}/steps/{step}/import")
async def step_import(
    request: Request, pid: int, step: str, session: Session = Depends(get_session)
) -> Response:
    check_step(step)
    project = load(session, pid)
    form = await request.form()
    try:
        svc.add_iteration(session, project, str(form.get("payload") or ""), step)
    except StepError as e:
        return step_page(request, project, step, str(e), e.status)
    return redirect(url_of(project, step))


@router.post("/projects/{pid}/steps/{step}/settings")
async def step_settings(
    request: Request, pid: int, step: str, session: Session = Depends(get_session)
) -> Response:
    check_step(step)
    project = load(session, pid)
    form = await request.form()
    try:
        if step == "1":
            svc.update_settings(
                session, project,
                t22_niz=to_float(form.get("t22_niz")), t12_verh=to_float(form.get("t12_verh")),
            )  # fmt: skip
        elif step == "4":
            svc.update_settings(session, project, kso_exception=bool(form.get("kso_exception")))
    except StepError as e:
        return step_page(request, project, step, str(e), e.status)
    return redirect(url_of(project, step))


@router.post("/projects/{pid}/steps/{step}/advance")
def step_advance(
    request: Request, pid: int, step: str, session: Session = Depends(get_session)
) -> Response:
    check_step(step)
    project = load(session, pid)
    try:
        svc.advance(session, project, step)
    except StepError as e:
        return step_page(request, project, step, str(e), e.status)
    return redirect(url_of(project))


@router.post("/projects/{pid}/steps/{step}/accept")
async def step_accept(
    request: Request, pid: int, step: str, session: Session = Depends(get_session)
) -> Response:
    check_step(step)
    project = load(session, pid)
    form = await request.form()
    try:
        svc.accept_with_deviation(session, project, step, str(form.get("comment") or ""))
    except StepError as e:
        return step_page(request, project, step, str(e), e.status)
    return redirect(url_of(project))


# ---------------------------------------------------------------- summary and iterations


@router.get("/projects/{pid}/summary", response_class=HTMLResponse)
def summary(request: Request, pid: int, session: Session = Depends(get_session)) -> Response:
    project = load(session, pid)
    if not svc.can_open(project, "summary"):
        return redirect(url_of(project))
    rows, seen = [], set()
    for step in svc.CALC_STEPS:
        for c in svc.compute_step(project, step).criteria:
            if c.key not in seen:
                seen.add(c.key)
                rows.append(c)
    return render(
        request, "summary.html", project=project, nav=nav(project), rows=rows,
        states=project.step_states,
    )  # fmt: skip


@router.get("/projects/{pid}/iterations/{number}", response_class=HTMLResponse)
def iteration(
    request: Request, pid: int, number: int, session: Session = Depends(get_session)
) -> HTMLResponse:
    project = load(session, pid)
    its = [it for it in project.iterations if it.number == number]
    if not its:
        raise HTTPException(404)
    snap = svc.snapshot_from_dict(its[0].snapshot)
    return render(
        request, "iteration.html", project=project, it=its[0], snap=snap,
        card_fields=[k for k in CARD_RESULT_FIELDS if k in snap.card],
        consumer_fields=CONSUMER_RESULT_FIELDS,
    )  # fmt: skip
