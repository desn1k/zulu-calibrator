"""Local UI: import, CTP fact, meter checks, steps 1–5 on the Огородная exports, history."""

import html
import json

from fastapi.testclient import TestClient

from tests.engine.conftest import raw

from .helpers import create_project, db_dump, enter_fact, import_export


def page(client: TestClient, url: str) -> str:
    resp = client.get(url)
    assert resp.status_code == 200, (url, resp.status_code)
    return html.unescape(resp.text)


def advance(client: TestClient, pid: int, step: str):
    return client.post(f"/projects/{pid}/steps/{step}/advance", follow_redirects=False)


def accept(client: TestClient, pid: int, step: str, comment: str):
    return client.post(
        f"/projects/{pid}/steps/{step}/accept", data={"comment": comment}, follow_redirects=False
    )


def test_home_has_the_two_entries(client: TestClient) -> None:
    text = page(client, "/")
    assert "Новый расчёт ЦТП" in text and 'href="/projects/new"' in text
    assert "История ЦТП" in text and 'href="/projects"' in text


def test_new_project_page_strips_private_fields_in_the_browser(client: TestClient) -> None:
    text = page(client, "/projects/new")
    assert 'src="/static/import.js"' in text
    js = client.get("/static/import.js").text
    for key in ("Name", "Bld", "Adres"):
        assert key in js


def test_import_strips_private_fields_on_the_server_too(client: TestClient, db_url: str) -> None:
    data = json.loads(json.dumps(raw("it0_initial")))
    data["дома"][0]["Name"] = "ул. Секретная, 1"
    data["дома"][0]["Bld"] = "корп. 2"
    data["карточка_ЦТП"]["Adres"] = "ул. Секретная, 3"
    create_project(client, data=json.dumps(data, ensure_ascii=False))

    dump = db_dump(db_url)
    assert "Секретная" not in dump
    assert "корп. 2" not in dump
    for key in ("'Name'", '"Name"', '"Bld"', '"Adres"'):
        assert key not in dump


def test_project_is_named_by_ctp_and_measurement_date(client: TestClient) -> None:
    create_project(client)
    text = page(client, "/projects")
    assert "ЦТП Огородная, 87" in text
    assert "10.02.2026" in text


def test_fact_form_is_prefilled_from_the_export(client: TestClient) -> None:
    pid = create_project(client)
    text = page(client, f"/projects/{pid}/fact")
    assert 'name="inlet_G1" value="98,4"' in text
    assert 'name="heating_T4" value="60,3"' in text
    assert 'name="dhw_Gp" value=""' in text  # DHW facts are not in the old export
    assert "м вод. ст." in text and "кгс/см²" in text


def test_pressure_in_kgf_cm2_is_stored_in_metres(client: TestClient) -> None:
    pid = create_project(client)
    enter_fact(client, pid, mode_pressure_unit="kgf_cm2", inlet_P1="5.48")
    text = page(client, f"/projects/{pid}/fact")
    assert 'name="inlet_P1" value="5,48"' in text  # shown in the chosen unit
    text = page(client, f"/projects/{pid}/checks")
    assert "54,8" in text  # check 11 works in metres


