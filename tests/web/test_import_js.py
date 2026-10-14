"""app/static/import.js strips names and addresses in the browser (run with Node)."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from app.engine.legacy import parse_legacy_export
from tests.engine.conftest import raw

SCRIPT = Path(__file__).resolve().parents[2] / "app" / "static" / "import.js"
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
