from unittest.mock import patch
from app.schemas import PageStructure, PageElement, GeneratedScenario, ScenarioStep

def test_create_scan_generates_scenarios(client):
    project = client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url="https://example.com", elements=[PageElement(tag="button", role="button", selector="#submit", text="Go")])
    fake_scenarios = [GeneratedScenario(title="Click submit", steps=[ScenarioStep(action="click", selector="#submit")])]

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        resp = client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "Check submit button",
        })

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ready"
    assert len(body["scenarios"]) == 1
    assert body["scenarios"][0]["title"] == "Click submit"

def test_get_scan_not_found_returns_404(client):
    resp = client.get("/scans/999")
    assert resp.status_code == 404
