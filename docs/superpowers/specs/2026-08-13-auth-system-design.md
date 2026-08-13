# Auth System — Design Spec

**Date:** 2026-08-13
**Status:** Approved

## 1. Overview

Replace the single hardcoded `_demo_user` with real email+password authentication: JWT-based, stateless. Every existing endpoint that currently attributes work to `_demo_user` is scoped to the authenticated user instead, with ownership checks along the FK chain (`Scan → Project → User`, `Run → Scenario → Scan → Project → User`). Also closes a real gap the screenshot-capture feature's final review flagged: screenshots are currently served with no auth and guessable sequential IDs — this spec replaces the static mount with an authorizing proxy endpoint. Third and last of three planned features (Gemini adapter → screenshot capture → auth system), all sharing one spec/plan/implementation cycle pattern.

## 2. Components

### Schema change

- `User` gains `password_hash: Mapped[str] = mapped_column(String)`.
- **No migration tooling exists in this project** (schema is created via `Base.metadata.create_all(engine)` at app startup, which does not add columns to an already-existing table). This spec does not introduce Alembic (YAGNI — out of scope, a bigger decision the user explicitly deferred). Instead: `CONTRIBUTING.md` gets a note that after this change lands, developers must delete their local `testcrafter.db` (or the Docker volume's copy) so it's recreated with the new column. No production data exists to migrate (local-only MVP).

### `backend/app/auth.py` (new module)

- `hash_password(password: str) -> str` / `verify_password(password: str, password_hash: str) -> bool` — using `bcrypt` (added as a new dependency).
- `create_access_token(user_id: int) -> str` — JWT signed with `SECRET_KEY` (new env var, no default — missing key is a startup-time config error, not silently insecure), expiry ~24h, using `pyjwt` (new dependency).
- `get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> User` — FastAPI dependency. Decodes/validates the JWT (`oauth2_scheme` is `fastapi.security.OAuth2PasswordBearer(tokenUrl="/auth/login")`), loads the `User` row by the token's `user_id` claim. Raises `HTTPException(401)` with a human-readable message on any failure (missing/malformed/expired token, user no longer exists) — never a raw stack trace to the client, matching the project's existing error-handling convention.

### `backend/app/api/auth.py` (new router)

- `POST /auth/register` — body `{email, password}`. If email already registered, `400` with a human-readable message. Otherwise hashes the password, creates the `User`, returns `{access_token, token_type: "bearer"}` (log the user in immediately, matching typical UX — no separate email-verification step, out of scope per the approved design).
- `POST /auth/login` — body `{email, password}` (or FastAPI's standard `OAuth2PasswordRequestForm` for compatibility with `oauth2_scheme`'s `tokenUrl` convention — implementer's call, whichever is more idiomatic with the chosen `oauth2_scheme` setup). Verifies credentials; `401` with a human-readable message on mismatch (same message for "no such user" and "wrong password" — don't leak which one, standard practice). Returns the same `{access_token, token_type}` shape as register.

### Existing endpoints — scoped to the authenticated user

- `backend/app/api/projects.py`: remove `_demo_user`. `create_project` and `list_projects` take `user: User = Depends(get_current_user)`. `create_project` uses `user.id` instead of `_demo_user(session).id`. `list_projects` filters `.filter_by(user_id=user.id)` — today it returns every project in the DB regardless of owner; this is a real gap auth closes, not a new restriction being invented.
- `backend/app/api/scans.py`: `create_scan`, `get_scan`, `run_scan` all take `user: User = Depends(get_current_user)`.
  - `create_scan(project_id, ...)`: verify the `Project` with that id belongs to `user` (404 if not found or not owned — same 404-not-403 pattern already used for "scan not found", so ownership doesn't leak existence).
  - `get_scan(scan_id, ...)` / `run_scan(scan_id, ...)`: verify the `Scan` belongs (via `Scan.project_id → Project.user_id`) to `user`, same 404-on-mismatch pattern.

### Screenshot proxy (replaces the static mount)

- Remove the `/screenshots` `StaticFiles` mount from `backend/app/main.py` entirely.
- New endpoint: `GET /runs/{run_id}/screenshots/{step_index}` in `backend/app/api/scans.py` (or a new small module if the implementer judges the file is getting crowded — no new abstraction required beyond that judgment call). Takes `user: User = Depends(get_current_user)`. Walks `Run → Scenario → Scan → Project → User` to verify `user_id` matches; `404` if the run doesn't exist or isn't owned (same non-leaking pattern). Looks up the matching `RunStep` by `run_id` + `step_index`, reads `screenshot_path` (the filesystem path is now derivable from `SCREENSHOTS_DIR / str(run_id) / f"{step_index}.png"` directly, since the DB no longer needs to store a public URL — see path-format note below), returns it via FastAPI's `FileResponse`. `404` if the file doesn't exist on disk.
- **Path format stored in `RunStep.screenshot_path` changes**: from the old public URL `/screenshots/{run_id}/{step_index}.png` to the new authorizing endpoint's path `/runs/{run_id}/screenshots/{step_index}` (no `.png` — the extension isn't part of the route, `FileResponse` sets the correct `Content-Type` from the actual file).
- Frontend fetches this URL with the `Authorization: Bearer` header attached (same as any other API call) instead of a bare `<img src>` — `<img>` tags can't send custom headers, so the frontend must fetch the image as a blob and construct an object URL, or (simpler, and preferred here) proxy it through a `fetch` call and set `<img src>` to a `URL.createObjectURL(blob)`. This is a real, necessary complexity increase from the previous plain static-mount approach — flagged explicitly since it's the one part of this spec with no precedent in the codebase yet.

### Frontend

- A minimal login/register UI: reusing `App.jsx`'s existing single-page structure (no router library added — YAGNI, consistent with the current app's simplicity), gated on whether a JWT is present. Two form modes (login/register) toggled by a link/button, not two separate pages.
- JWT stored in `localStorage`. `api.js`'s `handleResponse`/fetch helpers gain an `Authorization: Bearer <token>` header on every call except `/auth/register` and `/auth/login`. A `401` response anywhere clears the stored token and returns the user to the login form (session expired / invalid handling — human-readable, not a raw error dump).
- Screenshot rendering (added in the previous branch) changes from a plain `<img src>` to a blob-fetch-then-`createObjectURL` pattern, per the proxy note above.

