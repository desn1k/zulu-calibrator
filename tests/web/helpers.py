import json
import re
import sqlite3

from fastapi.testclient import TestClient

from tests.engine.conftest import raw

README_FACT = {
    "inlet_G1": "98.4", "inlet_G2": "99.7", "inlet_T1": "89.2", "inlet_T2": "57",
    "inlet_P1": "54.8", "inlet_P2": "48.4", "inlet_Q": "3.104",
    "heating_G3": "143.4", "heating_G4": "136.5", "heating_T3": "78.5", "heating_T4": "60.3",
    "heating_P3": "70.9", "heating_P4": "53.3", "heating_Q": "2.610",
    "dhw_Gp": "23.1", "dhw_Gc": "16.4", "dhw_Tgv": "62.8", "dhw_Tc": "53.5", "dhw_Q": "0.537",
    "mode_tnv": "-12.8", "mode_t_source": "88.7", "mode_thv": "5",
    "mode_data_type": "day", "mode_pressure_unit": "m",
}  # fmt: skip


def payload(name: str) -> str:
    return json.dumps(raw(name), ensure_ascii=False)


def create_project(client: TestClient, name: str = "it0_initial", data: str | None = None) -> int:
    resp = client.post("/projects", data={"payload": data or payload(name)}, follow_redirects=False)
    assert resp.status_code == 303, resp.text
    m = re.match(r"/projects/(\d+)/fact", resp.headers["location"])
    assert m, resp.headers["location"]
    return int(m.group(1))


def enter_fact(client: TestClient, pid: int, **extra: str) -> None:
    resp = client.post(
        f"/projects/{pid}/fact", data={**README_FACT, **extra}, follow_redirects=False
    )
    assert resp.status_code == 303, resp.text


def import_export(client: TestClient, pid: int, step: str, name: str):
    return client.post(
        f"/projects/{pid}/steps/{step}/import",
        data={"payload": payload(name)},
        follow_redirects=False,
    )


def db_dump(db_url: str) -> str:
    path = db_url.removeprefix("sqlite:///")
    conn = sqlite3.connect(path)
    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return "\n".join(str(row) for t in tables for row in conn.execute(f'SELECT * FROM "{t}"'))  # noqa: S608
    finally:
        conn.close()
