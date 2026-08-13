# testcrafter — Design Spec

**Date:** 2026-08-11
**Status:** Approved
**Code location:** `C:\dev\testcrafter` (this spec is the source of truth here; a lightweight pointer note lives in the vault under `01_Projects/testcrafter/`)

## 1. Overview

**What it is:** A web app where a user submits a target URL plus a short description/user story. The system analyzes the page, uses an AI provider to generate test scenarios (login flows, form validation, broken links, accessibility checks, etc.), runs those scenarios automatically with Playwright, and shows pass/fail results with screenshots on a dashboard.

**Why this project:** A single project that demonstrates backend API design (FastAPI), AI integration (provider-agnostic abstraction layer), and QA/test automation (Playwright) together — relevant to backend/full-stack, AI-integration, and QA-automation job applications simultaneously.

**Motivation:** Portfolio piece for job applications. Long-running/continuously developed, not a one-off sprint.

**MVP scope:** Runs locally via Docker Compose, no hosting for now. Data model and auth are multi-tenant-ready by design (real per-user accounts via JWT auth, see [Auth](#auth) below), so it can grow into a real SaaS later without a schema rewrite.

## 2. Architecture

```
testcrafter/
├── backend/          # FastAPI
│   ├── api/          # REST endpoints (projects, scans, runs)
│   ├── ai/           # Provider-agnostic AI layer (Claude/Gemini/DeepSeek/Qwen adapters)
│   ├── crawler/       # Analyzes target URL, extracts page structure via Playwright
│   ├── runner/        # Executes generated scenarios with Playwright
│   └── db/            # SQLite + SQLAlchemy models (User, Project, Scan, Scenario, Run, RunStep)
├── frontend/          # React (Vite) dashboard
└── docker-compose.yml # backend + frontend
```

**Flow:**
1. User enters a URL + short description on the dashboard → `POST /projects/{id}/scans`
2. Backend opens the page headless via Playwright, extracts DOM structure (forms, links, buttons)
3. Page structure + description sent to the selected AI provider → returns structured JSON test scenarios (step-by-step actions + expected results)
4. Scenarios saved to DB; once approved (or automatically), the runner executes them with Playwright
5. Screenshots taken at each step; pass/fail + error message recorded
6. Dashboard shows results per scenario (pass/fail, screenshots, AI-generated scenario text)

**AI provider abstraction:** `AIProvider` interface — `generate_scenarios(page_structure, description) -> list[Scenario]`. Each provider (Claude, Gemini, DeepSeek, Qwen) is a separate adapter implementing this interface. Active provider selected via `.env`. Adding a new provider means adding a new adapter file, nothing else changes.

## Auth

JWT-based, stateless: `POST /auth/register` and `POST /auth/login` return a signed access token; every subsequent request authenticates via `Authorization: Bearer <token>`, verified per-request in `app/auth.get_current_user` (`Depends`), with no server-side session store or token registry. Passwords are hashed with `bcrypt` (`app/auth.hash_password` / `verify_password`) — the plaintext password never persists, and `password_hash` is never returned by any endpoint. Tokens are signed with `SECRET_KEY` (required env var; the app refuses to start without it) and expire after 24 hours.

JWT was chosen over server-side sessions because it matches the existing architecture: the backend is a stateless FastAPI API consumed by an SPA, so there's no natural place to keep session state without adding a session store (Redis, DB-backed sessions) purely for auth. A signed, self-contained token needs no extra infrastructure and keeps every request independently verifiable — consistent with the project's "no hosting yet but SaaS-ready" posture (see MVP scope above): it costs nothing extra locally and scales cleanly to multiple backend instances later without sticky sessions or a shared session store.

## 3. Documentation Structure

```
testcrafter/
├── README.md                    # English (GitHub default — international visibility)
├── README.tr.md                 # Turkish translation, linked from README.md
├── CONTRIBUTING.md               # Setup, branch/PR flow, code style, running tests
├── CLAUDE.md                    # Project overview for AI assistant: purpose, stack, conventions, commands
├── LICENSE                      # MIT (standard for portfolio projects)
├── docs/
│   ├── architecture.md          # Durable version of this design
│   ├── api-spec.md              # REST endpoints: method, path, request/response schema, examples, "why" behind design choices
│   ├── ai-provider-interface.md # AIProvider contract + guide for adding new adapters
│   └── data-model.md            # DB schema + ER diagram
```

FastAPI auto-generates OpenAPI/Swagger (`/docs`) for the "what"; `docs/api-spec.md` captures the "why" behind endpoint/schema decisions. In-code docstrings only for non-obvious logic (WHY, not WHAT).

## 4. Testing and Error Handling

| Layer | Tool | Coverage |
|---|---|---|
| Backend unit | pytest | AI provider adapters (mocked responses), crawler parsing logic, DB models |
| Backend integration | pytest + httpx | API endpoints (test DB, AI calls mocked) |
| E2E | Playwright + pytest | The app's own dashboard flow (create project → start scan → view results) — using Playwright at a meta level to test the tool itself |
| CI | GitHub Actions | Lint + unit + integration on every PR; E2E runs separately (nightly or manual trigger) since it's slower |

**Error handling:**
- **AI provider errors** (rate limit, timeout, invalid JSON): retry with exponential backoff (max 3 attempts); on failure, `Run` status set to `failed` with reason shown to user. AI JSON output validated against a Pydantic schema — schema mismatch is treated as an error, never silently swallowed.
- **Crawler errors** (site unreachable, timeout, bot protection): scan moves to `failed`, user sees a human-readable message, not a stack trace.
- **Test runner failures** (scenario step can't find an element, etc.): this is a legitimate result — scenario marked `fail`, error captured with a screenshot. Not an application bug; it's the product doing its job.
- **General principle:** user-facing errors are human-readable; technical detail (stack traces, raw provider responses) stays in backend logs only.

**Coverage target:** Not 100% — solid coverage on critical paths (AI adapter contract, API endpoints, runner logic); E2E covers "core flow works" for the UI.

## 5. Data Model

```
User
├── id (PK)
├── email
├── created_at
(real per-user accounts via `POST /auth/register`; table was always multi-tenant-ready and is now exercised as such — see Auth above)

Project
├── id (PK)
├── user_id (FK → User)
├── name
├── base_url
├── created_at

Scan
├── id (PK)
├── project_id (FK → Project)
├── target_url
├── description
├── page_structure_json
├── ai_provider           # claude | gemini | deepseek | qwen
├── status                # pending | analyzing | ready | failed
├── created_at

Scenario
├── id (PK)
├── scan_id (FK → Scan)
├── title
├── steps_json            # AI-generated step-by-step actions (action, selector, value, expected)
├── created_at

Run
├── id (PK)
├── scenario_id (FK → Scenario)
├── status                # pending | running | passed | failed | error
├── error_message
├── started_at / finished_at

RunStep
├── id (PK)
├── run_id (FK → Run)
├── step_index
├── status                # passed | failed
├── screenshot_path
├── log_message
```

**Relationships:** `User 1—N Project 1—N Scan 1—N Scenario 1—N Run 1—N RunStep`. Multiple scenarios per scan, multiple runs per scenario — enables history/trend tracking (e.g. "did this scenario pass in the last 5 runs") for free later.

**Why SQLite despite this normalization:** SQLite is sufficient for MVP performance; schema is designed to map 1:1 to PostgreSQL (foreign keys, native types outside JSON columns) so a future SaaS migration is a connection-string change, not a schema rewrite.

## Decisions Log

- Test tooling: Playwright over Selenium (more current in industry, better auto-wait/multi-browser API)
- Product shape: local + Docker Compose for MVP, no hosting; architecture kept multi-tenant-ready for a possible future SaaS pivot
- AI layer: abstracted from day one (not single-provider), to support Claude/Gemini/DeepSeek/Qwen interchangeably
- Database: SQLite for MVP, schema designed for painless PostgreSQL migration
- Docs: bilingual README (English primary, Turkish secondary), plus CONTRIBUTING.md and MIT LICENSE
