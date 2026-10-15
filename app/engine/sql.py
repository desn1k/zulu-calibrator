"""Zulu SQL for the values to enter (docs/algorithm.md, example Чернышевского → «Внесение в Zulu»).

`UPDATE [<layer>] SET <Field> = <value> WHERE Sys = <sys>` (or `WHERE Sys IN (...)` when several
objects get the same value); CTP fields `WHERE Name = '<CTP name>'`. Decimal point, no SELECT.
Batch (default): `;` after every statement except the last — Zulu runs the block at once and a `;`
after the last statement is a syntax error. «По одной»: the same lines with no `;`.

Order inside the batch: a washer is cleared N first, then D; a washer is set D first, then N = 1.
A consumer row with Nshb_* = 1 and an empty D makes any UPDATE of that row fail («неверное значение
поля»): `Nshb_* = 0` is added to the first statement of that row.
"""

from dataclasses import dataclass

from app.engine.model import CTP_TARGET, Recommendation, Snapshot

DEFAULT_LAYER = "Актуальный_расчетный_2025"


def sql_value(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v == int(v) and abs(v) < 1e15:
            return str(int(v))
        return f"{v:.6f}".rstrip("0").rstrip(".")
    return "'" + str(v).replace("'", "''") + "'"


def is_n_field(field: str) -> bool:
    return field.startswith("Nshb_")


def order_key(r: Recommendation) -> int:
    """Clearing N first, then everything else, setting N = 1 last."""
    if is_n_field(r.field):
        return 0 if not r.enter else 2
    return 1


def broken_n_fields(fields: dict, setting: set[str]) -> list[str]:
    """Nshb_* = 1 with an empty D in the row, and the batch does not set that D."""
    out = []
    for name, value in fields.items():
        if not is_n_field(name) or value != 1:
            continue
        d_name = "D" + name[1:]
        if d_name in setting:
            continue
        d = fields.get(d_name)
        if d is None or d == 0:
            out.append(name)
    return sorted(out)


@dataclass(frozen=True)
class Statement:
    field: str
    value: object
    targets: tuple[str, ...]
    extra: tuple[str, ...] = ()  # «Nshb_* = 0» added for a broken row


def build_statements(rows: list[Recommendation], snap: Snapshot | None) -> list[Statement]:
    fields_of = {str(c.sys): c.fields for c in snap.consumers} if snap else {}
    setting: dict[str, set[str]] = {}
    for r in rows:
        if r.enter is not None and r.enter != 0:
            setting.setdefault(r.target, set()).add(r.field)
    fixes = {
        t: broken_n_fields(fields_of[t], setting.get(t, set()))
        for t in {r.target for r in rows}
        if t in fields_of
    }
    fixes = {t: f for t, f in fixes.items() if f}

    statements: list[Statement] = []
    groups: dict[tuple[str, str], int] = {}
    fixed: set[str] = set()
    for r in sorted(rows, key=order_key):  # stable: keeps the order inside each class
        target = r.target
        if target in fixes and target not in fixed:
            fixed.add(target)
            extra = tuple(f"{n} = 0" for n in fixes[target] if n != r.field)
            statements.append(Statement(r.field, r.enter, (target,), extra))
            continue
        if target == CTP_TARGET:
            statements.append(Statement(r.field, r.enter, (target,)))
            continue
        key = (r.field, sql_value(r.enter))
        i = groups.get(key)
        if i is None:
            groups[key] = len(statements)
            statements.append(Statement(r.field, r.enter, (target,)))
        else:
            s = statements[i]
            statements[i] = Statement(s.field, s.value, (*s.targets, target), s.extra)
    return statements


def statement_sql(s: Statement, layer: str, ctp_name: str) -> str:
    sets = ", ".join([f"{s.field} = {sql_value(s.value)}", *s.extra])
    if s.targets == (CTP_TARGET,):
        where = f"Name = {sql_value(ctp_name)}"
    elif len(s.targets) == 1:
        where = f"Sys = {s.targets[0]}"
    else:
        where = f"Sys IN ({', '.join(s.targets)})"
    # Text for the user to paste into Zulu — never executed by this app.
    return f"UPDATE [{layer}] SET {sets} WHERE {where}"  # noqa: S608


def sql_lines(
    rows: list[Recommendation], snap: Snapshot | None, layer: str, ctp_name: str
) -> list[str]:
    return [statement_sql(s, layer, ctp_name) for s in build_statements(rows, snap)]


def sql_text(lines: list[str], batch: bool = True) -> str:
    """Batch: `;` at the end of every line except the last. One by one: no `;` at all."""
    if not batch:
        return "\n".join(lines)
    return "\n".join(line + (";" if i < len(lines) - 1 else "") for i, line in enumerate(lines))
