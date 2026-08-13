# Data Model

ER diagram and column reference for the SQLAlchemy models in `backend/app/models.py`.

## Entity-Relationship Diagram

```
User 1──N Project 1──N Scan 1──N Scenario 1──N Run 1──N RunStep
```

## Tables

### users
| Column | Type | Notes |
|---|---|---|
| id | int, PK | |
| email | string, unique | MVP seeds one demo user (`demo@testcrafter.local`) |
| created_at | datetime | |

### projects
| Column | Type | Notes |
|---|---|---|
| id | int, PK | |
| user_id | int, FK -> users.id | |
| name | string | |
| base_url | string | |
| created_at | datetime | |

### scans
| Column | Type | Notes |
|---|---|---|
| id | int, PK | |
| project_id | int, FK -> projects.id | |
| target_url | string | |
| description | text | user-provided context for scenario generation |
| page_structure_json | text | JSON dump of the crawler's `PageStructure` |
| ai_provider | string | e.g. `"claude"` |
| status | string | `pending` \| `analyzing` \| `ready` \| `failed` |
| created_at | datetime | |

### scenarios
| Column | Type | Notes |
|---|---|---|
| id | int, PK | |
| scan_id | int, FK -> scans.id | |
| title | string | |
| steps_json | text | JSON dump of `list[ScenarioStep]` |
| created_at | datetime | |

### runs
| Column | Type | Notes |
|---|---|---|
| id | int, PK | |
| scenario_id | int, FK -> scenarios.id | |
| status | string | `passed` \| `failed` — set by `POST /scans/{scan_id}/run` once all of the scenario's steps have executed; `passed` only if every step passed. `pending`/`running`/`error` are reserved for once execution moves off the request/response cycle (background jobs, provider-level failures), not written today |
| error_message | text, nullable | reserved for provider/infra-level failures (e.g. the browser fails to launch); not written by the current synchronous runner — see `run_steps.log_message` for per-step failure detail |
| started_at / finished_at | datetime, nullable | wall-clock bounds of the Playwright run for this scenario |

### run_steps
| Column | Type | Notes |
|---|---|---|
| id | int, PK | |
| run_id | int, FK -> runs.id | |
| step_index | int | |
| status | string | `passed` \| `failed` |
| screenshot_path | string, nullable | URL path (e.g. `/screenshots/{run_id}/{step_index}.png`) served via the FastAPI static mount at `/screenshots`; `None` only if the screenshot capture itself failed (action result is unaffected) |
| log_message | text, nullable | one-line pass confirmation or failure reason from `app/runner.StepResult` |

## Why SQLite now, Postgres-ready later

Schema avoids SQLite-only shortcuts (real foreign keys, no dynamic typing tricks) so a future migration to PostgreSQL only requires changing the connection string in `app/db.py`, not the schema.
