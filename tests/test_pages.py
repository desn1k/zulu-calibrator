from fastapi.testclient import TestClient

HTMX = "/static/htmx-2.0.11.min.js"


def test_home_page_renders_in_russian(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert '<html lang="ru">' in resp.text
    assert "Калибровка ЦТП" in resp.text


def test_htmx_is_served_locally(client: TestClient) -> None:
    page = client.get("/").text
    assert f'src="{HTMX}"' in page
    assert "unpkg.com" not in page and "cdn" not in page

    resp = client.get(HTMX)
    assert resp.status_code == 200
    assert "htmx" in resp.text[:200]
