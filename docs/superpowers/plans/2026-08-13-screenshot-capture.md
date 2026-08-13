# Screenshot Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture a Playwright screenshot after every scenario step (pass or fail), persist it to local disk under `backend/data/screenshots/{run_id}/{step_index}.png`, serve it via a FastAPI static mount at `/screenshots/...`, record the URL path on `RunStep.screenshot_path`, and display it in the frontend results view.

**Architecture:** `runner.py`'s `_run_step`/`run_scenario` take a `screenshot_dir` and capture after each step. `scans.py::run_scan` is reordered to create the `Run` row (and get its id) before calling `run_scenario`, so screenshots can be organized by `run_id`. `main.py` mounts the screenshots directory as static files. The frontend renders an `<img>` per step when `screenshot_path` is present.

**Tech Stack:** Playwright's `page.screenshot(path=...)`, FastAPI's `StaticFiles` mount — no new dependencies.

## Global Constraints

- Screenshot capture must never change a step's `status`/`log_message` outcome — a screenshot failure (e.g. page already closed) is caught, logged, and leaves `screenshot_path=None`, nothing else.
- DB-stored path format is exactly `/screenshots/{run_id}/{step_index}.png` (the URL path, not a filesystem path).
- No new external dependencies; no cloud/object storage; no cleanup/retention policy — local disk only, matching MVP scope.
- Follow existing repo conventions: no comments except non-obvious WHY, no speculative abstractions.
- Never add a "Co-Authored-By: Claude" (or any AI attribution) trailer to commits — hard rule for this repo.

---

## Task 1: Runner captures screenshots per step

**Files:**
- Modify: `backend/app/runner.py`
- Modify: `backend/tests/test_runner.py`

**Interfaces:**
- Consumes: `GeneratedScenario`/`ScenarioStep` (`backend/app/schemas.py`, unchanged).
- Produces: `StepResult(status: str, log_message: str, screenshot_path: str | None = None)` — the new field. `run_scenario(scenario: GeneratedScenario, base_url: str, screenshot_dir: Path) -> list[StepResult]` — `screenshot_dir` is now a required third parameter. `screenshot_path` on each returned `StepResult` is the filesystem path string `str(screenshot_dir / f"{index}.png")` (not yet the `/screenshots/...` URL — that translation happens in Task 2, at the `scans.py` call site, since only that layer knows the URL-mount convention). Task 2 imports and calls `run_scenario` with this exact signature.

- [ ] **Step 1: Write the failing tests**

Modify `backend/tests/test_runner.py` — replace its full contents:

```python
from pathlib import Path
from app.schemas import GeneratedScenario, ScenarioStep
from app.runner import run_scenario

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "login_page.html").as_uri()

def test_run_scenario_passes_when_expectation_met(tmp_path):
    scenario = GeneratedScenario(
        title="Submit button has correct label",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_text", selector="#submit", expected="Log in"),
        ],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert all(r.status == "passed" for r in results)
    assert len(results) == 2

def test_run_scenario_fails_when_expectation_not_met(tmp_path):
    scenario = GeneratedScenario(
        title="Submit button has wrong label",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_text", selector="#submit", expected="Sign up"),
        ],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert results[-1].status == "failed"

def test_run_scenario_captures_screenshot_per_step(tmp_path):
    scenario = GeneratedScenario(
        title="Submit button has correct label",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_text", selector="#submit", expected="Log in"),
        ],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert len(results) == 2
    for index, result in enumerate(results):
        assert result.screenshot_path == str(tmp_path / f"{index}.png")
        assert (tmp_path / f"{index}.png").exists()

def test_run_scenario_screenshot_failure_does_not_change_step_status(tmp_path, monkeypatch):
    scenario = GeneratedScenario(
        title="Submit button has correct label",
        steps=[ScenarioStep(action="goto", value=FIXTURE_URL)],
    )

    from playwright.sync_api import Page
    def broken_screenshot(self, **kwargs):
        raise RuntimeError("simulated screenshot failure")
    monkeypatch.setattr(Page, "screenshot", broken_screenshot)

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert len(results) == 1
    assert results[0].status == "passed"
    assert results[0].screenshot_path is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_runner.py -v`
Expected: FAIL — `run_scenario() got an unexpected keyword argument 'screenshot_dir'` (or `TypeError: missing 1 required positional argument`) on all 4 tests.

- [ ] **Step 3: Implement screenshot capture**

Replace the full contents of `backend/app/runner.py`:

