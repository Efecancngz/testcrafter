import shutil
from pathlib import Path
from unittest.mock import patch
import pytest
from playwright.sync_api import Error as PlaywrightError
from app.crawler import BotChallengeDetected
from app.api.scans import SCREENSHOTS_DIR
from app.schemas import PageStructure, PageElement, GeneratedScenario, ScenarioStep
from app.models import Scan

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "login_page.html").as_uri()

def test_create_scan_generates_scenarios(authenticated_client):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url="https://example.com", elements=[PageElement(tag="button", role="button", selector="#submit", text="Go")])
    fake_scenarios = [GeneratedScenario(title="Click submit", steps=[ScenarioStep(action="click", selector="#submit")])]

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        resp = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "Check submit button",
        })

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ready"
    assert len(body["scenarios"]) == 1
    assert body["scenarios"][0]["title"] == "Click submit"

def test_create_scan_persists_ai_provider(authenticated_client, db_session, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url="https://example.com", elements=[PageElement(tag="button", role="button", selector="#submit", text="Go")])
    fake_scenarios = [GeneratedScenario(title="Click submit", steps=[ScenarioStep(action="click", selector="#submit")])]

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        resp = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "Check submit button",
        })

    assert resp.status_code == 201
    scan_id = resp.json()["id"]
    scan = db_session.get(Scan, scan_id)
    assert scan.ai_provider == "gemini"

def test_create_scan_marks_failed_when_crawl_fails(authenticated_client):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    with patch("app.api.scans.extract_page_structure", side_effect=PlaywrightError("net::ERR_NAME_NOT_RESOLVED")):
        resp = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://this-domain-does-not-exist.invalid",
            "description": "Check submit button",
        })

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "failed"
    assert body["scenarios"] == []

def test_create_scan_marks_blocked_when_bot_challenge_detected(authenticated_client):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    with patch("app.api.scans.extract_page_structure", side_effect=BotChallengeDetected("cloudflare")), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        resp = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "Check submit button",
        })

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "blocked"
    assert body["blocked_reason"] == "cloudflare"
    assert body["scenarios"] == []
    mock_get_provider.assert_not_called()


def test_get_scan_includes_blocked_reason(authenticated_client):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    with patch("app.api.scans.extract_page_structure", side_effect=BotChallengeDetected("recaptcha")):
        scan = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "x",
        }).json()

    resp = authenticated_client.get(f"/scans/{scan['id']}")

    assert resp.status_code == 200
    assert resp.json()["blocked_reason"] == "recaptcha"


def test_create_scan_marks_failed_when_ai_provider_not_configured(authenticated_client):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url="https://example.com", elements=[])

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider", side_effect=TypeError("missing ANTHROPIC_API_KEY")):
        resp = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "Check submit button",
        })

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "failed"

def test_create_scan_requires_auth(client):
    resp = client.post("/projects/1/scans", json={"target_url": "https://example.com", "description": "x"})
    assert resp.status_code == 401

def test_create_scan_returns_404_for_project_owned_by_another_user(client):
    token_a = client.post("/auth/register", json={"email": "a@example.com", "password": "pw"}).json()["access_token"]
    project = client.post("/projects", json={"name": "A's project", "base_url": "https://example.com"}, headers={"Authorization": f"Bearer {token_a}"}).json()

    token_b = client.post("/auth/register", json={"email": "b@example.com", "password": "pw"}).json()["access_token"]
    resp = client.post(f"/projects/{project['id']}/scans", json={"target_url": "https://example.com", "description": "x"}, headers={"Authorization": f"Bearer {token_b}"})

    assert resp.status_code == 404

def test_get_scan_not_found_returns_404(authenticated_client):
    resp = authenticated_client.get("/scans/999")
    assert resp.status_code == 404

def test_get_scan_returns_404_for_scan_owned_by_another_user(client):
    token_a = client.post("/auth/register", json={"email": "a@example.com", "password": "pw"}).json()["access_token"]
    project = client.post("/projects", json={"name": "A's project", "base_url": "https://example.com"}, headers={"Authorization": f"Bearer {token_a}"}).json()
    fake_structure = PageStructure(url="https://example.com", elements=[])
    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = []
        scan = client.post(f"/projects/{project['id']}/scans", json={"target_url": "https://example.com", "description": "x"}, headers={"Authorization": f"Bearer {token_a}"}).json()

    token_b = client.post("/auth/register", json={"email": "b@example.com", "password": "pw"}).json()["access_token"]
    resp = client.get(f"/scans/{scan['id']}", headers={"Authorization": f"Bearer {token_b}"})

    assert resp.status_code == 404

