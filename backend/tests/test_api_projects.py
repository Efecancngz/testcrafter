def test_list_projects_without_session_override_does_not_500():
    # Regression test: the `client` fixture overrides get_session with a plain
    # generator, which masked get_session being wrongly decorated with
    # @contextmanager (FastAPI's Depends() double-wraps that, breaking every
    # real request with AttributeError on '_GeneratorContextManager'). This
    # hits the app exactly as a real deployment would, with no override.
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as real_client:
        resp = real_client.get("/projects")

    assert resp.status_code == 200


def test_create_and_list_project(client):
    resp = client.post("/projects", json={"name": "Demo Site", "base_url": "https://example.com"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Demo Site"

    list_resp = client.get("/projects")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