```python
import logging
from dataclasses import dataclass
from pathlib import Path
from playwright.sync_api import sync_playwright
from app.schemas import GeneratedScenario

logger = logging.getLogger(__name__)

@dataclass
class StepResult:
    status: str
    log_message: str
    screenshot_path: str | None = None

def run_scenario(scenario: GeneratedScenario, base_url: str, screenshot_dir: Path) -> list[StepResult]:
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    results: list[StepResult] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            for index, step in enumerate(scenario.steps):
                results.append(_run_step(page, step, base_url, screenshot_dir, index))
        finally:
            browser.close()
    return results

def _run_step(page, step, base_url: str, screenshot_dir: Path, step_index: int) -> StepResult:
    try:
        if step.action == "goto":
            page.goto(step.value)
        elif step.action == "click":
            page.click(step.selector)
        elif step.action == "fill":
            page.fill(step.selector, step.value)
        elif step.action == "expect_text":
            actual = page.text_content(step.selector) or ""
            if step.expected not in actual:
                return _finish(page, screenshot_dir, step_index, "failed", f"expected '{step.expected}' in '{actual}'")
        elif step.action == "expect_url":
            if step.expected not in page.url:
                return _finish(page, screenshot_dir, step_index, "failed", f"expected url containing '{step.expected}', got '{page.url}'")
        else:
            return _finish(page, screenshot_dir, step_index, "failed", f"unknown action: {step.action}")
        return _finish(page, screenshot_dir, step_index, "passed", "ok")
    except Exception as exc:
        return _finish(page, screenshot_dir, step_index, "failed", str(exc))

def _finish(page, screenshot_dir: Path, step_index: int, status: str, log_message: str) -> StepResult:
    screenshot_path = screenshot_dir / f"{step_index}.png"
    try:
        page.screenshot(path=screenshot_path)
        captured_path = str(screenshot_path)
    except Exception:
        logger.exception("screenshot capture failed for step %d", step_index)
        captured_path = None
    return StepResult(status=status, log_message=log_message, screenshot_path=captured_path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_runner.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/runner.py backend/tests/test_runner.py
git commit -m "feat: capture a screenshot after every scenario step"
```

---

## Task 2: Wire screenshots into the API (persist path, serve statically)

