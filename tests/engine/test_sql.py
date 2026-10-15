"""Zulu SQL output of the step pages."""

from app.engine.model import CTP_TARGET, Consumer, Recommendation, Snapshot
from app.engine.sql import DEFAULT_LAYER, sql_lines, sql_text, sql_value

LAYER = DEFAULT_LAYER


def rec(target, field, enter, current=None) -> Recommendation:
    return Recommendation(str(target), field, current, enter, "")


def snap(*consumers: Consumer) -> Snapshot:
    return Snapshot(ctp_name="ЦТП Тест", card={}, consumers=list(consumers))


def test_same_value_for_several_objects_is_one_statement_with_in() -> None:
    rows = [rec(27966, "Dshb_so_pod_u", 12.7), rec(40462, "Dshb_so_pod_u", 12.7)]
    assert sql_lines(rows, None, LAYER, "ЦТП") == [
        "UPDATE [Актуальный_расчетный_2025] SET Dshb_so_pod_u = 12.7 WHERE Sys IN (27966, 40462)"
    ]  # the example of docs/algorithm.md


def test_ctp_fields_by_name_with_decimal_point_and_quotes() -> None:
    rows = [rec(CTP_TARGET, "Q_i_verh", 0.385), rec(CTP_TARGET, "Tgv", 62.7)]
    lines = sql_lines(rows, None, "Слой", "ЦТП Чернышевского. 8")
    assert lines == [
        "UPDATE [Слой] SET Q_i_verh = 0.385 WHERE Name = 'ЦТП Чернышевского. 8'",
        "UPDATE [Слой] SET Tgv = 62.7 WHERE Name = 'ЦТП Чернышевского. 8'",
    ]
    assert sql_value("ЦТП 'А'") == "'ЦТП ''А'''"
    assert sql_value(None) == "NULL" and sql_value(1) == "1" and sql_value(56.0) == "56"


def test_batch_has_semicolons_except_the_last_line_and_one_by_one_has_none() -> None:
    lines = ["UPDATE a", "UPDATE b", "UPDATE c"]
    assert sql_text(lines) == "UPDATE a;\nUPDATE b;\nUPDATE c"
    assert sql_text(lines, batch=False) == "UPDATE a\nUPDATE b\nUPDATE c"
    assert sql_text(["UPDATE a"]) == "UPDATE a"
    assert not any(line.upper().startswith("SELECT") for line in sql_text(lines).splitlines())


def test_washer_is_set_d_first_then_n_and_cleared_n_first() -> None:
    rows = [
        rec(1, "Dshb_so_pod_u", 13.1), rec(1, "Nshb_so_pod_u", 1),
        rec(2, "Dshb_pod", None), rec(2, "Nshb_pod", None),
        rec(3, "Dshb_so_pod_u", 12.7), rec(3, "Nshb_so_pod_u", 1),
    ]  # fmt: skip
    lines = sql_lines(rows, None, "L", "x")
    assert lines[0] == "UPDATE [L] SET Nshb_pod = NULL WHERE Sys = 2"
    assert lines[-1] == "UPDATE [L] SET Nshb_so_pod_u = 1 WHERE Sys IN (1, 3)"
    assert lines.index("UPDATE [L] SET Dshb_pod = NULL WHERE Sys = 2") < len(lines) - 1


def test_row_with_n_one_and_empty_d_gets_n_zero_in_the_same_statement() -> None:
    # Пионерская 33652: Nshb_gvs_u = 1 / Nshb_circ_u = 1 with an empty D → «неверное значение поля»
    broken = Consumer(33652, "g", 26, {"Nshb_gvs_u": 1, "Dshb_gvs_u": None, "Nshb_circ_u": 1,
                                       "Dshb_circ_u": 0, "Kcirc": None})  # fmt: skip
    ok = Consumer(33650, "h", 26, {"Nshb_gvs_u": 0})
    rows = [rec(33652, "Kcirc", 192), rec(33650, "Kcirc", 192), rec(33652, "Hcirc", 5)]
    lines = sql_lines(rows, snap(broken, ok), "L", "x")
    assert lines == [
        "UPDATE [L] SET Kcirc = 192, Nshb_circ_u = 0, Nshb_gvs_u = 0 WHERE Sys = 33652",
        "UPDATE [L] SET Kcirc = 192 WHERE Sys = 33650",
        "UPDATE [L] SET Hcirc = 5 WHERE Sys = 33652",
    ]


def test_no_fix_when_the_batch_sets_that_washer() -> None:
    c = Consumer(1, None, 4, {"Nshb_so_pod_u": 1, "Dshb_so_pod_u": None})
    rows = [rec(1, "Dshb_so_pod_u", 11.3)]
    assert sql_lines(rows, snap(c), "L", "x") == [
        "UPDATE [L] SET Dshb_so_pod_u = 11.3 WHERE Sys = 1"
    ]
