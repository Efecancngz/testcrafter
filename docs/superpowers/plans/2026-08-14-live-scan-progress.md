# Live Scan Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "click Run scenarios, stare at a frozen button for up to 90 seconds" experience with a live, step-by-step accordion that updates as scenarios actually execute, surviving navigation away and back.

**Architecture:** `runner.run_scenario` gains an optional `on_step` callback invoked after each step. `POST /scans/{id}/run` stops running scenarios synchronously — it creates `pending` `Run` rows, hands execution to a FastAPI background task, and returns `202` immediately. The background task opens its own DB session (the request's session is gone by the time it runs), sets each `Run` to `running`, and its `on_step` callback commits each `RunStep` the moment it finishes — short, independent transactions, never one held open for a whole scenario. A new `GET /scans/{id}/runs` endpoint lets the frontend poll (every 1.5s) for current state; the frontend renders that state as a collapsible per-scenario accordion and auto-resumes polling on mount if a run is already in flight.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, SQLite, pytest (backend); React 18, Vite, Tailwind CSS (frontend, no JS test framework — manual verification).

**Spec:** `docs/superpowers/specs/2026-08-14-live-scan-progress-design.md`

## Global Constraints

- Ownership checks always return 404 (never 403) for not-found-or-not-owned, per the existing `_get_owned_scan` pattern in `backend/app/api/scans.py`.
- The background job commits each `RunStep` independently, right after `on_step` fires — never one transaction held open across a whole scenario's execution. (This project has a documented past bug from exactly the opposite pattern, during the screenshot-capture feature.)
- The background job uses its own `SessionLocal()` session, never the request-scoped `Depends(get_session)` session — that session closes when the request returns, before the background job's first write.
- `runner.run_scenario`'s existing signature and return value must keep working unchanged for callers that don't pass `on_step` — this is an additive, backward-compatible change.
- No JS test framework in this project — frontend tasks are verified by manual browser checks, not automated tests.
- Commit messages must never include an AI co-author trailer (project-wide rule).
- `Run.status` and `RunStep.status` are plain `String` columns (no DB-level enum/check constraint) — adding the `"running"` value needs no Alembic migration.

---

## Task 1: `on_step` callback in the runner

**Files:**
- Modify: `backend/app/runner.py`
- Test: `backend/tests/test_runner.py`

**Interfaces:**
- Produces: `run_scenario(scenario, base_url, screenshot_dir, on_step: Callable[[int, StepResult], None] | None = None) -> list[StepResult]` — `on_step`, when given, is called once per step immediately after that step finishes, with the step's index and its `StepResult`. Consumed by Task 2's background job.

- [ ] **Step 1: Write the failing test**

In `backend/tests/test_runner.py`, append:

```python
def test_run_scenario_calls_on_step_after_each_step(tmp_path):
    scenario = GeneratedScenario(
        title="Two steps",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_text", selector="#submit", expected="Log in"),
        ],
    )

    calls = []
    def on_step(index, result):
        calls.append((index, result.status))

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path, on_step=on_step)

    assert calls == [(0, "passed"), (1, "passed")]
    assert len(results) == 2


def test_run_scenario_without_on_step_still_works(tmp_path):
    scenario = GeneratedScenario(
        title="No callback provided",
        steps=[ScenarioStep(action="goto", value=FIXTURE_URL)],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert results[0].status == "passed"
```

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `pytest tests/test_runner.py -k test_run_scenario_calls_on_step -v`
Expected: FAIL — `run_scenario() got an unexpected keyword argument 'on_step'`.

- [ ] **Step 3: Implement the callback**

In `backend/app/runner.py`, add `Callable` to the imports and update `run_scenario`:

```python
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from playwright.sync_api import sync_playwright
from app.browser import BROWSER_ARGS, NAVIGATION_TIMEOUT_MS, WAIT_UNTIL
from app.schemas import GeneratedScenario
```

```python
def run_scenario(
    scenario: GeneratedScenario,
    base_url: str,
    screenshot_dir: Path,
    on_step: Callable[[int, "StepResult"], None] | None = None,
) -> list[StepResult]:
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    results: list[StepResult] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(args=BROWSER_ARGS)
        page = browser.new_page()
        try:
            for index, step in enumerate(scenario.steps):
                result = _run_step(page, step, base_url, screenshot_dir, index)
                results.append(result)
                if on_step is not None:
                    on_step(index, result)
        finally:
            browser.close()
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runner.py -v`
Expected: All PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/runner.py backend/tests/test_runner.py
git commit -m "feat: add on_step callback to run_scenario"
```

---

## Task 2: Background execution for `POST /scans/{id}/run`

**Files:**
- Modify: `backend/app/api/scans.py`
- Test: `backend/tests/test_api_scans.py`

**Interfaces:**
- Consumes: `run_scenario(..., on_step=...)` from Task 1.
- Produces: `_execute_scan_runs(run_ids: list[int]) -> None` — the background job function, importable and directly callable from tests (not just reachable through HTTP). `POST /scans/{scan_id}/run` now returns `202` with `list[RunOut]` where every run has `status="pending"` and `steps=[]`, or `409` if a run for this scan is already `pending`/`running`. Consumed by Task 3 (shares the same `Run`/`RunStep` shapes) and by Task 4's frontend client.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_api_scans.py`, the top of the file currently reads:

```python
import shutil
from pathlib import Path
from unittest.mock import patch
import pytest
from playwright.sync_api import Error as PlaywrightError
from app.crawler import BotChallengeDetected
from app.api.scans import SCREENSHOTS_DIR
from app.schemas import PageStructure, PageElement, GeneratedScenario, ScenarioStep
from app.models import Scan
```

Replace the last two lines and add what the new tests need:

```python
import json
from datetime import datetime, timezone
from app.schemas import PageStructure, PageElement, GeneratedScenario, ScenarioStep
from app.models import Scan, Scenario, Run, RunStep
from app.runner import StepResult
```

Then append these tests:

```python
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

    assert seen_statuses_during_run == ["running"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_scans.py -k "run_scan_returns or execute_scan_runs" -v`
Expected: FAIL — `409` test fails because there's no conflict guard yet; `202` test fails because the endpoint still returns `200` with full results; `_execute_scan_runs` test fails with `ImportError`.

- [ ] **Step 3: Implement the background job and the new endpoint behavior**

In `backend/app/api/scans.py`, update the imports:

```python
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from playwright.sync_api import Error as PlaywrightError
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from app.db import get_session, SessionLocal
from app.models import Project, Run, RunStep, Scan, Scenario, User
from app.auth import get_current_user
from app.crawler import extract_page_structure, BotChallengeDetected
from app.ai.base import AIProvider
from app.runner import run_scenario
from app.schemas import GeneratedScenario, ScenarioStep
```

Replace the existing `run_scan` function (the one currently decorated `@router.post("/scans/{scan_id}/run", response_model=list[RunOut])`) with:

```python
def _execute_scan_runs(run_ids: list[int]) -> None:
    session = SessionLocal()
    try:
        for run_id in run_ids:
            run = session.get(Run, run_id)
            scenario = session.get(Scenario, run.scenario_id)
            steps = [ScenarioStep(**s) for s in json.loads(scenario.steps_json)]
            generated = GeneratedScenario(title=scenario.title, steps=steps)

            run.status = "running"
            session.commit()

            def on_step(index: int, result, run_id=run.id):
                screenshot_path = f"/runs/{run_id}/screenshots/{index}" if result.screenshot_path else None
                session.add(RunStep(run_id=run_id, step_index=index, status=result.status, log_message=result.log_message, screenshot_path=screenshot_path))
                session.commit()

            results = run_scenario(generated, base_url="", screenshot_dir=SCREENSHOTS_DIR / str(run.id), on_step=on_step)

            run.finished_at = datetime.now(timezone.utc)
            run.status = "passed" if all(r.status == "passed" for r in results) else "failed"
            session.commit()
    finally:
        session.close()

@router.post("/scans/{scan_id}/run", response_model=list[RunOut], status_code=202)
def run_scan(scan_id: int, background_tasks: BackgroundTasks, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    scan = _get_owned_scan(scan_id, user, session)

    scenarios = session.query(Scenario).filter_by(scan_id=scan.id).all()
    scenario_ids = [s.id for s in scenarios]

    in_flight = (
        session.query(Run)
        .filter(Run.scenario_id.in_(scenario_ids), Run.status.in_(["pending", "running"]))
        .first()
    )
    if in_flight is not None:
        raise HTTPException(status_code=409, detail="a run is already in progress for this scan")

    runs: list[Run] = []
    for scenario in scenarios:
        run = Run(scenario_id=scenario.id, status="pending", started_at=datetime.now(timezone.utc), finished_at=None)
        session.add(run)
        runs.append(run)
    session.commit()
    for run in runs:
        session.refresh(run)

    background_tasks.add_task(_execute_scan_runs, [run.id for run in runs])

    return [
        RunOut(id=run.id, scenario_id=run.scenario_id, status=run.status, started_at=run.started_at, finished_at=run.finished_at, steps=[])
        for run in runs
    ]
```

This replaces the old synchronous loop entirely — the old version's per-scenario `run_scenario(...)` call, its post-hoc `for index, result in enumerate(results): session.add(RunStep(...))` loop, and its final aggregation into a returned list are all gone; `_execute_scan_runs` now owns that work, run per background-task invocation, with `RunStep` rows written by `on_step` as they happen instead of after the fact.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_scans.py -v`
Expected: All PASS, including the 4 new tests.

- [ ] **Step 5: Run the full backend suite**

Run: `pytest -v`
Expected: All PASS (68+ tests, no regressions — the old `test_create_scan_generates_scenarios`-style tests that exercise `POST /projects/{id}/scans` are untouched by this change; only `POST /scans/{id}/run` behavior changed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/scans.py backend/tests/test_api_scans.py
git commit -m "feat: run scans in the background, return 202 immediately"
```

---

## Task 3: `GET /scans/{scan_id}/runs` polling endpoint

**Files:**
- Modify: `backend/app/api/scans.py`
- Test: `backend/tests/test_api_scans.py`

**Interfaces:**
- Consumes: `Run`, `RunStep`, `RunOut`, `RunStepOut`, `_get_owned_scan` (all already in `scans.py`).
- Produces: `GET /scans/{scan_id}/runs` → `list[RunOut]`, ordered by `Run.id`, each with its current `RunStep` rows (however many have been written so far). Consumed by Task 4's frontend `listScanRuns` client function.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_api_scans.py`, append:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api_scans.py -k test_get_scan_runs -v`
Expected: FAIL — route doesn't exist yet.

- [ ] **Step 3: Implement the endpoint**

In `backend/app/api/scans.py`, add after `run_scan`:

```python
@router.get("/scans/{scan_id}/runs", response_model=list[RunOut])
def get_scan_runs(scan_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    scan = _get_owned_scan(scan_id, user, session)
    scenario_ids = [s.id for s in session.query(Scenario).filter_by(scan_id=scan.id).all()]
    runs = session.query(Run).filter(Run.scenario_id.in_(scenario_ids)).order_by(Run.id).all()

    run_ids = [r.id for r in runs]
    steps_by_run: dict[int, list[RunStep]] = {rid: [] for rid in run_ids}
    for step in session.query(RunStep).filter(RunStep.run_id.in_(run_ids)).order_by(RunStep.step_index).all():
        steps_by_run[step.run_id].append(step)

    return [
        RunOut(id=r.id, scenario_id=r.scenario_id, status=r.status, started_at=r.started_at, finished_at=r.finished_at, steps=steps_by_run[r.id])
        for r in runs
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api_scans.py -v`
Expected: All PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `pytest -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/scans.py backend/tests/test_api_scans.py
git commit -m "feat: add GET /scans/{id}/runs polling endpoint"
```

---

## Task 4: Frontend API client — `listScanRuns` and 409 awareness

**Files:**
- Modify: `frontend/src/api.js`

**Interfaces:**
- Produces: `listScanRuns(scanId) -> Promise<RunOut[]>`, calling `GET /scans/{id}/runs`. `runScan(scanId)`'s existing behavior (calls `POST /scans/{id}/run`, returns the parsed body, throws an `Error` with `.status` set on any non-2xx response — including `409`) needs no code change, since `handleResponse` already attaches `.status` to thrown errors and already treats any `res.ok` response (200–299, which includes the new `202`) as success. Consumed by Task 6's `ScanDetailPage`.

- [ ] **Step 1: Add `listScanRuns`**

In `frontend/src/api.js`, add after `runScan`:

```js
export async function listScanRuns(scanId) {
  const res = await fetch(`${BASE_URL}/scans/${scanId}/runs`, { headers: { ...authHeaders() } });
  return handleResponse(res);
}
```

- [ ] **Step 2: Verify build**

Run: `npm run build` (from `frontend/`)
Expected: Build succeeds with no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api.js
git commit -m "feat: add listScanRuns API client function"
```

---

## Task 5: `RunAccordion` component

**Files:**
- Create: `frontend/src/components/RunAccordion.jsx`

**Interfaces:**
- Consumes: `Screenshot` component (`frontend/src/components/Screenshot.jsx`, unchanged — already handles its own lazy fetch-on-mount, so lazy loading here means only mounting it when a step is expanded, not eagerly for every step with a `screenshot_path`).
- Produces: `<RunAccordion runs={runs} scenarios={scenarios} />` — `runs` is the array returned by `runScan`/`listScanRuns` (`{id, scenario_id, status, started_at, finished_at, steps: [{id, step_index, status, log_message, screenshot_path}]}`); `scenarios` is `scan.scenarios` from `getScan` (`{id, title, steps_json}[]`), used to look up each run's scenario title and total step count. Consumed by Task 6's `ScanDetailPage`.

- [ ] **Step 1: Create the component**

Create `frontend/src/components/RunAccordion.jsx`:

```jsx
import { useState } from "react";
import Screenshot from "./Screenshot";

const RUN_ICON = { passed: "✓", running: "●", pending: "○", failed: "✗" };
const STEP_ICON = { passed: "✓", failed: "✗" };

function parsedScenarioSteps(scenario) {
  try {
    return JSON.parse(scenario.steps_json);
  } catch {
    return [];
  }
}

function formatDuration(startedAt, finishedAt) {
  if (!startedAt || !finishedAt) return null;
  const seconds = (new Date(finishedAt) - new Date(startedAt)) / 1000;
  if (!Number.isFinite(seconds) || seconds < 0) return null;
  return `${seconds.toFixed(1)}s`;
}

function stepLabel(plannedStep, result) {
  // plannedStep (from the scenario's own steps_json, e.g. {action, selector,
  // value, expected}) has the action name and selector/value; result (the
  // executed RunStepOut, if this step has run yet) has only status/log_message.
  // Combine them: action name always shown, plus a short hint and, on
  // failure, the real error instead of a generic status word.
  const action = plannedStep?.action || "?";
  const hint = plannedStep?.selector || plannedStep?.expected || plannedStep?.value || null;
  const parts = [action];
  if (hint) parts.push(hint);
  if (result && result.status === "failed" && result.log_message) {
    parts.push(`— ${result.log_message}`);
  }
  return parts.join("  ");
}

export default function RunAccordion({ runs, scenarios }) {
  const [manualOpen, setManualOpen] = useState({});
  const [expandedSteps, setExpandedSteps] = useState({});

  const scenarioById = {};
  for (const s of scenarios) scenarioById[s.id] = s;

  const anyRunning = runs.some((r) => r.status === "running");
  const firstRunId = runs[0]?.id;

  function isOpen(run) {
    if (Object.prototype.hasOwnProperty.call(manualOpen, run.id)) {
      return manualOpen[run.id];
    }
    if (run.status === "running") return true;
    if (!anyRunning && run.id === firstRunId) return true;
    return false;
  }

  function toggleRun(runId) {
    setManualOpen((prev) => ({ ...prev, [runId]: !isOpenFor(runId) }));
  }

  function isOpenFor(runId) {
    const run = runs.find((r) => r.id === runId);
    return run ? isOpen(run) : false;
  }

  function toggleStep(key) {
    setExpandedSteps((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <ul className="space-y-2">
      {runs.map((run) => {
        const scenario = scenarioById[run.scenario_id];
        const plannedSteps = scenario ? parsedScenarioSteps(scenario) : [];
        const totalSteps = plannedSteps.length || run.steps.length;
        const completed = run.steps.length;
        const open = isOpen(run);
        const duration = formatDuration(run.started_at, run.finished_at);
        const statusLabel =
          run.status === "running" ? "running…" : run.status === "pending" ? "queued" : duration || run.status;

        return (
          <li key={run.id} className="rounded-md border border-border">
            <button
              type="button"
              onClick={() => toggleRun(run.id)}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
            >
              <span className="w-4 text-muted-foreground">{RUN_ICON[run.status] || "○"}</span>
              <span className="flex-1">{scenario ? scenario.title : `Scenario ${run.scenario_id}`}</span>
              <span className="text-xs text-muted-foreground">
                {completed}/{totalSteps} {statusLabel}
              </span>
            </button>

            {open && (
              <ul className="space-y-1 border-t border-border px-3 py-2 pl-7">
                {Array.from({ length: totalSteps }).map((_, index) => {
                  const step = run.steps.find((s) => s.step_index === index);
                  const key = `${run.id}-${index}`;
                  const plannedStep = plannedSteps[index];
                  return (
                    <li key={key} className="text-sm">
                      <div className="flex items-center gap-2">
                        <span className="w-4 text-muted-foreground">
                          {step ? STEP_ICON[step.status] || "?" : "○"}
                        </span>
                        <span>{stepLabel(plannedStep, step)}</span>
                        {step && step.screenshot_path && (
                          <button
                            type="button"
                            onClick={() => toggleStep(key)}
                            className="text-xs text-muted-foreground hover:text-foreground hover:underline"
                          >
                            {expandedSteps[key] ? "hide screenshot" : "show screenshot"}
                          </button>
                        )}
                      </div>
                      {step && step.screenshot_path && expandedSteps[key] && (
                        <div className="mt-1 pl-6">
                          <Screenshot path={step.screenshot_path} stepIndex={index} />
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </li>
        );
      })}
    </ul>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `npm run build` (from `frontend/`)
Expected: Build succeeds — this component isn't wired into any page yet (Task 6 does that), so a clean build with no syntax/import errors is the bar.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/RunAccordion.jsx
git commit -m "feat: add RunAccordion component"
```

---

## Task 6: Wire polling into `ScanDetailPage`

**Files:**
- Modify: `frontend/src/pages/ScanDetailPage.jsx`

**Interfaces:**
- Consumes: `runScan`, `listScanRuns` (Task 4), `RunAccordion` (Task 5).
- Produces: final integrated page — no further tasks depend on this, it's the last task in the plan.

- [ ] **Step 1: Rewrite `ScanDetailPage.jsx`**

Replace the entire contents of `frontend/src/pages/ScanDetailPage.jsx`:

```jsx
import { useState, useEffect, useRef } from "react";
import { useParams } from "react-router-dom";
import { getScan, runScan, listScanRuns } from "../api";
import StatusBadge from "../components/StatusBadge";
import RunAccordion from "../components/RunAccordion";

const POLL_INTERVAL_MS = 1500;

function hasInFlightRun(runs) {
  return runs.some((r) => r.status === "pending" || r.status === "running");
}

export default function ScanDetailPage() {
  const { scanId } = useParams();
  const [scan, setScan] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [runs, setRuns] = useState(null);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    setNotFound(false);
    setRuns(null);
    getScan(scanId)
      .then(setScan)
      .catch((err) => {
        if (err.status === 404) {
          setNotFound(true);
        } else {
          setError(err.message);
        }
      });
    listScanRuns(scanId)
      .then((fetchedRuns) => {
        setRuns(fetchedRuns);
        if (hasInFlightRun(fetchedRuns)) {
          startPolling();
        }
      })
      .catch(() => {
        // No runs yet is not an error state here; getScan's own error
        // handling above covers real fetch failures for this scan.
      });

    return stopPolling;
  }, [scanId]);

  function startPolling() {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const latest = await listScanRuns(scanId);
        setRuns(latest);
        if (!hasInFlightRun(latest)) {
          stopPolling();
        }
      } catch {
        // Transient poll failure: retried on the next tick, no error shown.
      }
    }, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }

  async function handleRun() {
    setError(null);
    setStarting(true);
    try {
      const pendingRuns = await runScan(scanId);
      setRuns(pendingRuns);
      startPolling();
    } catch (err) {
      if (err.status === 409) {
        const latest = await listScanRuns(scanId);
        setRuns(latest);
        startPolling();
      } else {
        setError(err.message);
      }
    } finally {
      setStarting(false);
    }
  }

  if (notFound) {
    return <p className="text-sm text-muted-foreground">Scan not found.</p>;
  }

  if (!scan) {
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  }

  const running = hasInFlightRun(runs || []);

  return (
    <div>
      <h1 className="mb-1 text-xl font-semibold tracking-tight">{scan.target_url}</h1>
      <div className="mb-6">
        <StatusBadge status={scan.status} />
      </div>

      {scan.status === "blocked" && (
        <p className="mb-4 text-sm text-yellow-400">
          This site uses {scan.blocked_reason} bot protection and couldn't be scanned.
        </p>
      )}

      {error && <p className="mb-4 text-sm text-red-400">{error}</p>}

      <ul className="mb-6 space-y-1 text-sm">
        {scan.scenarios.map((s) => (
          <li key={s.id}>{s.title}</li>
        ))}
      </ul>

      {scan.status === "ready" && (
        <button
          onClick={handleRun}
          disabled={starting || running}
          className="mb-6 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {starting || running ? "Running..." : "Run scenarios"}
        </button>
      )}

      {runs && runs.length > 0 && (
        <div>
          <h2 className="mb-3 text-lg font-semibold tracking-tight">Results</h2>
          <RunAccordion runs={runs} scenarios={scan.scenarios} />
        </div>
      )}
    </div>
  );
}
```

Note what changed from the previous version: the old flat `<ul>` of runs (with `Step {index}: {status}` text and an always-mounted `Screenshot`) is replaced by `<RunAccordion>`; `running` (the old local boolean set only during the request) is replaced by `starting` (true only while the `POST /run` call itself is in flight) plus `running` derived from `runs` (true whenever any run is `pending`/`running`), so the button stays disabled and reads "Running..." for the entire duration of execution, not just the initial request; a `listScanRuns` call is added on mount so navigating back to an in-progress scan resumes polling automatically; a `409` from `runScan` is treated as "someone/something already started this — start watching," not an error.

- [ ] **Step 2: Manual verification**

Start both servers (`uvicorn app.main:app --reload` from `backend/`, `npm run dev` from `frontend/` — or `docker compose up` if that's how you're running it; if using Docker, remember `docker compose restart backend` after backend code changes, since it doesn't run with `--reload`). In a browser:

1. Open a `ready` scan with 2+ scenarios, click "Run scenarios". Confirm the accordion appears immediately with all scenarios showing `0/N queued`, button reads "Running..." and stays disabled.
2. Watch it update roughly every 1.5s: the running scenario expands automatically, its step icons fill in one at a time (○ → ✓/✗), the step count climbs.
3. Click a step with a screenshot — confirm it expands and loads the image; click again — confirm it collapses. Confirm steps without a screenshot show no such button.
4. Manually expand a currently-collapsed (not-yet-running) scenario, then wait for a poll tick — confirm your manual expand isn't overridden back to collapsed.
5. Mid-run, navigate to the project list and back to this scan. Confirm the accordion reflects current progress immediately and polling resumes (icons keep advancing) without clicking "Run scenarios" again.
6. Open the same scan in a second browser tab while a run is in progress; click "Run scenarios" there too. Confirm no error is shown and the second tab starts showing the same live progress (this is the `409`-as-"start watching" path).
7. Wait for the run to finish. Confirm the button re-enables, reads "Run scenarios" again, and polling stops (no more network requests to `/scans/{id}/runs` in the browser's network tab).
8. Reload the page after a run has finished. Confirm the accordion shows the final state (no polling starts, since nothing is `pending`/`running`).

- [ ] **Step 3: Run the backend suite one more time (regression check)**

Run: `pytest -v` (from `backend/`)
Expected: All tests PASS — this task touches no backend code, but confirms nothing in the manual walkthrough required a backend change that was missed.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ScanDetailPage.jsx
git commit -m "feat: wire live polling and accordion into ScanDetailPage"
```

---

## Self-Review Notes

- **Spec coverage:** `on_step` callback (spec's Execution model) → Task 1. `202` + pending `Run` creation + `409` guard + background job with independent-commit `on_step` writes + separate `SessionLocal` session (spec's Backend section, including the explicit "don't hold a transaction open" and "don't reuse the request session" constraints) → Task 2. `GET /scans/{id}/runs` (spec's New endpoint) → Task 3. Status vocabulary (`running` added, no migration needed) → Task 2, called out in Global Constraints. Frontend polling every 1.5s, resume-on-mount, `409`-as-watch, accordion visuals (collapsed row format, default-open logic including the "no run running yet → open the first one" edge case caught in the spec's own self-review, manual-expand not overridden by polling, lazy per-step screenshot loading, step action/hint display replacing raw `Step N: status`) → Tasks 4–6. Error handling (step failure is data not a request error; polling failures retried silently; `409` is not an error) → Task 6. Out-of-scope items (SSE, cancellation, global concurrency limits, a dedicated "skipped" status) are correctly absent from every task.
- **Placeholder scan:** No TBD/TODO markers. `RunAccordion`'s step rows need the spec's "actual action name plus a short selector/value hint" — `RunStepOut` (the executed-step data) only carries `status`/`log_message`, not the action/selector/value. Rather than settle for a partial substitute, `stepLabel` reads the action/selector/value straight from the scenario's own `steps_json` (already sent to the frontend, parsed once for the step count) and combines it with the executed result's `log_message` on failure — a real implementation of the spec's requirement, not a workaround for a missing field.
- **Type consistency:** `_execute_scan_runs(run_ids: list[int])` (Task 2) is imported and called identically by its own test and by `run_scan`'s `background_tasks.add_task(_execute_scan_runs, [...])` call. `RunOut`'s shape (`id`, `scenario_id`, `status`, `started_at`, `finished_at`, `steps`) is unchanged by this plan and used identically by both `POST /run` (Task 2) and `GET /runs` (Task 3). `listScanRuns` (Task 4) returns exactly that shape, consumed identically by `RunAccordion` (Task 5) and `ScanDetailPage` (Task 6) — `run.steps[].step_index`/`status`/`log_message`/`screenshot_path` field names match `RunStepOut` throughout.
