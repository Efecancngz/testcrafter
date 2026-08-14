import shutil
from pathlib import Path
from unittest.mock import patch
import pytest
from playwright.sync_api import Error as PlaywrightError
from app.crawler import BotChallengeDetected
from app.api.scans import SCREENSHOTS_DIR
import json
from datetime import datetime, timezone
from app.schemas import PageStructure, PageElement, GeneratedScenario, ScenarioStep
from app.models import Scan, Scenario, Run, RunStep
from app.runner import StepResult

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

def test_create_scan_normalizes_target_url_missing_scheme(authenticated_client):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url="https://example.com", elements=[])

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure) as mock_extract, \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = []
        resp = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "example.com",
            "description": "No scheme provided",
        })

    assert resp.status_code == 201
    assert resp.json()["target_url"] == "https://example.com"
    mock_extract.assert_called_once_with("https://example.com")


def test_create_scan_leaves_url_with_scheme_unchanged(authenticated_client):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url="http://example.com", elements=[])

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure) as mock_extract, \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = []
        resp = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "http://example.com",
            "description": "Scheme already provided",
        })

    assert resp.status_code == 201
    assert resp.json()["target_url"] == "http://example.com"
    mock_extract.assert_called_once_with("http://example.com")


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

def test_run_scan_executes_scenarios_and_persists_results(authenticated_client, db_session, monkeypatch, tmp_path):
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

    # 202 is returned immediately with pending/empty-steps placeholders — the
    # actual execution happens in a background task. TestClient runs
    # background tasks to completion before handing the response back, so by
    # the time we get here the run has already finished; we assert the final
    # state via the db_session (which shares the background job's engine).
    assert resp.status_code == 202
    pending_runs = resp.json()
    assert len(pending_runs) == 1
    assert pending_runs[0]["status"] == "pending"
    assert pending_runs[0]["steps"] == []
    run_id = pending_runs[0]["id"]

    db_session.expire_all()
    finished_run = db_session.get(Run, run_id)
    assert finished_run.status == "passed"
    steps = db_session.query(RunStep).filter_by(run_id=run_id).order_by(RunStep.step_index).all()
    assert len(steps) == 2
    assert all(step.status == "passed" for step in steps)
    for index, step in enumerate(steps):
        assert step.screenshot_path == f"/runs/{run_id}/screenshots/{index}"

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


def test_run_scan_returns_202_with_pending_runs_and_empty_steps(authenticated_client, db_session, monkeypatch):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()
    fake_structure = PageStructure(url="https://example.com", elements=[])
    fake_scenarios = [
        GeneratedScenario(title="First", steps=[ScenarioStep(action="goto", value="https://example.com")]),
        GeneratedScenario(title="Second", steps=[ScenarioStep(action="goto", value="https://example.com")]),
    ]
    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        scan = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "two scenarios",
        }).json()

    with patch("app.api.scans.run_scenario", return_value=[StepResult(status="passed", log_message="ok")]):
        resp = authenticated_client.post(f"/scans/{scan['id']}/run")

    assert resp.status_code == 202
    body = resp.json()
    assert len(body) == 2
    for run in body:
        assert run["status"] == "pending"
        assert run["steps"] == []


def test_run_scan_returns_409_when_already_in_progress(authenticated_client, db_session):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()
    fake_structure = PageStructure(url="https://example.com", elements=[])
    fake_scenarios = [GeneratedScenario(title="Only", steps=[ScenarioStep(action="goto", value="https://example.com")])]
    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        scan = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "one scenario",
        }).json()

    scenario_id = db_session.query(Scenario).filter_by(scan_id=scan["id"]).first().id
    db_session.add(Run(scenario_id=scenario_id, status="running", started_at=datetime.now(timezone.utc)))
    db_session.commit()

    resp = authenticated_client.post(f"/scans/{scan['id']}/run")

    assert resp.status_code == 409


def test_run_scan_requires_auth_and_ownership(client):
    resp = client.post("/scans/1/run")
    assert resp.status_code == 401


