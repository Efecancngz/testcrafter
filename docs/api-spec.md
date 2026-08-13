# API Spec

Human-readable design rationale for the REST API. FastAPI's auto-generated OpenAPI docs (`/docs` when the backend is running) are the source of truth for exact request/response shapes — this file explains *why* the endpoints look the way they do.

## `POST /auth/register` / `POST /auth/login`

`POST /auth/register` creates a new user (hashing the password with `bcrypt`) and immediately returns an access token, logging the caller in — there's no email verification step; that's out of scope per this feature's spec, not an oversight. `POST /auth/login` verifies the submitted password against the stored hash and returns the same token shape.

Both failure cases — wrong password and a nonexistent email — return the same generic `401` error rather than distinguishing them, so a caller can't use the login endpoint to enumerate which emails are registered.

Auth is stateless JWT: there's no server-side session or revocation list, so an issued token remains valid until it expires (24 hours) even if, say, the user's password is changed afterward. This is a known, accepted MVP limitation — closing it would mean adding a token blocklist or session store, which is exactly the infrastructure JWT was chosen to avoid (see `docs/architecture.md#auth`).

## `POST /projects`

Creates a project owned by the authenticated caller (`Depends(get_current_user)`; see `backend/app/auth.py`). The `user_id` FK — always present in the schema — is now exercised for real instead of pointing at a seeded demo user.

## `GET /projects`

Scoped to the caller's own projects. Previously this returned every project in the database regardless of owner; that was a real gap (any client could enumerate all users' projects), now closed by the same `get_current_user` dependency. Unpaginated for now — fine at MVP scale, would need pagination before this became a real multi-tenant product.

## `POST /projects/{project_id}/scans`

The core endpoint. Requires auth, and 404s (not 403) if `project_id` exists but isn't owned by the caller — the API deliberately doesn't reveal that a project id exists to a caller who doesn't own it. Synchronously: crawls the target URL, calls the configured AI provider, and persists generated scenarios — all in one request/response cycle. This is deliberately synchronous for the MVP (simpler to reason about and test) even though it means the caller waits for both a page crawl and an AI call. A background job queue is the natural next step once this gets slow in practice, but isn't justified yet.

If the AI response fails schema validation, the scan is saved with `status = "failed"` rather than the request erroring out — the crawl and scan record are still useful even if scenario generation failed.

If the crawl detects a bot-verification challenge page (Cloudflare, reCAPTCHA, hCaptcha) instead of real content, the scan is saved with `status = "blocked"` and `blocked_reason` set to the detected provider name — scenario generation is never attempted against challenge-page content.

## `GET /scans/{scan_id}`

Returns a scan and its generated scenarios. Requires auth, and 404s if the scan doesn't exist *or* belongs to a different user's project — same not-revealing-existence rationale as above. Enforced by API tests (`tests/test_api_scans.py`), not left as an assumption.

## `POST /scans/{scan_id}/run`

Executes every scenario belonging to the scan with Playwright (`app/runner.run_scenario`) and persists the results. Requires auth, 404s on a scan not owned by the caller (same pattern as `GET /scans/{scan_id}`). Synchronous for the same reason scan creation is: simpler to reason about and test at MVP scale, revisit with a job queue once real usage makes that too slow.

For each scenario, a `Run` row is written (`status = "passed"` only if every step passed, otherwise `"failed"`) along with one `RunStep` row per executed step (status + log message). Returns the list of created runs with their steps.

## Screenshots: `GET /runs/{run_id}/screenshots/{step_index}`

Each executed step's `screenshot_path` now points at this endpoint rather than a static file URL. It requires auth and 404s unless the caller owns the run (via the run's scenario → scan → project → user chain), streaming the image bytes back only after that check passes.

This replaces an earlier `StaticFiles` mount over `backend/data/screenshots/` that served every screenshot on disk to anyone who guessed or was handed a URL, with no ownership check at all. That gap was flagged in the screenshot-capture feature's final review and is closed here now that auth exists to check against. Because `<img src>` can't attach an `Authorization` header, the frontend fetches this endpoint as an authenticated blob and assigns the resulting object URL to the `<img>` (see `frontend/src/api.js#fetchScreenshotUrl`) instead of pointing `src` at the API directly.
