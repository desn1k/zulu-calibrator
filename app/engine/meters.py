"""Meter blocks of consumers and meter checks 1–11.

docs/algorithm.md: «Входные данные и проверка приборов»,
«Источники данных, GUID и неполные приборы».
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from app.engine import config
from app.engine.model import Consumer, CtpFact

Kind = Literal["heating", "dhw", "vent"]

# «Какой блок брать»: DHW objects are schemes without heating.
DHW_ONLY_SCHEMES = frozenset({26, 27, 34, 46, 48})
VENT_ONLY_SCHEMES = frozenset({25})
BLOCK_KEYS = ("T1", "T2", "P1", "P2", "G1", "G2", "Q")


def consumer_kind(scheme: int) -> Kind:
    if scheme in DHW_ONLY_SCHEMES:
        return "dhw"
    if scheme in VENT_ONLY_SCHEMES:
        return "vent"
    return "heating"


@dataclass(frozen=True)
class Meter:
    block: str  # "OT", "TS", "GVS", "SV"
    T1: float | None = None
    T2: float | None = None
    P1: float | None = None
    P2: float | None = None
    G1: float | None = None
    G2: float | None = None
    Q: float | None = None
    from_inlet: bool = False  # heating object counted from the _TS block («взят ввод»)

    @property
    def draw_off(self) -> float | None:
        """G1 − G2 (missing return counts as 0, e.g. a dead-end DHW object)."""
        if self.G1 is None:
            return None
        return self.G1 - (self.G2 or 0.0)


def read_block(c: Consumer, block: str) -> dict[str, float | None]:
    return {k: c.num(f"{k}_{block}") for k in BLOCK_KEYS}


def meter_for(c: Consumer) -> Meter | None:
    """«Какой блок брать» — by scheme, not by the TS/OTOP/GVS flags."""
    kind = consumer_kind(c.scheme)
    if kind == "dhw":
        values = read_block(c, "GVS")
        return Meter("GVS", **values) if any(v is not None for v in values.values()) else None
    if kind == "vent":
        values = read_block(c, "SV")
        return Meter("SV", **values) if any(v is not None for v in values.values()) else None

    ot = read_block(c, "OT")
    if ot["G1"] is not None or ot["Q"] is not None:
        return Meter("OT", **ot)
    ts = read_block(c, "TS")
    if ts["G1"] is not None or ts["Q"] is not None:
        return Meter("TS", **ts, from_inlet=True)
    return None


def pct(value: float, reference: float) -> float:
    return (value - reference) / reference * 100.0


class Status(StrEnum):
    OK = "ok"
    NOTE = "note"  # not an error, explanation for the user
    FLAG = "flag"  # meter contradicts the balance; not a fitting target
    QUESTION = "question"  # the user decides
    NA = "n/a"


@dataclass
class Check:
    no: int
    title: str
    status: Status
    message: str = ""
    values: dict[str, Any] = field(default_factory=dict)


def unique_meters(consumers: list[Consumer], kind: Kind) -> list[tuple[Consumer, Meter]]:
    """Meters of one system type; a multi-input house (same GUID) counts its meter once."""
    seen: set[str] = set()
    out = []
    for c in consumers:
        if consumer_kind(c.scheme) != kind:
            continue
        m = meter_for(c)
        if m is None:
            continue
        if c.guid:
            key = f"{c.guid}:{kind}"
            if key in seen:
                continue
            seen.add(key)
        out.append((c, m))
    return out


def total(values) -> float:
    return sum(v for v in values if v is not None)


def meter_checks(
    fact: CtpFact, consumers: list[Consumer], card: dict[str, Any] | None = None
) -> list[Check]:
    """Checks 1–11, in the order of the algorithm. Nothing is changed, only reported."""
    inlet, heating, dhw, mode = fact.inlet, fact.heating, fact.dhw, fact.mode
    heat = unique_meters(consumers, "heating")
    hot = unique_meters(consumers, "dhw")
    checks: list[Check] = []

    # 1 Heat of CTP heating
    qso = None
    if heating and None not in (heating.G3, heating.T3, heating.T4):
        qso = heating.G3 * (heating.T3 - heating.T4) / 1000.0
        c = Check(1, "Тепло отопления ЦТП: Qсо = G3·(T3 − T4)/1000", Status.OK, values={"Qso": qso})
        if heating.Q is not None and abs(pct(heating.Q, qso)) > config.CHECK_HEAT_CLOSE_PCT:
            c.status = Status.FLAG
            c.message = (
                "Q прибора не сходится с G·ΔT (часто посчитано как G3·T3 − G4·T4 и завышено "
                "из-за разницы расходомеров) → брать G·ΔT."
            )
        checks.append(c)
    else:
        checks.append(Check(1, "Тепло отопления ЦТП", Status.NA, "нет прибора отопления"))

    # 2 Heat of CTP DHW
    qgv = None
    if dhw and None not in (dhw.Gp, dhw.Gc, dhw.Tgv, dhw.Tc):
        thv = mode.thv
        qgv = (dhw.Gp * (dhw.Tgv - thv) - dhw.Gc * (dhw.Tc - thv)) / 1000.0
        c = Check(2, "Тепло ГВС ЦТП: [Gп·(Tгв − Tхв) − Gц·(Tц − Tхв)]/1000", Status.OK)
        c.values = {"Qgv": qgv, "Thv": thv}
        if dhw.Q is not None and abs(pct(dhw.Q, qgv)) > config.CHECK_HEAT_CLOSE_PCT:
            c.status = Status.QUESTION
            c.message = "Не сходится с Q прибора ГВС — подобрать Tхв (обычно 5)."
        checks.append(c)
    else:
        checks.append(Check(2, "Тепло ГВС ЦТП", Status.NA, "нет прибора ГВС"))

    # 3 Inlet balance
    if inlet and inlet.Q is not None and qso is not None:
        expected = qso + (qgv or 0.0)
        dev = pct(inlet.Q, expected)
        ok = abs(dev) <= config.CHECK_INLET_BALANCE_PCT
        checks.append(
            Check(
                3,
                "Баланс ввода: Qввода vs Qсо + Qгв",
                Status.OK if ok else Status.FLAG,
                "" if ok else "Баланс не сходится — искать ложный прибор.",
                {"Q_inlet": inlet.Q, "Q_expected": expected, "deviation_pct": dev},
            )
        )
    else:
        checks.append(Check(3, "Баланс ввода", Status.NA, "не хватает приборов"))

    # 4 «Leak» of the second circuit
    if heating and None not in (heating.G3, heating.G4):
        ctp_leak = heating.G3 - heating.G4
        houses_leak = total(m.G1 - m.G2 for _, m in heat if None not in (m.G1, m.G2))
        c = Check(
            4,
            "«Утечка» 2 контура: G3 − G4 ЦТП vs Σ(G1 − G2) домов",
            Status.OK,
            values={"ctp_leak": ctp_leak, "houses_leak": houses_leak},
        )
        if ctp_leak > 0 and houses_leak < config.CHECK_LEAK_HOUSES_SHARE * ctp_leak:
            c.status = Status.FLAG
            c.message = (
                "Дома возвращают почти всё → это ошибка расходомера ЦТП, утечки не подгонять."
            )
        checks.append(c)
    else:
        checks.append(Check(4, "«Утечка» 2 контура", Status.NA, "нет прибора отопления"))

    # 5 CTP flows vs houses
    values: dict[str, Any] = {}
    flags = []
    if heating and heating.G3 is not None:
        s = total(m.G1 for _, m in heat)
        values.update(sum_heating_G1=s, heating_deviation_pct=pct(s, heating.G3))
        if abs(values["heating_deviation_pct"]) > config.CHECK_FLOWS_PCT:
            flags.append("отопление")
    if dhw and dhw.Gp is not None:
        s1 = total(m.G1 for _, m in hot)
        s2 = total(m.G2 for _, m in hot)
        values.update(sum_dhw_G1=s1, dhw_supply_deviation_pct=pct(s1, dhw.Gp))
        if abs(values["dhw_supply_deviation_pct"]) > config.CHECK_FLOWS_PCT:
            flags.append("подача ГВС")
        if dhw.Gc:
            values.update(sum_dhw_G2=s2, dhw_circ_deviation_pct=pct(s2, dhw.Gc))
            if abs(values["dhw_circ_deviation_pct"]) > config.CHECK_FLOWS_PCT:
                flags.append("циркуляция ГВС")
    checks.append(
        Check(
            5,
            "Расходы ЦТП vs дома (±3 %)",
            Status.FLAG if flags else (Status.OK if values else Status.NA),
            f"Не сходится: {', '.join(flags)} — отметить, какому прибору верим." if flags else "",
            values,
        )
    )

    # 6 Quarter network losses
    if qso:
        s = total(m.Q for _, m in heat)
        losses_pct = (qso - s) / qso * 100.0
        lo, hi = config.CHECK_LOSSES_PCT
        if losses_pct < 0:
            st, msg = Status.FLAG, "Отрицательные потери = ошибка прибора."
        elif lo <= losses_pct <= hi:
            st, msg = Status.OK, ""
        else:
            st, msg = Status.NOTE, f"Потери вне обычных {lo:g}–{hi:g} %."
        checks.append(
            Check(6, "Потери квартальной сети: Qсо − ΣQ домов", st, msg,
                  {"sum_heating_Q": s, "losses": qso - s, "losses_pct": losses_pct})
        )  # fmt: skip
    else:
        checks.append(Check(6, "Потери квартальной сети", Status.NA, "нет Qсо"))

    # 7 DHW draw-off
    if dhw and dhw.Gp is not None and dhw.Gc is not None:
        ctp_draw = dhw.Gp - dhw.Gc
        houses_draw = total(m.draw_off for _, m in hot)
        dev = pct(houses_draw, ctp_draw) if ctp_draw else None
        ok = dev is not None and abs(dev) <= config.CHECK_DRAW_OFF_PCT
        checks.append(
            Check(
                7,
                "Разбор ГВС: (Gп − Gц) ЦТП vs Σ(G1 − G2) ГВС-домов",
                Status.OK if ok else Status.QUESTION,
                "" if ok else "Разбор не сходится — кому верим (цель Kgv): ЦТП или домам?",
                {"ctp_draw_off": ctp_draw, "houses_draw_off": houses_draw, "deviation_pct": dev},
            )
        )
    else:
        checks.append(Check(7, "Разбор ГВС", Status.NA, "нет прибора ГВС"))

    # 8 DHW stages
    if inlet and heating and inlet.T2 is not None and heating.T4 is not None:
        two = inlet.T2 < heating.T4
        checks.append(
            Check(
                8,
                "Ступени ГВС: T2 ввода < T4 отопления",
                Status.OK if two else Status.NOTE,
                "Есть I ступень на обратке — схема двухступенчатая."
                if two
                else "I ступени на обратке нет — схема параллельная (или нет ГВС).",
                {"two_stage": two},
            )
        )
    else:
        checks.append(Check(8, "Ступени ГВС", Status.NA, "не хватает температур"))

    # 9 Main line
    if inlet and inlet.T1 is not None and mode.t_source is not None:
        hotter = mode.t_source < inlet.T1
        checks.append(
            Check(
                9,
                "Магистраль: T1 ввода vs t источника",
                Status.NOTE if hotter else Status.OK,
                "T1 > t источника → потери ≈ 0, разница = погрешность датчиков." if hotter else "",
                {"T1": inlet.T1, "t_source": mode.t_source},
            )
        )
    else:
        checks.append(Check(9, "Магистраль", Status.NA, "нет T1 ввода или t источника"))

    # 10 DHW house meters
    flagged = []
    for c, m in hot:
        bad = (
            (m.G1 is not None and m.G2 is not None and m.G2 > m.G1)
            or (m.P1 is not None and m.P2 is not None and m.P2 >= m.P1)
            or (m.T1 is not None and m.T2 is not None and m.T2 >= m.T1)
        )
        if bad:
            flagged.append(c.sys)
    checks.append(
        Check(
            10,
            "Приборы ГВС-домов: G2 ≤ G1, P2 < P1, Tц < Tгв",
            Status.FLAG if flagged else Status.OK,
            f"Нарушение у Sys {', '.join(map(str, flagged))} — цель не ставить." if flagged else "",
            {"flagged": flagged},
        )
    )

    # 11 Pressures
    ppod = card.get("Ppod") if card else None
    pobr = card.get("Pobr") if card else None
    if inlet and None not in (inlet.P1, inlet.P2, ppod, pobr):
        s_sup, s_ret = ppod - inlet.P1, pobr - inlet.P2
        same = abs(s_sup - s_ret) <= config.CHECK_PRESSURE_SAME_SHIFT_M
        checks.append(
            Check(
                11,
                "Давления: модель − факт на подаче и обратке",
                Status.NOTE if same else Status.OK,
                "Одинаковый сдвиг → отметка манометров / H_geo; в калибровку давления не вносить, "
                "Pcalibr не заполнять."
                if same
                else "",
                {"supply_shift": s_sup, "return_shift": s_ret},
            )
        )
    else:
        checks.append(Check(11, "Давления", Status.NA, "нет давлений"))

    return checks