def test_execute_scan_runs_writes_steps_incrementally_and_finishes(tmp_path, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from app.db import Base, make_engine
    import app.db as db_module
    from app.api.scans import _execute_scan_runs
    from app.models import Project, User

    test_engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(test_engine)
    TestSessionLocal = sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "SessionLocal", TestSessionLocal)

    setup_session = TestSessionLocal()
    user = User(email="runner@example.com", password_hash="x")
    setup_session.add(user)
    setup_session.flush()
    project = Project(user_id=user.id, name="Demo", base_url="https://example.com")
    setup_session.add(project)
    setup_session.flush()
    scan = Scan(project_id=project.id, target_url="https://example.com", description="d", page_structure_json="{}", ai_provider="claude", status="ready")
    setup_session.add(scan)
    setup_session.flush()
    scenario = Scenario(scan_id=scan.id, title="Demo scenario", steps_json=json.dumps([{"action": "goto", "value": "https://example.com"}]))
    setup_session.add(scenario)
    setup_session.flush()
    run = Run(scenario_id=scenario.id, status="pending", started_at=datetime.now(timezone.utc))
    setup_session.add(run)
    setup_session.commit()
    run_id = run.id
    setup_session.close()

    seen_statuses_during_run = []

    def fake_run_scenario(generated, base_url, screenshot_dir, on_step=None):
        check_session = TestSessionLocal()
        seen_statuses_during_run.append(check_session.get(Run, run_id).status)
        check_session.close()
        if on_step is not None:
            on_step(0, StepResult(status="passed", log_message="ok"))
        return [StepResult(status="passed", log_message="ok")]

    with patch("app.api.scans.run_scenario", side_effect=fake_run_scenario):
        _execute_scan_runs([run_id])

    verify_session = TestSessionLocal()
    finished_run = verify_session.get(Run, run_id)
    assert finished_run.status == "passed"
    assert finished_run.finished_at is not None
    steps = verify_session.query(RunStep).filter_by(run_id=run_id).all()
    assert len(steps) == 1
    assert steps[0].status == "passed"
    verify_session.close()


def test_get_scan_runs_returns_current_progress(authenticated_client, db_session):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()
    fake_structure = PageStructure(url="https://example.com", elements=[])
    fake_scenarios = [GeneratedScenario(title="Only", steps=[ScenarioStep(action="goto", value="https://example.com")])]
    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        scan = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "one scenario",
        }).json()

    scenario_id = db_session.query(Scenario).filter_by(scan_id=scan["id"]).first().id
    run = Run(scenario_id=scenario_id, status="running", started_at=datetime.now(timezone.utc))
    db_session.add(run)
    db_session.commit()
    db_session.add(RunStep(run_id=run.id, step_index=0, status="passed", log_message="ok"))
    db_session.commit()

    resp = authenticated_client.get(f"/scans/{scan['id']}/runs")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["status"] == "running"
    assert len(body[0]["steps"]) == 1
    assert body[0]["steps"][0]["status"] == "passed"


def test_get_scan_runs_404_for_other_users_scan(client):
    token_a = client.post("/auth/register", json={"email": "runs-a@example.com", "password": "pw"}).json()["access_token"]
    project = client.post("/projects", json={"name": "A", "base_url": "https://a.example.com"}, headers={"Authorization": f"Bearer {token_a}"}).json()
    fake_structure = PageStructure(url="https://a.example.com", elements=[])
    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = []
        scan = client.post(f"/projects/{project['id']}/scans", json={"target_url": "https://a.example.com", "description": "x"}, headers={"Authorization": f"Bearer {token_a}"}).json()

    token_b = client.post("/auth/register", json={"email": "runs-b@example.com", "password": "pw"}).json()["access_token"]
    resp = client.get(f"/scans/{scan['id']}/runs", headers={"Authorization": f"Bearer {token_b}"})

    assert resp.status_code == 404

    assert seen_statuses_during_run == ["running"]


