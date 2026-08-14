# Live Scan Progress — Design

**Date:** 2026-08-14
**Status:** Approved

## Problem

`POST /scans/{scan_id}/run` (`backend/app/api/scans.py`) runs every scenario
synchronously inside the request and returns all results at once. For a
handful of scenarios against a real site this takes anywhere from 30 seconds
to several minutes (observed: 47–92s against github.com). During that time
the frontend (`frontend/src/pages/ScanDetailPage.jsx`) shows only a disabled
button reading "Running..." — no indication of which scenario or step is
executing, whether anything is happening at all, or how much longer it will
take.

## Goal

Show real, step-by-step progress as scenarios actually run: which scenario
is executing, which step within it, and the outcome of each step, updating
live while the run is in progress. Progress must survive navigating away and
back — the run continues server-side regardless of whether anyone is
watching, and returning to the page (or reloading it) resumes watching
wherever the run currently is.

## Visual direction

An accordion list, one entry per scenario:

- Collapsed row: status icon (✓ passed / ● running / ○ pending or failed-skip),
  scenario title, `completed/total` step count, and duration once finished or
  "running…"/"queued" while not.
- The currently-running scenario is expanded by default; if none is running
  yet (all still `pending`, immediately after triggering a run), the first
  scenario is expanded instead, since it's next up. Others stay collapsed.
  The user can expand/collapse any row manually, and manual expand/collapse
  is not overridden by later polling updates.
- Inside an expanded scenario, each step is a row: status icon, the actual
  action name (`goto`/`fill`/`click`/`expect_text`/`expect_url`/
  `expect_visible`) plus a short selector/value hint — replacing today's raw
  `Step 0: passed`.
- A step with a captured screenshot expands/collapses it inline on click.
  Screenshots are not fetched until clicked (a 4-scenario run today captures
  24 of them — no reason to pull all of them eagerly).
- Steps after a failed step in the same scenario stay in their `○`
  (never-run) state — the runner already stops a scenario at its first
  failure; no new "skipped" visual state is introduced.

## Backend

### Execution model

`run_scenario` in `backend/app/runner.py` gains an optional `on_step`
callback, invoked once per step immediately after that step finishes:

```python
def run_scenario(
    scenario: GeneratedScenario,
    base_url: str,
    screenshot_dir: Path,
    on_step: Callable[[int, StepResult], None] | None = None,
) -> list[StepResult]:
```

The function's return value and existing behavior are unchanged — the
callback is purely an additional notification point. Existing callers and
existing tests that don't pass `on_step` keep working with no changes.

`POST /scans/{scan_id}/run` changes from "run everything, then respond" to
"create pending runs, hand off execution, respond immediately":

1. Look up the scan (existing 404-not-403 ownership check, unchanged).
2. If any `Run` for this scan's scenarios is already `pending` or `running`,
   return `409 Conflict` — one execution in flight per scan at a time. (Two
   browser tabs triggering overlapping runs against the same scan is the
   scenario this guards; it is not a global concurrency limit.)
3. For each scenario, create a `Run` row with `status="pending"` and commit
   immediately, so the full set of runs exists and is queryable the instant
   this request returns.
4. Hand the actual execution off to a FastAPI `BackgroundTasks` job (see
   below) and return `202 Accepted` with the list of just-created `Run`
   rows (schema: the existing `RunOut`, `steps: []` for all of them since
   nothing has executed yet).

The background job iterates scenarios in order (same order as today), and
for each one:
- Sets `Run.status = "running"`, commits.
- Calls `run_scenario(..., on_step=...)`. The callback writes one `RunStep`
  row and commits **immediately** after each step — short, independent
  transactions, not one long transaction held open for the scenario's full
  duration. (This project has hit exactly the opposite bug before — a
  transaction held open across a slow external call — during the
  screenshot-capture feature; this design deliberately avoids repeating it.)
- Sets `Run.status` to `passed`/`failed` and `finished_at`, commits.

**Session lifetime:** the request-scoped `Session` from `Depends(get_session)`
closes when the request returns, before the background job's first write.
The background job opens its own session directly from `SessionLocal`
(`backend/app/db.py`) and closes it when the job finishes — it does not
reuse the request's session.

**Concurrency:** `BackgroundTasks` runs a sync function in a thread pool, so
a request returns immediately while execution proceeds on a worker thread.
Because each step is its own short commit rather than one long transaction,
this is safe against SQLite the same way the rest of this codebase already
is.

