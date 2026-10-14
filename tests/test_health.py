from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_healthz_ok(client: TestClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok"}


def test_healthz_answers_head_requests(client: TestClient) -> None:
    # Uptime monitors often probe with HEAD.
    assert client.head("/healthz").status_code == 200


def test_healthz_reports_unavailable_database(tmp_path: Path) -> None:
    # The database "file" is a directory, so SQLite cannot open it.
    broken = tmp_path / "not_a_file.db"
    broken.mkdir()
    app = create_app(Settings(database_url=f"sqlite:///{broken.as_posix()}"))
    with TestClient(app) as c:
        resp = c.get("/healthz")
    assert resp.status_code == 503
    assert resp.json() == {"status": "error", "db": "error"}
