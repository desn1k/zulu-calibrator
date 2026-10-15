"""app/static/import.js strips names and addresses in the browser (run with Node)."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.engine.parsers.common import to_value
from app.engine.parsers.legacy import parse_legacy_export
from app.engine.parsers.zulu import parse_zulu
from tests.engine.conftest import raw, zulu_raw

STATIC = Path(__file__).resolve().parents[2] / "app" / "static"
SCRIPT = STATIC / "import.js"
SHEETJS = STATIC / "xlsx-0.20.3.mini.min.js"
NODE = shutil.which("node")

if not NODE:
    if os.environ.get("CI"):
        pytest.fail("node is required in CI", pytrace=False)
    pytest.skip("needs node", allow_module_level=True)

HARNESS = """
const { clean } = require(process.argv[1]);
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", () => process.stdout.write(JSON.stringify(clean(JSON.parse(input)))));
"""


def run_clean(data: dict) -> dict:
    out = subprocess.run(  # noqa: S603
        [NODE, "-e", HARNESS, str(SCRIPT)],
        input=json.dumps(data, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(out.stdout)


CALL = """
global.XLSX = require(process.argv[2]);
const mod = require(process.argv[1]);
let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (d) => (input += d));
process.stdin.on("end", () => {
  const { fn, args } = JSON.parse(input);
  process.stdout.write(JSON.stringify(eval(fn)(...args)));
});
"""


def call_js(fn: str, *args) -> object:
    """Evaluate `fn` (an expression over `mod` and `XLSX`) on JSON args in Node."""
    out = subprocess.run(  # noqa: S603
        [NODE, "-e", CALL, str(SCRIPT), str(SHEETJS)],
        input=json.dumps({"fn": fn, "args": list(args)}, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(out.stdout)


# Builds an xlsx in memory (dates as real date cells), reads it back the way the page does and
# cleans it — the same path as a real Zulu export picked in the browser.
XLSX_ROUND_TRIP = """(rows, dateCol) => {
  const prepared = rows.map((r) => {
    const o = { ...r };
    if (dateCol && o[dateCol]) o[dateCol] = new Date(2026, 1, 10);
    return o;
  });
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(prepared), "Лист1");
  const bytes = XLSX.write(wb, { type: "array", bookType: "xlsx" });
  return mod.cleanRows(mod.parseRows(new Uint8Array(bytes), false));
}"""


def test_card_address_lines_never_leave_the_browser() -> None:
    text = "Name\tЦТП Тест\nAdres\tул. Секретная, 3\nFIAS_ID  0c5b\nN_schem\t12\n"
    cleaned = call_js("mod.cleanCard", text)
    assert "Секретная" not in cleaned and "0c5b" not in cleaned
    assert "Name\tЦТП Тест" in cleaned and "N_schem\t12" in cleaned


def test_consumer_private_columns_never_leave_the_browser() -> None:
    rows = [{"Sys": 1, "Name": "ул. Секретная", "Bld": "2", "Adres": "x", "FIAS_Adress": "y",
             "FIAS_ID": "z", "UUTE_Name": "УУТЭ", "CtpName": "ЦТП Тест", "Qo_r": 0.2}]  # fmt: skip
    [row] = call_js("mod.cleanRows", rows)
    assert row == {"Sys": 1, "CtpName": "ЦТП Тест", "Qo_r": 0.2}


def test_xlsx_export_read_in_the_browser_parses_like_the_csv() -> None:
    text, csv_rows = zulu_raw("chernyshevskogo_8", "it7_step4_kso_finetune")
    typed = [
        {k: to_value(v) for k, v in r.items()} | {"Name": "ул. Секретная, 1"} for r in csv_rows
    ]
    rows = call_js(XLSX_ROUND_TRIP, typed, "DateMea")
    assert all("Name" not in r for r in rows)
    from_xlsx, _ = parse_zulu(call_js("mod.cleanCard", text), rows)
    from_csv, _ = parse_zulu(text, [dict(r) for r in csv_rows])
    assert [c.sys for c in from_xlsx.consumers] == [c.sys for c in from_csv.consumers]
    for a, b in zip(from_xlsx.consumers, from_csv.consumers, strict=True):
        diff = {k for k in b.fields if k != "DateMea" and a.fields.get(k) != b.fields[k]}
        assert not diff, (b.sys, diff)
    assert from_xlsx.measured_on == from_csv.measured_on


def test_csv_read_in_the_browser_keeps_values_as_text() -> None:
    rows = call_js("(t) => mod.cleanRows(mod.parseRows(t, true))",
                   "Sys;Qo_r;Name\n101;0,22;ул. Секретная\n")  # fmt: skip
    assert rows == [{"Sys": "101", "Qo_r": "0,22"}]


def test_names_and_addresses_never_leave_the_browser() -> None:
    data = json.loads(json.dumps(raw("it0_initial")))
    data["дома"][0]["Name"] = "ул. Секретная, 1"
    data["дома"][0]["Bld"] = "корп. 2"
    data["дома"][0]["Adres_full"] = "г. Город"
    data["карточка_ЦТП"]["Adres"] = "ул. Секретная, 3"

    cleaned = run_clean(data)
    text = json.dumps(cleaned, ensure_ascii=False)
    assert "Секретная" not in text and "корп. 2" not in text and "г. Город" not in text
    for row in cleaned["дома"]:
        assert not {"Name", "Bld", "Adres"} & row.keys()
    # free-text parts of the old export are not sent at all
    assert "рекомендации" not in cleaned and "журнал" not in cleaned


def test_cleaned_payload_still_imports_with_the_same_numbers() -> None:
    cleaned = run_clean(raw("it0_initial"))
    full = parse_legacy_export(raw("it0_initial"))
    slim = parse_legacy_export(cleaned)
    assert slim.snapshot == full.snapshot
    assert slim.fact == full.fact
