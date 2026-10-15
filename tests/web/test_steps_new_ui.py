"""Step pages on a real Zulu set: SQL output, layer, step order, warnings, legend, labels."""

import html
import re

from fastapi.testclient import TestClient

from app.engine.schemes import INITIAL_CALIBRATED
from app.models import SchemeStatus

from .helpers import create_project, zulu_payload

SET = "chernyshevskogo_8"


def page(client: TestClient, url: str) -> str:
    resp = client.get(url)
    assert resp.status_code == 200, (url, resp.status_code)
    return html.unescape(resp.text)


def start(client: TestClient, iteration: str = "it2_step1a_inlet_washer_200") -> int:
    pid = create_project(client, data=zulu_payload(SET, "it0_initial"))
    form = {
        "inlet_G1": "129.5", "inlet_G2": "132.4", "inlet_T1": "89.2", "inlet_T2": "53",
        "inlet_P1": "68.8", "inlet_P2": "55.9", "inlet_Q": "4.571",
        "heating_G3": "128.5", "heating_G4": "128.2", "heating_T3": "89.2", "heating_T4": "58.2",
        "heating_P3": "66.6", "heating_P4": "56.3", "heating_Q": "4.012",
        "dhw_Gp": "4.7", "dhw_Tgv": "65.8", "dhw_Pp": "58.3", "dhw_Q": "0.285",
        "mode_tnv": "-12.8", "mode_thv": "5", "mode_data_type": "day", "mode_pressure_unit": "m",
    }  # fmt: skip
    client.post(f"/projects/{pid}/fact", data=form)
    client.post(f"/projects/{pid}/checks/next")
    client.post(f"/projects/{pid}/steps/1/import", data={"payload": zulu_payload(SET, iteration)})
    return pid


def sql_block(text: str, attr: str) -> str:
    m = re.search(rf'<pre class="sql" {attr}[^>]*>(.*?)</pre>', text, re.S)
    assert m, attr
    return m.group(1)


def test_step_page_prints_zulu_sql_batch_and_one_by_one(client: TestClient) -> None:
    pid = start(client)
    client.post(f"/projects/{pid}/steps/1/settings",
                data={"kgv_mode": "model", "circulation": "no", "t12_verh": "60"})  # fmt: skip
    text = page(client, f"/projects/{pid}/steps/1")
    batch = sql_block(text, "data-sql-batch").splitlines()
    single = sql_block(text, "data-sql-single").splitlines()
    assert batch and len(batch) == len(single)
    assert all(line.endswith(";") for line in batch[:-1]) and not batch[-1].endswith(";")
    assert not any(";" in line for line in single)
    assert any(
        line.startswith("UPDATE [Актуальный_расчетный_2025] SET Kgv = 0.261 WHERE Sys = 28108")
        for line in single
    )
    assert any("WHERE Name = 'ЦТП Чернышевского. 8'" in line for line in single)
    assert not any(line.upper().startswith("SELECT") for line in single)
    assert "Скопировать SQL" in text and "data-sql-toggle" in text and "по одной" in text
    assert "поле" in text.lower() and "Ввести" in text  # the table stays


def test_layer_is_a_project_setting(client: TestClient) -> None:
    pid = start(client)
    resp = client.post(f"/projects/{pid}/steps/1/settings", data={"layer": "Слой_2026"},
                       follow_redirects=False)  # fmt: skip
    assert resp.status_code == 303
    text = page(client, f"/projects/{pid}/steps/1")
    assert "UPDATE [Слой_2026]" in text
    bad = client.post(f"/projects/{pid}/steps/1/settings", data={"layer": "x]; DROP"})
    assert bad.status_code == 400


def test_dhw_target_reason_and_plug_warning_are_shown(client: TestClient) -> None:
    pid = start(client, "it1_step1_inlet_washer_plug")
    text = page(client, f"/projects/{pid}/steps/1")
    assert "заглушка" in text and "2/3 Ду" in text
    assert "не сходится с балансом ввод − отопление" in text


