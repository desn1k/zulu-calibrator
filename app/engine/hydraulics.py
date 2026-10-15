"""Heads and washers of the houses behind a CTP (G t/h, H m, d mm).

docs/algorithm.md: «Шаги 4–5» (order, two H(G) points at the CTP inlet), «Давления второго
контура» п. 3 (head at a house when the flow changes, house resistance without washers),
examples Чернышевского, Береговая, Верхняя, Пионерская.
"""

from dataclasses import dataclass

from app.engine import config


def washer_dh(g: float, d: float) -> float:
    """Head a consumer washer takes: ΔH = G²/(d/10)⁴ — exact in Zulu for house washers."""
    return g**2 / (d / 10.0) ** 4


def washer_d(g: float, dh: float) -> float:
    """d = 10·(G²/ΔH)^¼."""
    return 10.0 * (g**2 / dh) ** 0.25


@dataclass(frozen=True)
class HeadLine:
    """H = c − k·G² through two runs (H of a point vs the total flow through it)."""

    c: float
    k: float

    def at(self, g: float) -> float:
        return self.c - self.k * g**2


def head_line(g1: float, h1: float, g2: float, h2: float) -> HeadLine | None:
    """Two points H(G); None when the flows are too close to tell a slope."""
    if abs(g1 - g2) / max(g1, g2) * 100.0 < config.HEAD_POINTS_MIN_DG_PCT:
        return None
    k = (h2 - h1) / (g1**2 - g2**2)
    return HeadLine(c=h2 + k * g2**2, k=k)


def house_head(
    h_house: float, p_out_now: float, p_out_new: float, g_now: float, g_target: float
) -> float:
    """«Давления второго контура» п. 3: H_new = ΔP_выход,new − (ΔP_выход − H)·(G_цель/G)².

    The network loss from the CTP outlet to the house scales with the square of the total flow.
    """
    return p_out_new - (p_out_now - h_house) * (g_target / g_now) ** 2


@dataclass(frozen=True)
class WasherSizing:
    d: float | None  # mm, rounded; None = cannot be reached with a washer
    dh: float  # head the washer must take at the target flow, m
    s: float  # resistance of the house without washers, m/(t/h)²
    note: str = ""


def size_washer(
    h_new: float, h_ras: float, dh_washers_now: float, g_model: float, g_target: float
) -> WasherSizing:
    """S = (H_ras − ΔHшайб)/G_модели², ΔHш = H_new − S·G_цель², d = 10·(G_цель²/ΔHш)^¼."""
    s = (h_ras - dh_washers_now) / g_model**2
    dh = h_new - s * g_target**2
    if dh <= 0:
        return WasherSizing(None, dh, s, "напора не хватает и без шайбы")
    d = round(washer_d(g_target, dh), config.ROUND_D)
    if d < config.MIN_WASHER_MM:
        return WasherSizing(
            config.MIN_WASHER_MM, dh, s, f"диаметр меньше {config.MIN_WASHER_MM:g} мм"
        )
    return WasherSizing(d, dh, s)
