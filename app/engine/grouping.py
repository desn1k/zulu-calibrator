"""GUID grouping and multi-input split.

docs/algorithm.md: «Источники данных, GUID и неполные приборы» → «GUID».
"""

from dataclasses import dataclass, replace

from app.engine.meters import Kind, Meter, consumer_kind, meter_for
from app.engine.model import Consumer


@dataclass
class Group:
    guid: str | None
    kind: Kind
    members: list[Consumer]

    @property
    def multi_input(self) -> bool:
        """Several objects of one type under one GUID: one undivided meter per house."""
        return len(self.members) > 1


def group_consumers(consumers: list[Consumer]) -> list[Group]:
    """Group = GUID + system type. Different types under one GUID are different systems."""
    groups: dict[tuple[str, Kind], Group] = {}
    for c in consumers:
        kind = consumer_kind(c.scheme)
        key = (c.guid or f"sys:{c.sys}", kind)
        if key not in groups:
            groups[key] = Group(guid=c.guid, kind=kind, members=[])
        groups[key].members.append(c)
    return list(groups.values())


def load_of(c: Consumer, kind: Kind) -> float:
    if kind == "dhw":
        return (c.num("Qgv_sred") or 0.0) * (c.num("Kgv") or 1.0)
    if kind == "vent":
        return c.num("Qsv_r") or 0.0
    return c.num("Qo_r") or 0.0


def split_multi_input(group: Group, shares: dict[int, float] | None = None) -> dict[int, Meter]:
    """G_i = G · Qo_r,i / ΣQo_r (DHW: by Qgv_sred·Kgv); Q the same; T and P common.

    `shares` lets the user correct the split by hand.
    """
    meter = next((m for m in (meter_for(c) for c in group.members) if m is not None), None)
    if meter is None:
        return {}
    if shares is None:
        loads = {c.sys: load_of(c, group.kind) for c in group.members}
        total = sum(loads.values())
        n = len(group.members)
        shares = {s: (v / total if total else 1.0 / n) for s, v in loads.items()}

    def part(value: float | None, share: float) -> float | None:
        return None if value is None else value * share

    return {
        c.sys: replace(
            meter,
            G1=part(meter.G1, shares[c.sys]),
            G2=part(meter.G2, shares[c.sys]),
            Q=part(meter.Q, shares[c.sys]),
        )
        for c in group.members
    }


def duplicate_facts(consumers: list[Consumer]) -> list[tuple[int, int]]:
    """Identical meter values under different GUIDs — «похоже на ошибку выгрузки»."""
    seen: dict[tuple, Consumer] = {}
    pairs = []
    for c in consumers:
        m = meter_for(c)
        if m is None or m.G1 is None:
            continue
        key = (m.block, m.G1, m.G2, m.T1, m.T2, m.Q)
        other = seen.get(key)
        if other is not None and other.guid != c.guid:
            pairs.append((other.sys, c.sys))
        else:
            seen[key] = c
    return pairs


Shares = dict[str, dict[int, float]]  # group key → {Sys: share}, user-edited split


def group_key(group: Group) -> str:
    return f"{group.guid}:{group.kind}"


def house_meters(
    consumers: list[Consumer], shares: Shares | None = None
) -> dict[int, Meter | None]:
    """Meter per consumer: the split meter for a multi-input house, its own meter otherwise."""
    out: dict[int, Meter | None] = {}
    for g in group_consumers(consumers):
        if g.multi_input:
            split = split_multi_input(g, (shares or {}).get(group_key(g)))
            for c in g.members:
                out[c.sys] = split.get(c.sys)
        else:
            for c in g.members:
                out[c.sys] = meter_for(c)
    return out
