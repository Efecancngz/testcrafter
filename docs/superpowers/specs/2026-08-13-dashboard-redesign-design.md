# Dashboard Redesign — Design

**Date:** 2026-08-13
**Status:** Approved

## Problem

The current frontend (`frontend/src/App.jsx`) is a single component implementing
one linear flow: log in → create a project → start one scan → view its
results. There is no routing, no way to see a project's scan history, and
no way to revisit a past scan without re-running it. The backend already
models multiple projects and multiple scans per project (`Project`, `Scan`
FK chain), but the UI only ever shows the most recent scan created in the
current session.

## Goal

Rebuild the frontend as a real multi-page dashboard: a project list, a
project detail view showing that project's scan history, and a scan detail
view showing scenarios/results — restyled with a sparse, technical,
dev-tool aesthetic (reference: Supabase's dashboard) using Tailwind CSS +
shadcn/ui. This requires two small backend additions to expose scan
history, which are in scope as prerequisites.

## Visual direction

- **Feel:** minimal/technical, not decorative — sparse color, generous
  whitespace, dev-tool identity (in the spirit of Linear/Vercel/GitHub).
- **Reference:** Supabase Dashboard — chosen because its
  project → table → row hierarchy structurally mirrors testcrafter's
  project → scan → scenario → run hierarchy.
- **Palette:** neutral gray scale with a dark-green accent, close to
  Supabase's own palette, dark theme by default. Exact token values are an
  implementation-time decision (Tailwind's default `slate`/`emerald`
  scales are a reasonable starting point), not fixed here — the user
  remained deliberately open on precise values.
- **Component approach:** Tailwind CSS + shadcn/ui (Table, Card, Badge,
  Button, Dialog/Form primitives as needed). shadcn/ui components are
  copied into the repo (not an npm dependency in the traditional sense),
  so they can be restyled to match the palette above.

## Backend additions (prerequisite phase)

**`Scan.created_at`** — new `DateTime` column, `default=now_utc` (reuses
the same `now_utc()` helper already used by `User`/`Project`/`Scenario` in
`backend/app/models.py`). Added via Alembic migration, following this
project's established migration workflow (edit model → autogenerate →
review, don't hand-edit).

**`GET /projects/{project_id}`** — returns a single `ProjectOut`
(existing schema, no changes needed), 404 if not found or not owned by the
requesting user (mirrors `_get_owned_scan`'s existing ownership-check
pattern in `scans.py`, applied here to `Project` directly by
`user_id`).

**`GET /projects/{project_id}/scans`** — returns
`list[ScanSummaryOut]`, ordered by `created_at` descending (newest first).
`ScanSummaryOut` is a new, deliberately lighter schema than the existing
`ScanOut` — it omits the `scenarios` list entirely:

```python
class ScanSummaryOut(BaseModel):
    id: int
    target_url: str
    status: str
    blocked_reason: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}
```

This avoids an N+1 query (fetching every scenario for every scan just to
render a list row) — the scan detail page fetches full scenario data
separately via the existing `GET /scans/{scan_id}`, unchanged. 404s
consistent with the ownership pattern used everywhere else in this router
(project not found or not owned → 404, never leak existence).

## Frontend architecture

**Routing:** `react-router-dom` added as a new dependency. Routes:
- `/login` — login/register (existing logic, relocated from inline
  conditional rendering into its own route)
- `/` — `ProjectListPage`
- `/projects/:projectId` — `ProjectDetailPage`
- `/scans/:scanId` — `ScanDetailPage`

An auth guard component wraps the three authenticated routes: no token in
`localStorage` → redirect to `/login`. The existing
`setUnauthorizedHandler` mechanism (flips the UI to the login form on any
401) is preserved and now performs a route navigation instead of a local
state flip.

**Components:**
- `Layout` — persistent left sidebar (nav: project list link, logout) +
  top bar; wraps all three authenticated pages.
- `ProjectListPage` — grid/list of project cards (`GET /projects`); a
  "New project" form (existing `POST /projects`, relocated here).
- `ProjectDetailPage` — project name/URL header; scan history table
  (`GET /projects/{id}/scans`, columns: target URL, status badge, created
  time, link to detail); a "New scan" form (existing
  `POST /projects/{id}/scans`, relocated here) that on success navigates
  to the new scan's detail route.
- `ScanDetailPage` — scenario list, "Run scenarios" button
  (`POST /scans/{id}/run`, existing logic), results with per-step
  screenshots (existing authenticated blob-fetch logic, relocated
  unchanged from the current `Screenshot` component).
- `StatusBadge` — shared component mapping a status string
  (`pending`/`analyzing`/`ready`/`failed`/`blocked`/`passed`) to a
  shadcn/ui `Badge` variant/color; single source of truth for status
  color, replacing the current plain-text status rendering and the
  one-off inline `color: "#b8860b"` blocked-message style.

**API client (`frontend/src/api.js`):** gains
`getProject(id)`, `listProjectScans(id)` alongside the existing
functions; no changes to existing functions' signatures.

## Data flow

1. User logs in (unchanged) → token stored, app navigates to `/`.
2. `ProjectListPage` fetches `GET /projects` on mount.
3. Clicking a project navigates to `/projects/:id`; that page fetches
   `GET /projects/{id}` and `GET /projects/{id}/scans` in parallel.
4. Submitting the "new scan" form calls `POST /projects/{id}/scans`,
   then navigates to `/scans/{newScanId}`.
5. `ScanDetailPage` fetches `GET /scans/{id}` on mount; "Run scenarios"
   calls `POST /scans/{id}/run` and renders the returned runs/steps
   in place (no navigation).
6. Any 401 from any fetch anywhere triggers the existing unauthorized
   handler → redirect to `/login`.

## Error handling

- 401: existing `setUnauthorizedHandler` pattern, now redirects via
  router instead of local state.
- 404 (project/scan not found or not owned): rendered as a simple
  "not found" page state, not a crash — this can happen legitimately
  (stale link, direct URL to another user's resource returning 404 by
  design per the existing ownership-check convention).
- Empty states: `ProjectListPage` with zero projects and
  `ProjectDetailPage` with zero scans both get an explicit
  empty-state message + call-to-action, not a blank list.
- `blocked` status: existing distinct message/treatment carries over,
  now rendered via `StatusBadge` + the existing blocked-reason message
  instead of the current ad hoc inline style.

## Testing

**Backend:** new tests for `GET /projects/{id}` (success, 404 not-owned,
404 not-found) and `GET /projects/{id}/scans` (success with correct
`created_at` ordering, empty list for a project with no scans, 404
not-owned) — following the existing ownership-test patterns already used
throughout `test_api_scans.py`/`test_api_projects.py`. Also a
`test_alembic.py`-covered schema-drift check for the new
`Scan.created_at` column (automatic, no new test code needed — same
mechanism as the `blocked_reason` column).

**Frontend:** this project has no JS test framework (confirmed
project-wide convention, not something this feature introduces) — manual
per-page verification remains the approach, as with the prior
bot-challenge-detection frontend change.

## Out of scope

- Editing/deleting projects or scans (no such endpoints exist today;
  not requested).
- Any change to the login/register UI's own visual design beyond moving
  it into its own route — restyling it with the new palette is included,
  but no new fields or flows.
- Pagination for project/scan lists (not needed at current expected
  scale; can be added later if it becomes a problem).
- Real-time updates (e.g. auto-refreshing scan status via polling or
  websockets) — scan/run results are fetched on page load and after
  explicit user actions only, matching current behavior.
