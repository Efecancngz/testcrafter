# Contributing

## Setup

```bash
cd backend && pip install -e ".[dev]" && playwright install chromium
cd frontend && npm install
```

Or via Docker: `docker compose up --build`.

## Running tests

```bash
cd backend && pytest -v
```

## Branch / PR flow

- Branch from `main`: `git checkout -b feat/<short-description>`
- One logical change per PR
- Every backend change needs a passing test (see `docs/architecture.md` for testing layers)
- Open a PR against `main`; CI must pass before merge

## Commit messages

Conventional-commit style prefixes: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`. No AI co-author trailers — see `CLAUDE.md`.

## Code style

- Comments explain WHY, not WHAT
- No speculative abstractions — see `docs/architecture.md` decisions log for the reasoning behind current boundaries (e.g. why the AI layer is abstracted from day one but auth isn't built yet)