### Config

- `.env.example`: add `SECRET_KEY=` (no default value — must be set; document in `README.md`/`README.tr.md` that this needs to be a real random secret, not left blank, for the app to start).
- `backend/pyproject.toml`: add `pyjwt` and `bcrypt`.

## 3. Testing

- `backend/tests/test_auth.py` — register (success, duplicate email), login (success, wrong password, nonexistent email), `get_current_user` (valid token, expired/malformed token, token for a deleted user).
- `backend/tests/test_api_projects.py` / `test_api_scans.py` — existing tests updated to authenticate (a shared test fixture, e.g. an `authenticated_client` building on the existing `client` fixture, that registers a user and attaches the resulting token to requests). Add at least one new test per endpoint proving cross-user isolation (user A cannot see/access user B's project/scan/run — expect 404).
- New test for the screenshot proxy: owner can fetch (200, correct bytes), non-owner gets 404, nonexistent run/step gets 404.

## 4. Documentation

- `docs/architecture.md`: update the flow/data-model sections that currently describe `_demo_user` — add a short "Auth" section covering the JWT approach and why (stateless, matches the FastAPI/SPA architecture, no session store needed).
- `docs/api-spec.md`: add `POST /auth/register` and `POST /auth/login` sections (the "why" — e.g. why the login error message doesn't distinguish "no such user" from "wrong password"). Update the existing `POST /projects`, `GET /projects`, `POST /projects/{id}/scans`, `GET /scans/{id}`, `POST /scans/{id}/run` sections to note they now require auth and are scoped to the caller. Add a section for the new screenshot proxy endpoint, replacing the removed mention of the static mount.
- `docs/data-model.md`: update the `users` table row list to include `password_hash`; update `run_steps.screenshot_path`'s description to reflect the new endpoint-path format (not a public static URL).
- `CONTRIBUTING.md`: add the "delete your local `testcrafter.db` after this change" note (see Schema change above), and a note that `SECRET_KEY` must be set in `.env` for the app to start.
- `README.md` / `README.tr.md`: mention the new required `SECRET_KEY` env var in setup instructions, and that the app now requires registering/logging in (brief, one line — this isn't a tutorial).

## 5. Out of Scope

- Alembic or any other migration tool (explicitly deferred per user decision above).
- Email verification, password reset/forgot-password flow, OAuth/social login (explicitly deferred per user decision above — simple email+password only).
- Refresh tokens / token revocation / logout-invalidation (a 24h-expiry access token with no revocation list is accepted as sufficient for this MVP; noted as a known limitation, not silently glossed over).
- Role-based permissions (admin vs regular user) — every registered user has identical capabilities, scoped only to their own data.
- Rate limiting on `/auth/login` (brute-force protection) — out of scope for this pass, worth a future ticket, not blocking this one.