### New endpoint

`GET /scans/{scan_id}/runs` — returns the current state of every run
belonging to the scan (same ownership check, ordered by `Run.id`), including
whatever `RunStep` rows exist so far. Response schema is `list[RunOut]`,
identical to what `POST /run` used to return in full — this endpoint is what
the frontend polls, and what a page reload or navigation-back reads to
resume watching.

### Status vocabulary

`Run.status` gains `"running"` alongside the existing `pending`/`passed`/
`failed`. `RunStep.status` is unchanged (`passed`/`failed`, written once per
step, never in a pending state — a step row is only created once it has
finished).

## Frontend

`ScanDetailPage.jsx`:

- "Run scenarios" calls `POST /scans/{id}/run`. On `202`, the returned
  (all-`pending`) runs go straight into state — the accordion renders
  immediately, every scenario showing `0/N queued`.
- On `409` (already running), the click is treated as "start watching" —
  no error shown, the page begins polling as if it had started the run
  itself. This is the natural response to opening a second tab on an
  in-flight scan.
- Whenever any run in state is `pending` or `running`, an interval polls
  `GET /scans/{id}/runs` every 1.5s and replaces run state with the
  response. Polling stops once every run is `passed` or `failed`.
- On mount / navigating to a scan (`getScan` + this new call, both fired
  from the existing `useEffect`), if any returned run is `pending` or
  `running`, polling starts automatically — this is the entire mechanism
  for "resume watching a run in progress," no separate resume path needed.
- New `RunAccordion` component (or equivalent breakdown) replaces the current
  flat `<ul>` of runs: collapsible per-scenario rows as described in Visual
  direction, with the currently-active scenario open by default. Step rows
  show the action name and a short selector/value hint instead of the
  current bare `Step {index}: {status}`.
- Screenshot fetching stays lazy: `Screenshot` (existing component) only
  mounts for a step once its row is expanded by a click.

## Error handling

- A step's own failure is not a request error — same as today, it's data
  (`RunStep.status = "failed"`, `log_message` populated) and the scenario's
  remaining steps stay unexecuted (`○`).
- A polling request that fails (network blip, backend restart) is retried on
  the next tick; no error surfaces to the user for a single missed poll,
  consistent with this codebase's existing "don't spam transient errors"
  pattern in `ProjectDetailPage`/`ProjectListPage`.
- `409` from `POST /run` is not an error state in the UI, per above — it's
  the trigger to start watching an already-running scan.

## Testing

**Backend:**
- `run_scenario` calls the `on_step` callback exactly once per step, in
  order, with the right `(index, StepResult)` — and that omitting the
  callback (existing call sites) still works unchanged.
- `POST /scans/{id}/run` returns `202` with `Run` rows all `status="pending"`
  and empty `steps`, and that those rows exist in the DB immediately
  (queryable before the background job would plausibly have finished).
- `POST /scans/{id}/run` returns `409` when a run for the scan is already
  `pending`/`running`.
- `GET /scans/{id}/runs` enforces the existing ownership pattern (404, not
  403, for a scan not owned by the caller) and returns partial progress
  correctly (some steps written, run still `running`).
- The background job itself: since it runs in a thread pool outside the
  request/response cycle, its test drives it directly (call the job function
  the endpoint schedules, not through an HTTP round-trip) with a mocked
  `run_scenario`, asserting the `Run`/`RunStep` state transitions and that
  each step commits independently (not all-or-nothing).

**Frontend:** this project has no JS test framework (established, accepted
convention) — verified manually against a real long-running scan (e.g.
github.com), watching the accordion update live, confirming a page
reload mid-run resumes polling and shows the run already in progress.

## Out of scope

- **SSE/WebSocket push.** The `on_step` callback is the only integration
  point a future push-based transport would need — it can feed an event
  stream the same way it feeds `RunStep` writes, without changing
  `runner.py`'s or the endpoint's public shape. Not built now; the design
  leaves it a pure addition, not a rework.
- **Cancelling an in-progress run.** No cancel endpoint or UI. A `409` on
  re-trigger is the only interaction with an in-flight run.
- **Global concurrency limits** (e.g. capping total simultaneous background
  runs across all users/scans). The `409` guard is per-scan only.
- **A dedicated "skipped" step status.** Steps after a failure stay `○`
  (never-run), matching current runner behavior — no new status is
  introduced for this design.
