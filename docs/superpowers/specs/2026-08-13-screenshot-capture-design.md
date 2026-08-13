# Screenshot Capture — Design Spec

**Date:** 2026-08-13
**Status:** Approved

## 1. Overview

Capture a Playwright screenshot after every scenario step (pass or fail), persist it to local disk, record its path on `RunStep.screenshot_path`, serve it via a static file mount, and display it in the frontend results view. Second of three planned features (Gemini adapter [done, merged] → screenshot capture → auth system), each with its own spec/plan/implementation cycle.

## 2. Components

### `backend/app/runner.py`

- `StepResult` gains a `screenshot_path: str | None` field (default `None`).
- `_run_step(page, step, base_url, screenshot_dir: Path, step_index: int)` — after executing the step's action (regardless of pass/fail branch), calls `page.screenshot(path=screenshot_dir / f"{step_index}.png")`. If the screenshot call itself raises (e.g. page already closed), the exception is caught, logged via the module logger, and `screenshot_path` stays `None` — this must not change the step's `status`/`log_message` outcome, which already reflects the action's own success/failure.
- `run_scenario(scenario, base_url, screenshot_dir: Path) -> list[StepResult]` gains the `screenshot_dir` parameter; it's created (`mkdir(parents=True, exist_ok=True)`) before the Playwright session starts, and each step's screenshot path is set on its `StepResult` as `screenshot_dir`-relative-to-`SCREENSHOTS_DIR`... — see the "Path stored in DB" note below for the exact string format returned.

### `backend/app/api/scans.py`

- New module-level constant: `SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "screenshots"` (i.e. `backend/data/screenshots`), or read from an env var with that as default — implementation plan decides based on what's simplest to override in tests.
- `run_scan`'s per-scenario loop currently calls `run_scenario(...)` *before* creating the `Run` row (so `run.id` doesn't exist yet at capture time). Reorder: create the `Run` row and `session.flush()` first (to get `run.id`), *then* call `run_scenario(generated, base_url="", screenshot_dir=SCREENSHOTS_DIR / str(run.id))`. This changes only the order of operations, not what gets persisted or when the response is returned.
- Each `RunStep` is created with `screenshot_path=result.screenshot_path` (currently omitted/always `None`).
- **Path stored in DB:** `/screenshots/{run_id}/{step_index}.png` (the URL path the frontend will fetch from, not a filesystem path) — this is what `RunStep.screenshot_path` holds, matching the `docs/data-model.md` column already declared for this purpose.

### `backend/app/main.py`

- Mount static files: `app.mount("/screenshots", StaticFiles(directory=SCREENSHOTS_DIR), name="screenshots")`, importing `SCREENSHOTS_DIR` from `app.api.scans` (or a shared config module if the implementer judges that cleaner — no new abstraction is required by this spec, keep it to the minimum).

### Storage & persistence

- Files live at `backend/data/screenshots/{run_id}/{step_index}.png`. Added to `.gitignore` (generated data, not source).
- `docker-compose.yml` already mounts `./backend:/app` as a volume for the `backend` service — no additional volume needed; screenshots written inside the container appear on the host automatically.

### `backend/app/api/scans.py` — `RunStepOut` schema

- Add `screenshot_path: str | None = None` to `RunStepOut` (currently missing — the API never returns it even though the DB column exists).

### Frontend (`frontend/src/App.jsx`)

- In the per-step `<li>` in the results view, if `step.screenshot_path` is present, render `<img src={`${BASE_URL}${step.screenshot_path}`} alt="" style={{maxWidth: 200}} />` below the status/log line. `BASE_URL` needs to be exported from `api.js` (currently a private module constant) or duplicated as a small constant in `App.jsx` — implementer's call, keep it minimal.
- No lightbox/zoom/gallery — out of scope for MVP (YAGNI).

## 3. Testing

- `backend/tests/test_runner.py`: extend existing tests (or add new ones) to assert that after `run_scenario(scenario, base_url, screenshot_dir=<tmp_path>)`, each returned `StepResult.screenshot_path` is set and the corresponding file actually exists on disk at `tmp_path / f"{index}.png"`. Use pytest's built-in `tmp_path` fixture — no real `SCREENSHOTS_DIR` writes during tests.
- `backend/tests/test_api_scans.py`: extend `test_run_scan_executes_scenarios_and_persists_results` (or add a new test) to assert the response's `steps[].screenshot_path` is a non-null string matching the `/screenshots/{run_id}/{index}.png` pattern. Since this test hits the real `run_scan` endpoint, the test must override `SCREENSHOTS_DIR` to a temp directory — via `monkeypatch.setattr("app.api.scans.SCREENSHOTS_DIR", tmp_path)` or equivalent — so it doesn't write into the repo's working directory during CI.
- Existing tests that construct `StepResult` directly (if any) may need the new field added to their call sites — check `test_runner.py` for direct `StepResult(...)` construction.

## 4. Documentation

- `docs/data-model.md`: update the `run_steps.screenshot_path` row — currently says "always `None` today — screenshot capture isn't implemented anywhere in the codebase yet". Update to reflect that it's now populated, with the `/screenshots/{run_id}/{step_index}.png` format.
- `docs/api-spec.md`: update the `POST /scans/{scan_id}/run` section — currently says "Screenshot capture was never implemented, so `RunStep.screenshot_path` is always `None` for now — the column exists for when that lands." Update to describe the new behavior and the static-serving path.
- `README.md` / `README.tr.md`: no changes expected (no new setup step — screenshots work out of the box, no new env var or dependency), but check for any wording that specifically calls out "no screenshots yet" and correct it if found (the git history shows README once had a screenshots claim removed — this feature makes such a claim true again, but only re-add wording if the current README explicitly says screenshots are absent, don't add promotional copy that wasn't asked for).

## 5. Out of Scope

- Screenshot cleanup/retention policy (disk usage growth over time) — not addressed, matches MVP's "not hosting, local only" scope.
- Cloud/object storage — explicitly deferred to a future SaaS migration per `docs/architecture.md`'s existing decisions log; this spec only does local disk + static mount, consistent with current `AI_PROVIDER`-style MVP-first choices.
- Screenshot on crawl-phase failures (the crawler, not the runner) — out of scope; this spec only covers the Playwright *runner* (scenario execution), not the crawler.