def test_execute_scan_runs_recovers_from_a_crashed_run_and_continues_to_the_next(tmp_path, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from app.db import Base, make_engine
    import app.db as db_module
    from app.api.scans import _execute_scan_runs
    from app.models import Project, User

    test_engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(test_engine)
    TestSessionLocal = sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "SessionLocal", TestSessionLocal)

    setup_session = TestSessionLocal()
    user = User(email="runner2@example.com", password_hash="x")
    setup_session.add(user)
    setup_session.flush()
    project = Project(user_id=user.id, name="Demo", base_url="https://example.com")
    setup_session.add(project)
    setup_session.flush()
    scan = Scan(project_id=project.id, target_url="https://example.com", description="d", page_structure_json="{}", ai_provider="claude", status="ready")
    setup_session.add(scan)
    setup_session.flush()
    crashing_scenario = Scenario(scan_id=scan.id, title="Crashing scenario", steps_json=json.dumps([{"action": "goto", "value": "https://example.com"}]))
    ok_scenario = Scenario(scan_id=scan.id, title="OK scenario", steps_json=json.dumps([{"action": "goto", "value": "https://example.com"}]))
    setup_session.add(crashing_scenario)
    setup_session.add(ok_scenario)
    setup_session.flush()
    crashing_run = Run(scenario_id=crashing_scenario.id, status="pending", started_at=datetime.now(timezone.utc))
    ok_run = Run(scenario_id=ok_scenario.id, status="pending", started_at=datetime.now(timezone.utc))
    setup_session.add(crashing_run)
    setup_session.add(ok_run)
    setup_session.commit()
    crashing_run_id = crashing_run.id
    ok_run_id = ok_run.id
    setup_session.close()

    calls = []

    def fake_run_scenario(generated, base_url, screenshot_dir, on_step=None):
        calls.append(generated.title)
        if generated.title == "Crashing scenario":
            raise RuntimeError("boom")
        if on_step is not None:
            on_step(0, StepResult(status="passed", log_message="ok"))
        return [StepResult(status="passed", log_message="ok")]

    with patch("app.api.scans.run_scenario", side_effect=fake_run_scenario):
        _execute_scan_runs([crashing_run_id, ok_run_id])

    assert calls == ["Crashing scenario", "OK scenario"]

    verify_session = TestSessionLocal()
    crashed = verify_session.get(Run, crashing_run_id)
    assert crashed.status == "failed"
    assert crashed.finished_at is not None

    ok = verify_session.get(Run, ok_run_id)
    assert ok.status == "passed"
    assert ok.finished_at is not None
    ok_steps = verify_session.query(RunStep).filter_by(run_id=ok_run_id).all()
    assert len(ok_steps) == 1
    verify_session.close()


def test_get_scan_runs_returns_current_progress(authenticated_client, db_session):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()
    fake_structure = PageStructure(url="https://example.com", elements=[])
    fake_scenarios = [GeneratedScenario(title="Only", steps=[ScenarioStep(action="goto", value="https://example.com")])]
    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        scan = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "one scenario",
        }).json()

    scenario_id = db_session.query(Scenario).filter_by(scan_id=scan["id"]).first().id
    run = Run(scenario_id=scenario_id, status="running", started_at=datetime.now(timezone.utc))
    db_session.add(run)
    db_session.commit()
    db_session.add(RunStep(run_id=run.id, step_index=0, status="passed", log_message="ok"))
    db_session.commit()

    resp = authenticated_client.get(f"/scans/{scan['id']}/runs")

    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["status"] == "running"
    assert len(body[0]["steps"]) == 1
    assert body[0]["steps"][0]["status"] == "passed"


def test_get_scan_runs_404_for_other_users_scan(client):
    token_a = client.post("/auth/register", json={"email": "runs-a@example.com", "password": "pw"}).json()["access_token"]
    project = client.post("/projects", json={"name": "A", "base_url": "https://a.example.com"}, headers={"Authorization": f"Bearer {token_a}"}).json()
    fake_structure = PageStructure(url="https://a.example.com", elements=[])
    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = []
        scan = client.post(f"/projects/{project['id']}/scans", json={"target_url": "https://a.example.com", "description": "x"}, headers={"Authorization": f"Bearer {token_a}"}).json()

    token_b = client.post("/auth/register", json={"email": "runs-b@example.com", "password": "pw"}).json()["access_token"]
    resp = client.get(f"/scans/{scan['id']}/runs", headers={"Authorization": f"Bearer {token_b}"})

    assert resp.status_code == 404
