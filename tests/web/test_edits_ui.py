"""Meter-check page: manual consumer edits, GUID groups and split shares."""

import html
import json
import re

from fastapi.testclient import TestClient

from app.models import Project
from tests.engine.conftest import raw

from .helpers import create_project, enter_fact, import_export


def page(client: TestClient, url: str) -> str:
    resp = client.get(url)
    assert resp.status_code == 200, (url, resp.status_code)
    return html.unescape(resp.text)


def cell(text: str, name: str) -> str:
    """The <input> tag with this name."""
    m = re.search(rf'<input[^>]*name="{re.escape(name)}"[^>]*>', text)
    assert m, name
    return m.group(0)


def save_edits(client: TestClient, pid: int, form: dict[str, str]) -> None:
    resp = client.post(f"/projects/{pid}/checks/edits", data=form, follow_redirects=False)
    assert resp.status_code == 303, resp.text


def set_step(client: TestClient, pid: int, step: str) -> None:
    with client.app.state.sessionmaker() as s:
        p = s.get(Project, pid)
        p.current_step = step
        s.commit()


def test_checks_page_lists_consumer_meters_with_block_choice(client: TestClient) -> None:
    pid = create_project(client)
    enter_fact(client, pid)
    text = page(client, f"/projects/{pid}/checks")
    assert 'name="33525:block"' in text
    assert 'value="11"' in cell(text, "33525:G1_OT")
    assert 'name="33525:distrust"' in text
    assert "edited" not in cell(text, "33525:G1_OT")


def test_edits_survive_a_reimport_of_it2(client: TestClient) -> None:
    pid = create_project(client)
    enter_fact(client, pid)
    save_edits(
        client,
        pid,
        {"33525:shown": "OT", "33525:block": "", "33525:G1_OT": "12", "33531:distrust": "on",
         "33531:shown": "OT", "33531:block": ""},
    )  # fmt: skip
    text = page(client, f"/projects/{pid}/checks")
    assert 'value="12"' in cell(text, "33525:G1_OT")
    assert "edited" in cell(text, "33525:G1_OT")

    client.post(f"/projects/{pid}/checks/next")
    assert import_export(client, pid, "1", "it2_step1a").status_code == 303

    text = page(client, f"/projects/{pid}/checks")
    assert 'value="12"' in cell(text, "33525:G1_OT")
    assert "edited" in cell(text, "33525:G1_OT")
    assert "checked" in cell(text, "33531:distrust")


def test_unchanged_values_are_not_stored_as_edits(client: TestClient) -> None:
    pid = create_project(client)
    enter_fact(client, pid)
    save_edits(client, pid, {"33525:shown": "OT", "33525:block": "", "33525:G1_OT": "11,0"})
    text = page(client, f"/projects/{pid}/checks")
    assert "edited" not in cell(text, "33525:G1_OT")


def test_distrusted_meter_is_excluded_from_step_criteria(client: TestClient) -> None:
    pid = create_project(client, "it6_step4_kso")
    enter_fact(client, pid)
    set_step(client, pid, "5")
    text = page(client, f"/projects/{pid}/steps/5")
    assert "Sys 33523: Gso" in text

    save_edits(client, pid, {"33523:shown": "OT", "33523:block": "", "33523:distrust": "on"})
    text = page(client, f"/projects/{pid}/steps/5")
    assert "Sys 33523: Gso" not in text
    assert "33523\tDshb_so_pod_u" not in text


def test_engine_uses_edited_facts(client: TestClient) -> None:
    pid = create_project(client, "it6_step4_kso")
    enter_fact(client, pid)
    set_step(client, pid, "5")
    # meter flow equal to the model flow → no washer change for 33523
    save_edits(client, pid, {"33523:shown": "OT", "33523:block": "", "33523:G1_OT": "9.605"})
    text = page(client, f"/projects/{pid}/steps/5")
    assert "33523\tDshb_so_pod_u" not in text


def multi_input_payload() -> str:
    data = json.loads(json.dumps(raw("it6_step4_kso")))
    rows = {r["Sys"]: r for r in data["дома"]}
    rows[33535]["GUID"] = rows[33531]["GUID"]
    return json.dumps(data, ensure_ascii=False)


def test_guid_groups_and_shares_are_shown_and_editable(client: TestClient) -> None:
    pid = create_project(client, data=multi_input_payload())
    enter_fact(client, pid)
    text = page(client, f"/projects/{pid}/checks")
    assert "Многовводовые дома" in text
    # default split of one building meter: by model flow Gso 15.696 / 18.041 (2026-10-15)
    assert 'value="46,5"' in cell(text, "share:33531")
    assert 'value="53,5"' in cell(text, "share:33535")

    resp = client.post(
        f"/projects/{pid}/checks/shares",
        data={"share:33531": "60", "share:33535": "30"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "100" in html.unescape(resp.text)

    resp = client.post(
        f"/projects/{pid}/checks/shares",
        data={"share:33531": "50", "share:33535": "50"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    text = page(client, f"/projects/{pid}/checks")
    assert 'value="50"' in cell(text, "share:33531")
    assert "edited" in cell(text, "share:33531")


def test_single_input_houses_are_not_listed_as_multi_input(client: TestClient) -> None:
    pid = create_project(client)
    enter_fact(client, pid)
    text = page(client, f"/projects/{pid}/checks")
    assert 'name="share:' not in text
