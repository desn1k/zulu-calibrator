"""Step 2: DHW circulation of the houses (algorithm «Шаг 2»)."""

import pytest

from app.engine.model import Consumer, Snapshot
from app.engine.step2 import step2

from .conftest import by_target, imported

KCIRC_FORMULA = {"33551": 612, "33561": 200, "33569": 564, "33573": 796, "33575": 520}
HCIRC = {"33551": 19.4, "33561": 19.6, "33569": 18.5, "33573": 18.9, "33575": 18.0}


def test_kcirc_golden_from_it2() -> None:
    res = step2(imported("it2_step1a").snapshot)
    kcirc = by_target(res.rows, "Kcirc")
    assert kcirc.keys() == KCIRC_FORMULA.keys()
    for sys, expected in KCIRC_FORMULA.items():
        assert kcirc[sys] == pytest.approx(expected, rel=0.01), sys


def test_hcirc_is_h_ras_from_last_run() -> None:
    res = step2(imported("it2_step1a").snapshot)
    assert by_target(res.rows, "Hcirc") == HCIRC


def test_tcirc_already_equal_to_meter_is_not_touched() -> None:
    res = step2(imported("it2_step1a").snapshot)
    assert by_target(res.rows, "Tcirc") == {}


def test_dead_end_objects_are_skipped() -> None:
    res = step2(imported("it2_step1a").snapshot)
    targets = {r.target for r in res.rows}
    assert {"33553", "33559", "33567"}.isdisjoint(targets)
    assert any("33553" in n for n in res.notes)


def test_hcirc_correction_when_circulation_is_off() -> None:
    house = Consumer(
        sys=1,
        guid="g",
        scheme=26,
        fields={
            "Qgv_sred": 0.05,
            "Kgv": 0.3,
            "Tgv": 60.0,
            "Thv": 5.0,
            "Kcirc": 733,  # = 100 · G2 / Ggv already
            "Hcirc": 19.0,
            "Tcirc": 49.0,
            "G1_GVS": 2.2,
            "G2_GVS": 2.0,
            "T1_GVS": 60.0,
            "T2_GVS": 49.0,
            "Gcirc": 2.4,  # +20 % vs meter
            "H_ras": 19.0,
        },
    )
    res = step2(Snapshot(ctp_name="x", card={}, consumers=[house]))
    # Hcirc_new = Hcirc · (Gmodel / Gfact)² = 19 · 1.2² = 27.36
    assert by_target(res.rows, "Hcirc") == {"1": 27.4}
    assert by_target(res.rows, "Kcirc") == {}
