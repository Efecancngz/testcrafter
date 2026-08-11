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
| status | string | `pending` \| `running` \| `passed` \| `failed` \| `error` |
| error_message | text, nullable | human-readable summary only |
| started_at / finished_at | datetime, nullable | |

### run_steps
| Column | Type | Notes |
|---|---|---|
| id | int, PK | |
| run_id | int, FK -> runs.id | |
| step_index | int | |
| status | string | `passed` \| `failed` |
| screenshot_path | string, nullable | |
| log_message | text, nullable | |

## Why SQLite now, Postgres-ready later

Schema avoids SQLite-only shortcuts (real foreign keys, no dynamic typing tricks) so a future migration to PostgreSQL only requires changing the connection string in `app/db.py`, not the schema.