def test_steps_cannot_be_skipped(client: TestClient) -> None:
    pid = create_project(client)
    enter_fact(client, pid)
    resp = client.get(f"/projects/{pid}/steps/3", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/projects/{pid}/checks"


def test_full_walkthrough_on_ogorodnaya(client: TestClient) -> None:
    pid = create_project(client)
    enter_fact(client, pid)

    # Meter checks
    text = page(client, f"/projects/{pid}/checks")
    assert "Проверка приборов" in text
    assert "не подгонять" in text  # check 4
    resp = client.post(f"/projects/{pid}/checks/next", follow_redirects=False)
    assert resp.headers["location"] == f"/projects/{pid}/steps/1"

    # Step 1 on it0, with the free parameters of the real session (README: 59 / 57.5)
    # Kgv: the Огородная session used formula 1.3 (manual override of the automatic rule)
    client.post(f"/projects/{pid}/steps/1/settings",
                data={"t22_niz": "59", "t12_verh": "57,5", "kgv_mode": "formula"})  # fmt: skip
    text = page(client, f"/projects/{pid}/steps/1")
    for value in ("57,2", "60,9", "61,1", "0,362", "0,178", "92,8"):
        assert value in text
    assert "T2_bal" in text and "57,2" in text and "57" in text
    assert "T2 ввода физически не опустится до факта" in text
    assert "ЦТП\tT12_i_niz\t57,2" in text  # «Копировать» payload
    assert "33553\tKgv\t0,361" in text
    assert "33567\tKgv\t0,072" in text
    assert "по теплу (расход не измерен)" in text

    resp = advance(client, pid, "1")
    assert resp.status_code == 409  # criteria do not pass on it0 (Gverh = 0)

    assert import_export(client, pid, "1", "it2_step1a").status_code == 303
    text = page(client, f"/projects/{pid}/steps/1")
    assert "T2so_t" in text and "не сошлось" in text
    assert advance(client, pid, "1").status_code == 409
    assert accept(client, pid, "1", "").status_code == 400  # comment is mandatory
    resp = accept(client, pid, "1", "T2 ввода не дойдёт: разбор по домам меньше")
    assert resp.headers["location"] == f"/projects/{pid}/steps/2"

    # Step 2 on it2
    text = page(client, f"/projects/{pid}/steps/2")
    assert "33551\tKcirc\t612" in text
    assert "33551\tHcirc\t19,4" in text
    assert advance(client, pid, "2").status_code == 409
    import_export(client, pid, "2", "it3_step2")
    resp = advance(client, pid, "2")
    assert resp.headers["location"] == f"/projects/{pid}/steps/3"

    # Step 3 on it3: washer stays; identical export is flagged
    text = page(client, f"/projects/{pid}/steps/3")
    assert "Ø72" in text
    import_export(client, pid, "3", "it5_step3_rollback")
    text = page(client, f"/projects/{pid}/steps/3")
    assert "идентичны" in text
    resp = advance(client, pid, "3")
    assert resp.headers["location"] == f"/projects/{pid}/steps/4"

    # Step 4: variant А by default, Kso with the exception flag
    text = page(client, f"/projects/{pid}/steps/4")
    assert "Вариант А" in text
    client.post(f"/projects/{pid}/steps/4/settings", data={"kso_exception": "on"})
    text = page(client, f"/projects/{pid}/steps/4")
    assert "33523\tKso\t1,075" in text
    assert "нагрузка в модели ≠ договорной" in text
    assert advance(client, pid, "4").status_code == 409
    import_export(client, pid, "4", "it6_step4_kso")
    # ±4 % since 2026-10-15: 33525 and 33531 at −4.1 % → accepted with a comment
    assert advance(client, pid, "4").status_code == 409
    resp = accept(client, pid, "4", "33525 и 33531 −4,1 %, дотянет шаг 5")
    assert resp.headers["location"] == f"/projects/{pid}/steps/5"

    # Step 5 on it6 → it7
    text = page(client, f"/projects/{pid}/steps/5")
    assert "33523\tDshb_so_pod_u\t16,7" in text
    assert "36749\tDshb_so_pod_u\t36,9" in text
    import_export(client, pid, "5", "it7_step5_washers")
    text = page(client, f"/projects/{pid}/steps/5")
    assert "33525\tDshb_so_pod_u\t17,5" in text  # washers in series
    assert "33525\tDshb_pod\t" in text  # cleared → empty value
    resp = advance(client, pid, "5")
    assert resp.headers["location"] == f"/projects/{pid}/summary"

    text = page(client, f"/projects/{pid}/summary")
    assert "Модель" in text and "Факт" in text
    assert "Gsum_pod" in text
    assert "<code>Gso:" not in text  # titles, not internal keys

    text = page(client, "/projects")
    assert "принят с отклонениями" in text

    # Resume goes to the current page; past iterations are read-only
    resp = client.get(f"/projects/{pid}", follow_redirects=False)
    assert resp.headers["location"] == f"/projects/{pid}/summary"
    text = page(client, f"/projects/{pid}/iterations/1")
    assert "только чтение" in text
    assert "<form" not in text


def test_step1_free_parameters_can_be_changed(client: TestClient) -> None:
    pid = create_project(client)
    enter_fact(client, pid)
    client.post(f"/projects/{pid}/checks/next")
    text = page(client, f"/projects/{pid}/steps/1")
    assert 'name="t22_niz"' in text and 'name="t12_verh"' in text

    client.post(f"/projects/{pid}/steps/1/settings", data={"t22_niz": "59", "t12_verh": "57,5"})
    text = page(client, f"/projects/{pid}/steps/1")
    assert 'name="t22_niz" value="59"' in text
    assert "ЦТП\tT12_i\t61,1" in text