def test_run_scan_executes_scenarios_and_persists_results(authenticated_client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.scans.SCREENSHOTS_DIR", tmp_path)

    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url=FIXTURE_URL, elements=[PageElement(tag="button", role="button", selector="#submit", text="Log in")])
    fake_scenarios = [
        GeneratedScenario(
            title="Submit button has correct label",
            steps=[
                ScenarioStep(action="goto", value=FIXTURE_URL),
                ScenarioStep(action="expect_text", selector="#submit", expected="Log in"),
            ],
        )
    ]

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        scan = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": FIXTURE_URL,
            "description": "Check submit button label",
        }).json()

    resp = authenticated_client.post(f"/scans/{scan['id']}/run")

    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "passed"
    assert len(runs[0]["steps"]) == 2
    assert all(step["status"] == "passed" for step in runs[0]["steps"])
    run_id = runs[0]["id"]
    for index, step in enumerate(runs[0]["steps"]):
        assert step["screenshot_path"] == f"/runs/{run_id}/screenshots/{index}"

def test_run_scan_not_found_returns_404(authenticated_client):
    resp = authenticated_client.post("/scans/999/run")
    assert resp.status_code == 404

def test_run_scan_returns_404_for_scan_owned_by_another_user(client):
    token_a = client.post("/auth/register", json={"email": "a@example.com", "password": "pw"}).json()["access_token"]
    project = client.post("/projects", json={"name": "A's project", "base_url": "https://example.com"}, headers={"Authorization": f"Bearer {token_a}"}).json()
    fake_structure = PageStructure(url="https://example.com", elements=[])
    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = []
        scan = client.post(f"/projects/{project['id']}/scans", json={"target_url": "https://example.com", "description": "x"}, headers={"Authorization": f"Bearer {token_a}"}).json()

    token_b = client.post("/auth/register", json={"email": "b@example.com", "password": "pw"}).json()["access_token"]
    resp = client.post(f"/scans/{scan['id']}/run", headers={"Authorization": f"Bearer {token_b}"})

    assert resp.status_code == 404

def test_get_ai_provider_defaults_to_claude(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    from app.api.scans import get_ai_provider
    from app.ai.claude_provider import ClaudeProvider
    with patch("anthropic.Anthropic"):
        provider = get_ai_provider()
    assert isinstance(provider, ClaudeProvider)


def test_get_ai_provider_selects_gemini(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    from app.api.scans import get_ai_provider
    from app.ai.gemini_provider import GeminiProvider
    with patch("google.genai.Client"):
        provider = get_ai_provider()
    assert isinstance(provider, GeminiProvider)


def test_get_ai_provider_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "not-a-real-provider")
    from app.api.scans import get_ai_provider
    with pytest.raises(ValueError, match="unknown AI_PROVIDER"):
        get_ai_provider()


def test_screenshot_proxy_serves_file_to_owner(authenticated_client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.scans.SCREENSHOTS_DIR", tmp_path)

    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url=FIXTURE_URL, elements=[PageElement(tag="button", role="button", selector="#submit", text="Log in")])
    fake_scenarios = [
        GeneratedScenario(
            title="Submit button has correct label",
            steps=[ScenarioStep(action="goto", value=FIXTURE_URL)],
        )
    ]

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        scan = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": FIXTURE_URL,
            "description": "x",
        }).json()

    run_resp = authenticated_client.post(f"/scans/{scan['id']}/run")
    run_id = run_resp.json()[0]["id"]
    on_disk_path = tmp_path / str(run_id) / "0.png"
    assert on_disk_path.is_file()
    expected_bytes = on_disk_path.read_bytes()

    resp = authenticated_client.get(f"/runs/{run_id}/screenshots/0")

    assert resp.status_code == 200
    assert resp.content == expected_bytes


def test_screenshot_proxy_requires_auth(client):
    resp = client.get("/runs/1/screenshots/0")
    assert resp.status_code == 401


def test_screenshot_proxy_returns_404_for_run_owned_by_another_user(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.scans.SCREENSHOTS_DIR", tmp_path)

    token_a = client.post("/auth/register", json={"email": "a@example.com", "password": "pw"}).json()["access_token"]
    project = client.post("/projects", json={"name": "A's project", "base_url": "https://example.com"}, headers={"Authorization": f"Bearer {token_a}"}).json()

    fake_structure = PageStructure(url=FIXTURE_URL, elements=[PageElement(tag="button", role="button", selector="#submit", text="Log in")])
    fake_scenarios = [GeneratedScenario(title="Submit button has correct label", steps=[ScenarioStep(action="goto", value=FIXTURE_URL)])]
    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        scan = client.post(f"/projects/{project['id']}/scans", json={"target_url": FIXTURE_URL, "description": "x"}, headers={"Authorization": f"Bearer {token_a}"}).json()
    run_id = client.post(f"/scans/{scan['id']}/run", headers={"Authorization": f"Bearer {token_a}"}).json()[0]["id"]

    token_b = client.post("/auth/register", json={"email": "b@example.com", "password": "pw"}).json()["access_token"]
    resp = client.get(f"/runs/{run_id}/screenshots/0", headers={"Authorization": f"Bearer {token_b}"})

    assert resp.status_code == 404


def test_screenshot_proxy_returns_404_for_nonexistent_run(authenticated_client):
    resp = authenticated_client.get("/runs/999999/screenshots/0")
    assert resp.status_code == 404