**Files:**
- Modify: `backend/app/api/scans.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api_scans.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `run_scenario(scenario, base_url, screenshot_dir)` and `StepResult.screenshot_path` from Task 1 (exact signature above).
- Produces: `SCREENSHOTS_DIR` constant in `backend/app/api/scans.py` (a `pathlib.Path`), imported by `backend/app/main.py` for the static mount. `RunStepOut.screenshot_path: str | None`. No other task depends on further new symbols from this task.

- [ ] **Step 1: Add `.gitignore` entry**

Add to `.gitignore`:

```
backend/data/
```

- [ ] **Step 2: Write the failing test**

In `backend/tests/test_api_scans.py`, modify `test_run_scan_executes_scenarios_and_persists_results` to assert screenshot paths, and add `monkeypatch` as a parameter (already imported implicitly via pytest — no new import needed, `monkeypatch` is a built-in pytest fixture). Change the test's signature and body:

```python
def test_run_scan_executes_scenarios_and_persists_results(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.scans.SCREENSHOTS_DIR", tmp_path)

    project = client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

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
        scan = client.post(f"/projects/{project['id']}/scans", json={
            "target_url": FIXTURE_URL,
            "description": "Check submit button label",
        }).json()

    resp = client.post(f"/scans/{scan['id']}/run")

    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "passed"
    assert len(runs[0]["steps"]) == 2
    assert all(step["status"] == "passed" for step in runs[0]["steps"])
    run_id = runs[0]["id"]
    for index, step in enumerate(runs[0]["steps"]):
        assert step["screenshot_path"] == f"/screenshots/{run_id}/{index}.png"
```

(This replaces the existing body of that test — the only additions are the `monkeypatch`/`tmp_path` params, the `monkeypatch.setattr` line, and the final `for` loop assertion.)

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_api_scans.py::test_run_scan_executes_scenarios_and_persists_results -v`
Expected: FAIL — `TypeError: run_scenario() missing 1 required positional argument: 'screenshot_dir'` (Task 1 changed the signature, this call site hasn't been updated yet), and/or `screenshot_path` KeyError since `RunStepOut` doesn't have the field yet.

- [ ] **Step 4: Implement the wiring**

In `backend/app/api/scans.py`, add near the top (after existing imports):

```python
from pathlib import Path
from app.runner import run_scenario

SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "screenshots"
```

(Note: `run_scenario` and `RunStep`/`Scenario` imports may already partially exist — check the current top of the file and merge, don't duplicate.)

Add `screenshot_path: str | None = None` to `RunStepOut`:

```python
class RunStepOut(BaseModel):
    id: int
    step_index: int
    status: str
    log_message: str | None = None
    screenshot_path: str | None = None
    model_config = {"from_attributes": True}
```

In `run_scan`, replace the per-scenario loop body. Current code (approximate):

```python
    for scenario in scenarios:
        steps = [ScenarioStep(**s) for s in json.loads(scenario.steps_json)]
        generated = GeneratedScenario(title=scenario.title, steps=steps)

        started_at = datetime.now(timezone.utc)
        results = run_scenario(generated, base_url="")
        finished_at = datetime.now(timezone.utc)
        run_status = "passed" if all(r.status == "passed" for r in results) else "failed"

        run = Run(scenario_id=scenario.id, status=run_status, started_at=started_at, finished_at=finished_at)
        session.add(run)
        session.flush()
        for index, result in enumerate(results):
            session.add(RunStep(run_id=run.id, step_index=index, status=result.status, log_message=result.log_message))
        runs.append(run)
```

Replace with (create the `Run` row first to get `run.id`, then run the scenario into a `run_id`-scoped screenshot directory, then finalize the run's status/timestamps):

```python
    for scenario in scenarios:
        steps = [ScenarioStep(**s) for s in json.loads(scenario.steps_json)]
        generated = GeneratedScenario(title=scenario.title, steps=steps)

        run = Run(scenario_id=scenario.id, status="pending", started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc))
        session.add(run)
        session.flush()

        results = run_scenario(generated, base_url="", screenshot_dir=SCREENSHOTS_DIR / str(run.id))
        run.finished_at = datetime.now(timezone.utc)
        run.status = "passed" if all(r.status == "passed" for r in results) else "failed"

        for index, result in enumerate(results):
            screenshot_path = f"/screenshots/{run.id}/{index}.png" if result.screenshot_path else None
            session.add(RunStep(run_id=run.id, step_index=index, status=result.status, log_message=result.log_message, screenshot_path=screenshot_path))
        runs.append(run)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api_scans.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 6: Mount static files in `main.py`**

In `backend/app/main.py`, add the import and mount:

```python
from fastapi.staticfiles import StaticFiles
from app.api.scans import SCREENSHOTS_DIR
```

Add near the top of the file, after `SCREENSHOTS_DIR` import, before `app.include_router(...)` calls:

```python
SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots")
```

- [ ] **Step 7: Run the full backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS, all tests green (20+ tests, no regressions).

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/scans.py backend/app/main.py backend/tests/test_api_scans.py .gitignore
git commit -m "feat: persist and serve screenshot paths for scenario runs"
```

---

## Task 3: Frontend display + documentation

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/api.js`
- Modify: `docs/data-model.md`
- Modify: `docs/api-spec.md`

**Interfaces:**
- Consumes: `RunOut.steps[].screenshot_path` from Task 2's API response — no code-level interface, just the JSON shape.
- Produces: nothing consumed by later tasks (final task in this plan).

- [ ] **Step 1: Export `BASE_URL` from `api.js`**

In `frontend/src/api.js`, change:

```js
const BASE_URL = "http://localhost:8000";
```

to:

```js
export const BASE_URL = "http://localhost:8000";
```

- [ ] **Step 2: Render screenshots in `App.jsx`**

In `frontend/src/App.jsx`, add the import:

```js
import { createProject, createScan, runScan, BASE_URL } from "./api";
```

(replacing the existing `import { createProject, createScan, runScan } from "./api";` line)

In the results rendering section, change:

```jsx
                  {run.steps.map((step) => (
                    <li key={step.id}>
                      Step {step.step_index}: {step.status} {step.log_message ? `— ${step.log_message}` : ""}
                    </li>
                  ))}
```

to:

```jsx
                  {run.steps.map((step) => (
                    <li key={step.id}>
                      Step {step.step_index}: {step.status} {step.log_message ? `— ${step.log_message}` : ""}
                      {step.screenshot_path && (
                        <div>
                          <img src={`${BASE_URL}${step.screenshot_path}`} alt="" style={{ maxWidth: 200 }} />
                        </div>
                      )}
                    </li>
                  ))}
```

- [ ] **Step 3: Manually verify in the browser**

Run: `cd backend && python -m uvicorn app.main:app --reload` (in one terminal) and `cd frontend && npm run dev` (in another). Open `http://localhost:5173`, submit a scan against any reachable URL, run it, and confirm screenshots render inline under each step. This is a manual check — no automated test for visual rendering is in scope.

- [ ] **Step 4: Update `docs/data-model.md`**

Change the `run_steps.screenshot_path` row from:

```
| screenshot_path | string, nullable | always `None` today — screenshot capture isn't implemented anywhere in the codebase yet |
```

to:

```
| screenshot_path | string, nullable | URL path (e.g. `/screenshots/{run_id}/{step_index}.png`) served via the FastAPI static mount at `/screenshots`; `None` only if the screenshot capture itself failed (action result is unaffected) |
```

- [ ] **Step 5: Update `docs/api-spec.md`**

In the `POST /scans/{scan_id}/run` section, replace:

```
Screenshot capture was never implemented, so `RunStep.screenshot_path` is always `None` for now — the column exists for when that lands.
```

with:

```
Each executed step's `screenshot_path` is a `/screenshots/{run_id}/{step_index}.png` URL, served by a `StaticFiles` mount over `backend/data/screenshots/` (see `app.main`); it's `None` only if the screenshot capture call itself failed, independent of the step's pass/fail outcome.
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.jsx frontend/src/api.js docs/data-model.md docs/api-spec.md
git commit -m "feat: display scenario screenshots in the frontend, update docs"
```
