# API Spec

Human-readable design rationale for the REST API. FastAPI's auto-generated OpenAPI docs (`/docs` when the backend is running) are the source of truth for exact request/response shapes — this file explains *why* the endpoints look the way they do.

## `POST /projects`

Creates a project under the single MVP demo user (see `_demo_user` in `backend/app/api/projects.py`). No auth yet — every request is attributed to `demo@testcrafter.local`. This is intentional: the `user_id` foreign key is already in place so adding real auth later is a matter of swapping `_demo_user` for a real session lookup, not a schema change.

## `GET /projects`

Lists all projects for the demo user. Unpaginated for now — fine at MVP scale, would need pagination before this became a real multi-tenant product.

## `POST /projects/{project_id}/scans`

The core endpoint. Synchronously: crawls the target URL, calls the configured AI provider, and persists generated scenarios — all in one request/response cycle. This is deliberately synchronous for the MVP (simpler to reason about and test) even though it means the caller waits for both a page crawl and an AI call. A background job queue is the natural next step once this gets slow in practice, but isn't justified yet.

If the AI response fails schema validation, the scan is saved with `status = "failed"` rather than the request erroring out — the crawl and scan record are still useful even if scenario generation failed.

## `GET /scans/{scan_id}`

Returns a scan and its generated scenarios. 404s if the scan doesn't exist — this is enforced by API tests (`tests/test_api_scans.py`), not left as an assumption.
