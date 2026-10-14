"""Manual consumer fact edits (algorithm: «Источники данных…» → «Редактирование»).

Each meter cell of a consumer can be corrected by hand: choice of the meter block, a value, or
«не доверять прибору». Edits are keyed by Sys and applied to every fresh export.
"""

from dataclasses import dataclass, field, replace

from app.engine.model import BLOCK_FIELD, DISTRUST_FIELD, Consumer, Snapshot


@dataclass(frozen=True)
class ConsumerEdit:
    block: str | None = None  # "OT", "TS", "GVS", "SV"; None = by scheme
    overrides: dict[str, float | None] = field(default_factory=dict)  # Zulu field → value
    distrust: bool = False

    @property
    def empty(self) -> bool:
        return self.block is None and not self.overrides and not self.distrust


def apply_edits(snap: Snapshot, edits: dict[int, ConsumerEdit]) -> Snapshot:
    """A copy of the snapshot with the edits applied; the original is not changed."""
    consumers = []
    for c in snap.consumers:
        e = edits.get(c.sys)
        if e is None or e.empty:
            consumers.append(c)
            continue
        fields = {**c.fields, **e.overrides}
        if e.block:
            fields[BLOCK_FIELD] = e.block
        if e.distrust:
            fields[DISTRUST_FIELD] = True
        consumers.append(Consumer(sys=c.sys, guid=c.guid, scheme=c.scheme, fields=fields))
    return replace(snap, consumers=consumers)


def edited_cells(edits: dict[int, ConsumerEdit]) -> set[tuple[int, str]]:
    """(Sys, field) pairs to highlight; "block" and "distrust" stand for those choices."""
    cells = set()
    for sys, e in edits.items():
        cells.update((sys, name) for name in e.overrides)
        if e.block:
            cells.add((sys, "block"))
        if e.distrust:
            cells.add((sys, "distrust"))
    return cells