def test_checks_have_a_legend_russian_labels_and_the_dhw_source(client: TestClient) -> None:
    pid = start(client)
    text = page(client, f"/projects/{pid}/checks")
    for status in ("в норме", "пояснение", "вопрос", "флажок"):
        assert status in text
    for key in ("ctp_leak", "deviation_pct", "Q_inlet", "supply_shift", "houses_draw_off"):
        assert key not in text
    assert "G3 − G4 ЦТП" in text and "т/ч" in text
    assert "источник разбора: дома" in text  # check 7


def test_washers_first_switches_the_step_order(client: TestClient) -> None:
    pid = start(client, "it3_step1_3_kgv")
    for step in ("1", "2", "3"):
        client.post(f"/projects/{pid}/steps/{step}/accept", data={"comment": "тест"})
    text = page(client, f"/projects/{pid}/steps/4")
    assert "Сначала шаг 5 (шайбы), потом шаг 4" in text
    resp = client.post(f"/projects/{pid}/steps/4/settings", data={"washers_first": "on"},
                       follow_redirects=False)  # fmt: skip
    assert resp.headers["location"] == f"/projects/{pid}/steps/5"
    nav = page(client, f"/projects/{pid}/steps/5")
    assert nav.index("Шаг 5 — шайбы домов") < nav.index("Шаг 4 — тепло отопления домов")
    resp = client.post(f"/projects/{pid}/steps/5/accept", data={"comment": "тест"},
                       follow_redirects=False)  # fmt: skip
    assert resp.headers["location"] == f"/projects/{pid}/steps/4"


def test_group_meters_are_entered_by_hand(client: TestClient) -> None:
    pid = create_project(
        client, data=zulu_payload("pionerskaya_2_30_36", "it4_pressure_overgrowth_b2_branch")
    )
    fact = {"heating_G3": "51.6", "mode_thv": "5", "mode_data_type": "day",
            "mode_pressure_unit": "m"}  # fmt: skip
    client.post(f"/projects/{pid}/fact", data=fact)
    text = page(client, f"/projects/{pid}/checks")
    assert "Приборы многовводовых домов (узлы учёта)" in text
    guids = sorted(set(re.findall(r'name="gm:([^:"]+):G1"', text)))
    assert len(guids) == 3
    client.post(f"/projects/{pid}/checks/group-meters",
                data={f"gm:{guids[0]}:G1": "19,3", f"gm:{guids[0]}:Q": "0.592"})  # fmt: skip
    text = page(client, f"/projects/{pid}/checks")
    assert 'value="19,3"' in text


def test_scheme_registry_initial_state_and_warning(client: TestClient) -> None:
    with client.app.state.sessionmaker() as session:
        rows = {(r.kind, r.n): r for r in session.query(SchemeStatus)}
    assert {(s.kind, s.n) for s in INITIAL_CALIBRATED} == set(rows)
    assert all(r.status == "calibrated" for r in rows.values())
    assert rows[("ctp", 12)].calibrated_on.isoformat() == "2026-10-15"
    assert rows[("consumer", 2)].project == "Верхняя, 24"

    pid = start(client)
    text = page(client, f"/projects/{pid}/steps/1")
    assert "не откалибрована" not in text  # scheme 12 and consumers 4 / 26 are calibrated
    with client.app.state.sessionmaker() as session:
        session.query(SchemeStatus).filter_by(kind="ctp", n=12).delete()
        session.commit()
    text = page(client, f"/projects/{pid}/steps/1")
    assert "Схема ЦТП 12 не откалибрована" in text


def test_off_target_criterion_is_a_warning_not_a_block(client: TestClient) -> None:
    pid = start(client, "it7_step4_kso_finetune")
    for step in ("1", "2", "3", "4"):
        client.post(f"/projects/{pid}/steps/{step}/accept", data={"comment": "тест"})
    text = page(client, f"/projects/{pid}/steps/5")
    # Gsum_pod2 130.5 vs 128.5 (+1.6 %) passes; inlet-side warnings may show for other rows
    assert "Gsum_pod2 ЦТП ±4 % (цель ±2 %)" in text
    assert "только предупреждение" in text
