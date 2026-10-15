"""Import of the real Zulu formats through the pages (CTP card + consumer export)."""

import html

from fastapi.testclient import TestClient

from .helpers import create_project, db_dump, zulu_payload

SET = "chernyshevskogo_8"


def page(client: TestClient, url: str) -> str:
    resp = client.get(url)
    assert resp.status_code == 200, (url, resp.status_code)
    return html.unescape(resp.text)


def test_new_project_page_offers_the_zulu_import(client: TestClient) -> None:
    text = page(client, "/projects/new")
    assert 'class="zulu-import-form"' in text
    assert 'src="/static/xlsx-0.20.3.mini.min.js"' in text
    assert "data-card" in text and "data-consumers-file" in text
    # the raw card and the raw file are never form fields
    assert 'name="card"' not in text and 'name="consumers"' not in text
    assert client.get("/static/xlsx-0.20.3.mini.min.js").status_code == 200


def test_zulu_import_prefills_the_fact_from_the_card(client: TestClient) -> None:
    pid = create_project(client, data=zulu_payload(SET, "it0_initial"))
    text = page(client, f"/projects/{pid}/fact")
    assert 'name="inlet_G1" value="129,5"' in text
    assert 'name="heating_T4" value="58,2"' in text
    assert 'name="dhw_Gp" value="4,7"' in text
    assert 'name="mode_tnv" value="-12,8"' in text
    assert "ЦТП Чернышевского. 8" in page(client, "/projects")


def test_zulu_import_strips_private_fields_on_the_server(client: TestClient, db_url: str) -> None:
    create_project(client, data=zulu_payload(SET, "it0_initial", private_value="Секретная"))
    dump = db_dump(db_url)
    assert "Секретная" not in dump
    for key in ('"Name"', '"Adres"', '"FIAS_Adress"', '"UUTE_Name"'):
        assert key not in dump


def test_bad_zulu_input_shows_a_message(client: TestClient) -> None:
    resp = client.post(
        "/projects", data={"payload": '{"format": "zulu", "card": "x", "consumers": []}'}
    )
    assert resp.status_code == 400
    assert "потребител" in html.unescape(resp.text)


def test_consumers_only_reimport_warns_that_the_card_is_old(client: TestClient) -> None:
    pid = create_project(client, data=zulu_payload(SET, "it0_initial"))
    client.post(f"/projects/{pid}/fact", data={"mode_thv": "5", "mode_data_type": "day",
                                               "mode_pressure_unit": "m"})  # fmt: skip
    client.post(f"/projects/{pid}/checks/next")
    resp = client.post(
        f"/projects/{pid}/steps/1/import",
        data={"payload": zulu_payload(SET, "it1_step1_inlet_washer_plug", card=False)},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    assert "Карточка ЦТП не обновлена" in page(client, f"/projects/{pid}/steps/1")
