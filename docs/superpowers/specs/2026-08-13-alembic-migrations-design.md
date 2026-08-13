# Alembic Migrations — Design Spec

**Date:** 2026-08-13
**Status:** Approved

## 1. Overview

Replace `Base.metadata.create_all(engine)` (the sole schema-management mechanism today) with Alembic migrations. Closes a real, repeatedly-hit gap: every schema change so far (the `password_hash` column added for auth) required manually deleting the local `testcrafter.db` file, documented as a stopgap in `CONTRIBUTING.md` with an explicit "no migration tooling yet" caveat. This is the deliberate follow-up to close that gap, per the project's own documented migration policy (vault: `Yazılım Projesi Standartları.md` §20).

## 2. Components

### Alembic project structure

`backend/alembic.ini` + `backend/alembic/env.py` + `backend/alembic/versions/` — created via `alembic init alembic` inside `backend/`, then configured: `env.py`'s `target_metadata` is set to `app.db.Base.metadata` (enables `--autogenerate`), and the database URL is read the same way `app/db.py` reads it today (not hardcoded separately — one source of truth for the connection string).

### Initial migration

Generated via `alembic revision --autogenerate -m "initial schema"` against an empty SQLite database, producing a single migration file that creates all six existing tables (`users`, `projects`, `scans`, `scenarios`, `runs`, `run_steps`) exactly as `app/models.py` currently defines them. This migration is committed as autogenerate produces it and is never hand-edited afterward — consistent with the project's migration policy (§20: "migration dosyaları commit edilir ve sonradan elle düzenlenmez — değişiklik gerekiyorsa yeni migration üretilir").

### `backend/app/main.py`

`Base.metadata.create_all(engine)` is removed entirely. The application no longer creates its own schema — Alembic migrations are the only mechanism that creates or alters tables in a real (non-test) database. If migrations haven't been applied, the app should fail loudly on first query (missing table), not silently work against a stale/absent schema.

### `backend/tests/conftest.py` — unchanged

The `db_session` fixture keeps using `Base.metadata.create_all(engine)` against an in-memory SQLite database. This is a deliberate, documented exception, not an oversight: tests need a fast, fully-isolated schema per test run, and running Alembic migrations for that would add complexity and slowness for no benefit — the test schema's job is to mirror the *models*, and `create_all` does that directly and quickly. `docs/architecture.md`'s new migrations section explicitly calls out this split so it doesn't read as an inconsistency later.

### `backend/Dockerfile`

`CMD` changes from directly launching `uvicorn` to first applying migrations:
```dockerfile
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
```
This keeps `docker compose up --build` a single command with no new manual step — consistent with the project's existing "no manual DB step to remember" quick-start experience, and specifically avoids repeating the class of gap this project has hit twice before (`docker-compose.yml` missing a newly-required piece of setup, caught only by final review on the Gemini adapter and auth-system branches). Here the equivalent risk (forgetting to wire migrations into the container startup) is addressed directly in the design rather than left to be caught later.

### `backend/pyproject.toml`

Add `alembic` to `dependencies`.

### One-time local-database transition

`CONTRIBUTING.md`'s existing note (from the auth-system branch: "delete your local `testcrafter.db`, no migration tooling yet") is replaced — not stacked alongside — with a note framed as the *last* time this manual step is needed: after pulling this change, delete `backend/testcrafter.db` one more time, then either let `docker compose up`'s automatic `alembic upgrade head` create the schema, or run `alembic upgrade head` manually for a non-Docker setup. Every schema change after this one is a migration, not a manual deletion.

`README.md`/`README.tr.md`'s Docker-based quick start is unaffected (migrations run automatically). The manual (non-Docker) local setup instructions in `README.md`/`CONTRIBUTING.md` gain one line: run `alembic upgrade head` from `backend/` before starting the app.

## 3. Testing

- `backend/tests/test_alembic.py` (new) — runs `alembic upgrade head` against a fresh temporary SQLite file (via Alembic's Python API, `alembic.command.upgrade`, pointed at a `tmp_path`-scoped database URL, not the real dev DB), then inspects the resulting schema (via SQLAlchemy's `inspect(engine)`) and asserts every table and column that `app.models.Base.metadata` declares actually exists with a matching name/type. This is the automated guard against the exact failure mode §20 names as its motivating incident (a migration that was generated but never kept in sync with the model).

## 4. Documentation

- `docs/architecture.md`: new "Database migrations" section (alongside the existing "Auth" section, same file/pattern) covering: Alembic chosen over `create_all` for real deployments, the deliberate test-vs-production split (`create_all` for tests, migrations for everything else), and how to add a new migration (`alembic revision --autogenerate -m "..."`, review the generated file before committing, never hand-edit an already-committed migration).
- `CONTRIBUTING.md`: replace the existing "delete local db" note per the transition plan above; add the `alembic upgrade head` step to non-Docker setup instructions.
- `README.md` / `README.tr.md`: add the one-line manual-setup migration step; no change to the Docker quick start.
- `docs/data-model.md`: no content change needed (it documents the schema's current shape, which isn't changing) — but add one sentence noting the schema is now managed via Alembic migrations under `backend/alembic/versions/`, not `create_all`, so a reader knows where schema history actually lives.

## 5. Out of Scope

- CI workflow / `alembic check` automation — no GitHub Actions workflow exists in this repo at all yet (despite `docs/architecture.md` referencing CI aspirationally); adding one is a separate, larger piece of work the user explicitly deferred. `alembic check`'s manual-run equivalent (the new `test_alembic.py`) covers the immediate risk in the meantime.
- PostgreSQL-specific migration concerns (e.g. `alembic` async support, connection pooling differences) — out of scope while the project stays SQLite-only; the schema is already designed to map 1:1 to PostgreSQL per existing decisions, and Alembic itself is DB-agnostic, so this isn't expected to require rework later.
- Data migrations / backfills for existing rows — not applicable, there's no production data to migrate (local MVP, single/few developers).
