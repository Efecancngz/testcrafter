def test_create_and_list_project(client):
    resp = client.post("/projects", json={"name": "Demo Site", "base_url": "https://example.com"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Demo Site"

    list_resp = client.get("/projects")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
