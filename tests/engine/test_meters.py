"""Meter block choice and meter checks 1–11 (algorithm: «Входные данные и проверка приборов»)."""

import pytest

from app.engine.meters import Status, meter_checks, meter_for

from .conftest import imported


def test_dhw_object_uses_gvs_block() -> None:
    m = meter_for(imported("it0_initial").snapshot.consumer(33551))
    assert m.block == "GVS"
    assert (m.G1, m.G2, m.T1, m.T2, m.Q) == (2.2, 1.9, 60.6, 49, 0.041)
    assert not m.from_inlet


def test_heating_object_uses_ot_block() -> None:
    m = meter_for(imported("it0_initial").snapshot.consumer(33525))
    assert m.block == "OT"
    assert (m.G1, m.Q) == (11, 0.266)


def test_heating_object_without_ot_falls_back_to_ts() -> None:
    m = meter_for(imported("it0_initial").snapshot.consumer(33563))
    assert m.block == "TS"
    assert m.from_inlet  # «взят ввод»
    assert (m.G1, m.Q) == (37.3, 0.668)


@pytest.fixture
def checks(fact):
    return {c.no: c for c in meter_checks(fact, imported("it0_initial").snapshot.consumers)}


def test_check1_heating_heat_from_flow_and_dt(checks) -> None:
    c = checks[1]
    assert c.values["Qso"] == pytest.approx(2.610, abs=5e-4)
    assert c.status is Status.OK


def test_check2_dhw_heat(checks) -> None:
    c = checks[2]
    assert c.values["Qgv"] == pytest.approx(0.540, abs=5e-4)
    assert c.status is Status.OK


def test_check3_inlet_balance(checks) -> None:
    c = checks[3]
    assert c.values["deviation_pct"] == pytest.approx(-1.4, abs=0.1)
    assert c.status is Status.OK


def test_check4_second_circuit_leak_is_ctp_flowmeter_error(checks) -> None:
    c = checks[4]
    assert c.values["ctp_leak"] == pytest.approx(6.9)
    assert c.values["houses_leak"] == pytest.approx(0.3, abs=1e-6)
    assert c.status is Status.FLAG
    assert "не подгонять" in c.message


def test_check5_ctp_vs_houses_flows(checks) -> None:
    c = checks[5]
    assert c.values["sum_heating_G1"] == pytest.approx(143.1)
    assert c.values["heating_deviation_pct"] == pytest.approx(-0.2, abs=0.05)
    # DHW: Gп 23.1 vs ΣG1_GVS 22.0, Gц 16.4 vs ΣG2_GVS 17.3 — both outside ±3 %
    assert c.values["sum_dhw_G1"] == pytest.approx(22.0)
    assert c.values["sum_dhw_G2"] == pytest.approx(17.3)
    assert c.status is Status.FLAG


def test_check6_quarter_network_losses(checks) -> None:
    c = checks[6]
    assert c.values["sum_heating_Q"] == pytest.approx(2.567)
    assert c.values["losses_pct"] == pytest.approx(1.6, abs=0.1)
    assert c.status is Status.OK


def test_check7_dhw_draw_off_asks_whom_to_trust(checks) -> None:
    c = checks[7]
    assert c.values["ctp_draw_off"] == pytest.approx(6.7)
    assert c.values["houses_draw_off"] == pytest.approx(4.7)
    assert c.status is Status.QUESTION


def test_check8_two_stage_dhw(checks) -> None:
    c = checks[8]
    assert c.values["two_stage"] is True
    assert c.status is Status.OK


def test_check9_main_line_sensor_error(checks) -> None:
    c = checks[9]  # T1 89.2 > t source 88.7 → losses ≈ 0, difference is sensor error
    assert c.status is Status.NOTE


def test_check10_dhw_house_meters_are_consistent(checks) -> None:
    c = checks[10]
    assert c.values["flagged"] == []
    assert c.status is Status.OK


def test_check11_same_pressure_shift_is_gauge_elevation(fact) -> None:
    card = imported("it0_initial").snapshot.card  # Ppod 34.45 / Pobr 29.81 vs 54.8 / 48.4
    checks = {c.no: c for c in meter_checks(fact, imported("it0_initial").snapshot.consumers, card)}
    c = checks[11]
    assert c.values["supply_shift"] == pytest.approx(-20.35)
    assert c.values["return_shift"] == pytest.approx(-18.59)
    assert c.status is Status.NOTE
    assert "Pcalibr" in c.message


def test_checks_without_dhw_meter_are_not_applicable(fact) -> None:
    no_dhw = fact.__class__(inlet=fact.inlet, heating=fact.heating, dhw=None, mode=fact.mode)
    checks = {c.no: c for c in meter_checks(no_dhw, imported("it0_initial").snapshot.consumers)}
    assert checks[2].status is Status.NA
    assert checks[7].status is Status.NA
