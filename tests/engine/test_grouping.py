"""GUID grouping and multi-input split (algorithm: «Источники данных, GUID и неполные приборы»)."""

import pytest

from app.engine.grouping import duplicate_facts, group_consumers, split_multi_input
from app.engine.model import Consumer

from .conftest import imported


def test_heating_and_dhw_under_one_guid_are_separate_groups() -> None:
    groups = group_consumers(imported("it0_initial").snapshot.consumers)
    assert len(groups) == 16
    assert all(len(g.members) == 1 for g in groups)

    guid = "bea0ba13-c700-11e5-80e5-005056a05192"
    kinds = sorted(g.kind for g in groups if g.guid == guid)
    assert kinds == ["dhw", "heating"]


def two_input_house() -> list[Consumer]:
    meter = {"G1_OT": 20.0, "G2_OT": 19.6, "T1_OT": 77.0, "T2_OT": 57.0, "Q_OT": 0.4}
    return [
        Consumer(sys=1, guid="g-1", scheme=4, fields={"Qo_r": 0.3, **meter}),
        Consumer(sys=2, guid="g-1", scheme=4, fields={"Qo_r": 0.1, **meter}),
    ]


def test_multi_input_house_splits_meter_by_load() -> None:
    [group] = group_consumers(two_input_house())
    assert group.multi_input

    split = split_multi_input(group)
    assert pytest.approx(15.0) == split[1].G1
    assert pytest.approx(5.0) == split[2].G1
    assert pytest.approx(0.3) == split[1].Q
    assert pytest.approx(0.1) == split[2].Q
    # temperatures are common
    assert split[1].T1 == split[2].T1 == 77.0


def test_multi_input_split_can_be_overridden_by_hand() -> None:
    [group] = group_consumers(two_input_house())
    split = split_multi_input(group, shares={1: 0.5, 2: 0.5})
    assert pytest.approx(10.0) == split[1].G1


def test_identical_fact_under_different_guids_is_flagged() -> None:
    meter = {"G1_OT": 8.9, "G2_OT": 8.8, "T1_OT": 76.9, "T2_OT": 65.8, "Q_OT": 0.107}
    consumers = [
        Consumer(sys=1, guid="a", scheme=4, fields={"Qo_r": 0.1, **meter}),
        Consumer(sys=2, guid="b", scheme=4, fields={"Qo_r": 0.2, **meter}),
        Consumer(sys=3, guid="c", scheme=4, fields={"Qo_r": 0.2, **meter, "G1_OT": 9.5}),
    ]
    assert duplicate_facts(consumers) == [(1, 2)]


def test_fixture_has_no_duplicate_facts() -> None:
    assert duplicate_facts(imported("it0_initial").snapshot.consumers) == []
