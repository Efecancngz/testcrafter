# testcrafter

> Ortak standart: `C:\Users\efeca\OneDrive\Belgeler\obsidian\claudesidian\06_Metadata\Reference\Yazılım Projesi Standartları.md` (commit/branch/README/test/secrets/lisans + kodlama öncesi planlama). Bu dosyadaki kurallar zaten o standarda uygun, çakışırsa buradaki daha spesifik olan geçerli.

AI-powered test scenario generator + Playwright runner. User submits a URL + short description, an AI provider generates test scenarios, Playwright executes them, results show on a React dashboard.

Full design rationale: `docs/architecture.md`. Read it before making architectural changes.

Current work-in-progress status / AI handoff: `HANDOFF.md` — read it first when resuming work.

## Purpose

Portfolio project spanning backend/full-stack, AI-integration, and QA-automation — built to be demoable in job interviews for all three. Long-running, continuously developed (not a fixed-scope sprint).

## Stack

- **Backend:** FastAPI, SQLAlchemy, SQLite (schema kept PostgreSQL-migration-ready)
- **Frontend:** React (Vite)
- **Test automation:** Playwright (crawling, scenario execution, and the project's own E2E tests)
- **AI layer:** provider-agnostic (`AIProvider` interface), adapters for Claude, Gemini, DeepSeek, Qwen
- **Infra:** Docker Compose (local only for now, no hosting)

## Structure

```
backend/
├── api/       # REST endpoints (projects, scans, runs)
├── ai/        # AIProvider interface + adapters
├── crawler/   # Page structure extraction via Playwright
├── runner/    # Executes AI-generated scenarios via Playwright
└── db/        # SQLAlchemy models: User, Project, Scan, Scenario, Run, RunStep
frontend/      # React dashboard
docs/          # architecture.md, api-spec.md, ai-provider-interface.md, data-model.md
```

## Conventions

- Comments only for non-obvious WHY (hidden constraints, workarounds), never WHAT — identifiers should explain themselves.
- No speculative abstractions or unused flexibility. Adding a new AI provider = one new adapter file implementing `AIProvider`, nothing else.
- User-facing errors are human-readable; stack traces and raw provider responses stay in backend logs only.
- AI provider JSON output is always validated against a Pydantic schema — a schema mismatch is an error, never silently accepted.
- Data model is written multi-tenant-ready (real FKs, no shortcuts) even though MVP only seeds one demo user.

## Testing

- `pytest` for backend unit + integration tests (AI adapters and crawler use mocked responses/pages; integration tests hit a test DB, never real AI calls)
- Playwright + pytest for E2E — tests the dashboard's own flow (create project → start scan → view results)
- CI (GitHub Actions): lint + unit + integration on every PR; E2E runs separately (nightly/manual) since it's slower
- Not chasing 100% coverage — solid tests on critical paths (AI adapter contract, API endpoints, runner logic), E2E for "core flow works"

## Documentation

- `README.md` (English, primary) / `README.tr.md` (Turkish) — keep both in sync on any user-facing change
- `CONTRIBUTING.md` — setup, branch/PR flow, test running
- `docs/api-spec.md` — the "why" behind endpoint/schema design; FastAPI's `/docs` already covers the "what"
- `docs/data-model.md` — schema + ER diagram, keep in sync with actual SQLAlchemy models

## Git workflow

- Never add a "Co-Authored-By: Claude" (or any AI attribution) trailer to commits — hard rule for this repo.
- Create new commits rather than amending, unless explicitly told otherwise.
