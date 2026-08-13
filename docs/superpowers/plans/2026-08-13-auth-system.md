# Auth System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded `_demo_user` with real JWT-based email+password authentication. Every endpoint that currently attributes work to `_demo_user` becomes scoped to the authenticated caller, with ownership checks along the FK chain. The screenshot static mount (a real auth gap flagged by the previous feature's final review) is replaced with an authorizing proxy endpoint.

**Architecture:** `backend/app/auth.py` owns password hashing, JWT issuance/validation, and a `get_current_user` FastAPI dependency. `backend/app/api/auth.py` exposes `/auth/register` and `/auth/login`. Every existing endpoint in `projects.py`/`scans.py` gains `user: User = Depends(get_current_user)` and filters/verifies ownership. The screenshot static mount is removed; a new `GET /runs/{run_id}/screenshots/{step_index}` endpoint checks ownership through `Run → Scenario → Scan → Project → User` before serving the file. The frontend gains a login/register form, attaches `Authorization: Bearer` headers to every API call, and fetches screenshots as authenticated blobs instead of plain `<img src>`.

**Tech Stack:** `pyjwt` (JWT), `bcrypt` (password hashing) — both new backend dependencies. No new frontend dependencies.

## Global Constraints

- No migration tooling exists in this project (schema created via `Base.metadata.create_all`, which doesn't alter existing tables). This plan does not add Alembic. `CONTRIBUTING.md` gets a note that local `testcrafter.db` must be deleted after this change lands.
- `SECRET_KEY` env var has no default — missing it is a startup/runtime config error (`RuntimeError`), never a silently-insecure fallback.
- Ownership failures return `404`, never `403` — consistent with the existing "don't leak existence" pattern already used for `scan not found`.
- Login failure (wrong password vs. nonexistent email) returns the same generic message either way — don't leak which one.
- Follow existing repo conventions: no comments except non-obvious WHY, no speculative abstractions.
- Never add a "Co-Authored-By: Claude" (or any AI attribution) trailer to commits — hard rule for this repo.
- No Alembic, no email verification, no password reset, no OAuth, no refresh tokens/logout-invalidation, no RBAC, no login rate-limiting — all explicitly out of scope per the approved spec.

---

## Task 1: Auth module — hashing, JWT, `get_current_user`

**Files:**
- Modify: `backend/app/models.py` (add `password_hash` to `User`)
- Modify: `backend/pyproject.toml` (add `pyjwt`, `bcrypt`)
- Modify: `backend/tests/conftest.py` (autouse `SECRET_KEY` fixture for all tests)
- Create: `backend/app/auth.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: `User` model, `get_session` (`app/db.py`) — both pre-existing.
- Produces: `hash_password(password: str) -> str`, `verify_password(password: str, password_hash: str) -> bool`, `create_access_token(user_id: int) -> str`, `get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> User`, `oauth2_scheme` (a module-level `OAuth2PasswordBearer(tokenUrl="/auth/login")`), `ALGORITHM` (module constant, `"HS256"`) — all importable from `app.auth`. Task 2 imports `hash_password`, `verify_password`, `create_access_token`. Tasks 3 and 4 import `get_current_user`.

- [ ] **Step 1: Add `password_hash` to the `User` model**

In `backend/app/models.py`, change:

```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
```

to:

```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
```

- [ ] **Step 2: Add dependencies**

Edit `backend/pyproject.toml`, add to `dependencies`:

```toml
    "pyjwt>=2.9",
    "bcrypt>=4.2",
```

- [ ] **Step 3: Install them**

Run: `cd backend && pip install -e ".[dev]"`
Expected: installs successfully, no errors.

- [ ] **Step 4: Add an autouse `SECRET_KEY` fixture to `conftest.py`**

Edit `backend/tests/conftest.py`, add near the top (after the `import pytest` line):

```python
@pytest.fixture(autouse=True)
def _test_secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-do-not-use-in-production")
```

Every test in the suite gets a valid `SECRET_KEY` automatically — later tasks that create tokens through HTTP endpoints don't need to set it themselves.

- [ ] **Step 5: Write the failing tests**

Create `backend/tests/test_auth.py`:

```python
import pytest
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.auth import hash_password, verify_password, create_access_token, get_current_user, ALGORITHM
from app.models import User


def test_hash_password_and_verify_roundtrip():
    hashed = hash_password("s3cret!")
    assert hashed != "s3cret!"
    assert verify_password("s3cret!", hashed)
    assert not verify_password("wrong-password", hashed)


def test_create_access_token_encodes_user_id():
    token = create_access_token(user_id=42)
    payload = jwt.decode(token, "test-secret-key-do-not-use-in-production", algorithms=[ALGORITHM])
    assert payload["sub"] == "42"


def test_get_current_user_returns_user_for_valid_token(db_session):
    user = User(email="a@example.com", password_hash=hash_password("pw"))
    db_session.add(user)
    db_session.flush()
    token = create_access_token(user_id=user.id)

    result = get_current_user(token=token, session=db_session)

    assert result.id == user.id


def test_get_current_user_rejects_malformed_token(db_session):
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token="not-a-real-token", session=db_session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_expired_token(db_session):
    payload = {"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(hours=1)}
    expired_token = jwt.encode(payload, "test-secret-key-do-not-use-in-production", algorithm=ALGORITHM)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token=expired_token, session=db_session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_token_for_deleted_user(db_session):
    token = create_access_token(user_id=999999)

    with pytest.raises(HTTPException) as exc_info:
        get_current_user(token=token, session=db_session)
    assert exc_info.value.status_code == 401


def test_create_access_token_raises_without_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_access_token(user_id=1)
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.auth'`

- [ ] **Step 7: Implement `backend/app/auth.py`**

```python
import os
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import User

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _secret_key() -> str:
    key = os.getenv("SECRET_KEY")
    if not key:
        raise RuntimeError("SECRET_KEY environment variable is not set")
    return key


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, _secret_key(), algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), session: Session = Depends(get_session)) -> User:
    try:
        payload = jwt.decode(token, _secret_key(), algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="invalid or expired token")
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return user
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_auth.py -v`
Expected: PASS (7 passed)

- [ ] **Step 9: Run the full backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS — the `password_hash` column addition doesn't break any existing test (nothing yet constructs a `User` without it via a code path that runs in tests; the only existing `User` construction is via `_demo_user` in `projects.py`, which Task 3 removes — check that no other test currently constructs a bare `User()` without `password_hash` and fails now; if one does, it's pre-existing test debt this step surfaces, not something this task should silently work around — report it if found, don't patch around it).

- [ ] **Step 10: Commit**

```bash
git add backend/app/models.py backend/pyproject.toml backend/tests/conftest.py backend/app/auth.py backend/tests/test_auth.py
git commit -m "feat: add password hashing and JWT auth module"
```

---

## Task 2: Register/login endpoints

**Files:**
- Create: `backend/app/api/auth.py`
- Modify: `backend/app/main.py` (wire in the new router)
- Test: `backend/tests/test_api_auth.py`

**Interfaces:**
- Consumes: `hash_password`, `verify_password`, `create_access_token` (`app.auth`, from Task 1).
- Produces: `POST /auth/register` and `POST /auth/login` HTTP endpoints, both returning `{"access_token": str, "token_type": "bearer"}`. Task 3's test updates and all later tasks' test fixtures obtain tokens by calling these two endpoints over HTTP — no Python-level import of this module's internals is needed elsewhere.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_api_auth.py`:

```python
def test_register_creates_user_and_returns_token(client):
    resp = client.post("/auth/register", json={"email": "a@example.com", "password": "s3cret!"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_register_rejects_duplicate_email(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "s3cret!"})

    resp = client.post("/auth/register", json={"email": "a@example.com", "password": "different"})

    assert resp.status_code == 400


def test_login_succeeds_with_correct_credentials(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "s3cret!"})

    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "s3cret!"})

    assert resp.status_code == 200
    assert resp.json()["access_token"]


def test_login_rejects_wrong_password(client):
    client.post("/auth/register", json={"email": "a@example.com", "password": "s3cret!"})

    resp = client.post("/auth/login", json={"email": "a@example.com", "password": "wrong"})

    assert resp.status_code == 401


def test_login_rejects_nonexistent_email(client):
    resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever"})

    assert resp.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_api_auth.py -v`
Expected: FAIL — `404 Not Found` for `/auth/register` and `/auth/login` (routes don't exist yet).

- [ ] **Step 3: Implement `backend/app/api/auth.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import User
from app.auth import hash_password, verify_password, create_access_token

router = APIRouter()


class AuthRequest(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(payload: AuthRequest, session: Session = Depends(get_session)):
    existing = session.query(User).filter_by(email=payload.email).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="email already registered")
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return TokenOut(access_token=create_access_token(user.id))


@router.post("/auth/login", response_model=TokenOut)
def login(payload: AuthRequest, session: Session = Depends(get_session)):
    user = session.query(User).filter_by(email=payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid email or password")
    return TokenOut(access_token=create_access_token(user.id))
```

- [ ] **Step 4: Wire the router into `main.py`**

In `backend/app/main.py`, add the import (alongside the existing router imports):

```python
from app.api.auth import router as auth_router
```

Add `app.include_router(auth_router)` alongside the existing `app.include_router(...)` calls.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api_auth.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Run the full backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/auth.py backend/app/main.py backend/tests/test_api_auth.py
git commit -m "feat: add register and login endpoints"
```

---

## Task 3: Scope existing endpoints to the authenticated user

**Files:**
- Modify: `backend/app/api/projects.py`
- Modify: `backend/app/api/scans.py`
- Modify: `backend/tests/conftest.py` (add `authenticated_client` fixture)
- Modify: `backend/tests/test_api_projects.py`
- Modify: `backend/tests/test_api_scans.py`

**Interfaces:**
- Consumes: `get_current_user` (`app.auth`, Task 1), `/auth/register` (Task 2, used by the new `authenticated_client` test fixture over HTTP).
- Produces: `authenticated_client` pytest fixture in `conftest.py` (a `client` with a valid `Authorization: Bearer` header already attached, for tests that don't care about auth mechanics themselves). No other task depends on new production-code symbols from this task — Task 4 modifies the same two files further but doesn't import anything new from this task's changes beyond what's already shared (`User`, `get_current_user`).

- [ ] **Step 1: Add the `authenticated_client` fixture**

In `backend/tests/conftest.py`, add after the existing `client` fixture:

```python
@pytest.fixture
def authenticated_client(client):
    token = client.post("/auth/register", json={"email": "test@example.com", "password": "s3cret!"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
```

- [ ] **Step 2: Write the failing tests**

Replace the full contents of `backend/tests/test_api_projects.py`:

```python
def test_list_projects_without_session_override_does_not_500():
    # Regression test: the `client` fixture overrides get_session with a plain
    # generator, which masked get_session being wrongly decorated with
    # @contextmanager (FastAPI's Depends() double-wraps that, breaking every
    # real request with AttributeError on '_GeneratorContextManager'). This
    # hits the app exactly as a real deployment would, with no override.
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as real_client:
        token = real_client.post("/auth/register", json={"email": "real-deployment-check@example.com", "password": "s3cret!"}).json()["access_token"]
        resp = real_client.get("/projects", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200


def test_create_and_list_project(authenticated_client):
    resp = authenticated_client.post("/projects", json={"name": "Demo Site", "base_url": "https://example.com"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Demo Site"

    list_resp = authenticated_client.get("/projects")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


def test_create_project_requires_auth(client):
    resp = client.post("/projects", json={"name": "Demo Site", "base_url": "https://example.com"})
    assert resp.status_code == 401


def test_list_projects_only_returns_own_projects(client):
    token_a = client.post("/auth/register", json={"email": "a@example.com", "password": "pw"}).json()["access_token"]
    client.post("/projects", json={"name": "A's project", "base_url": "https://a.example.com"}, headers={"Authorization": f"Bearer {token_a}"})

    token_b = client.post("/auth/register", json={"email": "b@example.com", "password": "pw"}).json()["access_token"]
    resp = client.get("/projects", headers={"Authorization": f"Bearer {token_b}"})

    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_api_projects.py -v`
Expected: FAIL — `test_create_and_list_project` fails because `/projects` doesn't require/use auth yet (list isn't scoped), `test_create_project_requires_auth` fails because the endpoint currently succeeds without a token (expects 401, gets 201).

- [ ] **Step 4: Implement the scoping in `projects.py`**

Replace the full contents of `backend/app/api/projects.py`:

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import Project, User
from app.auth import get_current_user

router = APIRouter()

class ProjectCreate(BaseModel):
    name: str
    base_url: str

class ProjectOut(BaseModel):
    id: int
    name: str
    base_url: str
    model_config = {"from_attributes": True}

@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    project = Project(user_id=user.id, name=payload.name, base_url=payload.base_url)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project

@router.get("/projects", response_model=list[ProjectOut])
def list_projects(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return session.query(Project).filter_by(user_id=user.id).all()
```

- [ ] **Step 5: Run projects tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api_projects.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Write the failing scans tests**

Replace the full contents of `backend/tests/test_api_scans.py` (this integrates Task 3's auth scoping into the existing screenshot-related tests from the previous feature — every `client.post`/`client.get` that talks to `/projects` or `/scans` becomes `authenticated_client`, and two new cross-user isolation tests are added):

```python
import shutil
from pathlib import Path
from unittest.mock import patch
import pytest
from playwright.sync_api import Error as PlaywrightError
from app.api.scans import SCREENSHOTS_DIR
from app.schemas import PageStructure, PageElement, GeneratedScenario, ScenarioStep
from app.models import Scan

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "login_page.html").as_uri()

def test_create_scan_generates_scenarios(authenticated_client):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url="https://example.com", elements=[PageElement(tag="button", role="button", selector="#submit", text="Go")])
    fake_scenarios = [GeneratedScenario(title="Click submit", steps=[ScenarioStep(action="click", selector="#submit")])]

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        resp = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "Check submit button",
        })

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ready"
    assert len(body["scenarios"]) == 1
    assert body["scenarios"][0]["title"] == "Click submit"

def test_create_scan_persists_ai_provider(authenticated_client, db_session, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url="https://example.com", elements=[PageElement(tag="button", role="button", selector="#submit", text="Go")])
    fake_scenarios = [GeneratedScenario(title="Click submit", steps=[ScenarioStep(action="click", selector="#submit")])]

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        resp = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "Check submit button",
        })

    assert resp.status_code == 201
    scan_id = resp.json()["id"]
    scan = db_session.get(Scan, scan_id)
    assert scan.ai_provider == "gemini"

def test_create_scan_marks_failed_when_crawl_fails(authenticated_client):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    with patch("app.api.scans.extract_page_structure", side_effect=PlaywrightError("net::ERR_NAME_NOT_RESOLVED")):
        resp = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://this-domain-does-not-exist.invalid",
            "description": "Check submit button",
        })

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "failed"
    assert body["scenarios"] == []

def test_create_scan_marks_failed_when_ai_provider_not_configured(authenticated_client):
    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url="https://example.com", elements=[])

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider", side_effect=TypeError("missing ANTHROPIC_API_KEY")):
        resp = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "Check submit button",
        })

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "failed"

def test_create_scan_requires_auth(client):
    resp = client.post("/projects/1/scans", json={"target_url": "https://example.com", "description": "x"})
    assert resp.status_code == 401

def test_create_scan_returns_404_for_project_owned_by_another_user(client):
    token_a = client.post("/auth/register", json={"email": "a@example.com", "password": "pw"}).json()["access_token"]
    project = client.post("/projects", json={"name": "A's project", "base_url": "https://example.com"}, headers={"Authorization": f"Bearer {token_a}"}).json()

    token_b = client.post("/auth/register", json={"email": "b@example.com", "password": "pw"}).json()["access_token"]
    resp = client.post(f"/projects/{project['id']}/scans", json={"target_url": "https://example.com", "description": "x"}, headers={"Authorization": f"Bearer {token_b}"})

    assert resp.status_code == 404

def test_get_scan_not_found_returns_404(authenticated_client):
    resp = authenticated_client.get("/scans/999")
    assert resp.status_code == 404

def test_get_scan_returns_404_for_scan_owned_by_another_user(client):
    token_a = client.post("/auth/register", json={"email": "a@example.com", "password": "pw"}).json()["access_token"]
    project = client.post("/projects", json={"name": "A's project", "base_url": "https://example.com"}, headers={"Authorization": f"Bearer {token_a}"}).json()
    fake_structure = PageStructure(url="https://example.com", elements=[])
    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = []
        scan = client.post(f"/projects/{project['id']}/scans", json={"target_url": "https://example.com", "description": "x"}, headers={"Authorization": f"Bearer {token_a}"}).json()

    token_b = client.post("/auth/register", json={"email": "b@example.com", "password": "pw"}).json()["access_token"]
    resp = client.get(f"/scans/{scan['id']}", headers={"Authorization": f"Bearer {token_b}"})

    assert resp.status_code == 404

def test_run_scan_executes_scenarios_and_persists_results(authenticated_client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.scans.SCREENSHOTS_DIR", tmp_path)

    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url=FIXTURE_URL, elements=[PageElement(tag="button", role="button", selector="#submit", text="Log in")])
    fake_scenarios = [
        GeneratedScenario(
            title="Submit button has correct label",
            steps=[
                ScenarioStep(action="goto", value=FIXTURE_URL),
                ScenarioStep(action="expect_text", selector="#submit", expected="Log in"),
            ],
        )
    ]

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        scan = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": FIXTURE_URL,
            "description": "Check submit button label",
        }).json()

    resp = authenticated_client.post(f"/scans/{scan['id']}/run")

    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "passed"
    assert len(runs[0]["steps"]) == 2
    assert all(step["status"] == "passed" for step in runs[0]["steps"])

def test_run_scan_not_found_returns_404(authenticated_client):
    resp = authenticated_client.post("/scans/999/run")
    assert resp.status_code == 404

def test_run_scan_returns_404_for_scan_owned_by_another_user(client):
    token_a = client.post("/auth/register", json={"email": "a@example.com", "password": "pw"}).json()["access_token"]
    project = client.post("/projects", json={"name": "A's project", "base_url": "https://example.com"}, headers={"Authorization": f"Bearer {token_a}"}).json()
    fake_structure = PageStructure(url="https://example.com", elements=[])
    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = []
        scan = client.post(f"/projects/{project['id']}/scans", json={"target_url": "https://example.com", "description": "x"}, headers={"Authorization": f"Bearer {token_a}"}).json()

    token_b = client.post("/auth/register", json={"email": "b@example.com", "password": "pw"}).json()["access_token"]
    resp = client.post(f"/scans/{scan['id']}/run", headers={"Authorization": f"Bearer {token_b}"})

    assert resp.status_code == 404

def test_get_ai_provider_defaults_to_claude(monkeypatch):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    from app.api.scans import get_ai_provider
    from app.ai.claude_provider import ClaudeProvider
    with patch("anthropic.Anthropic"):
        provider = get_ai_provider()
    assert isinstance(provider, ClaudeProvider)


def test_get_ai_provider_selects_gemini(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    from app.api.scans import get_ai_provider
    from app.ai.gemini_provider import GeminiProvider
    with patch("google.genai.Client"):
        provider = get_ai_provider()
    assert isinstance(provider, GeminiProvider)


def test_get_ai_provider_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "not-a-real-provider")
    from app.api.scans import get_ai_provider
    with pytest.raises(ValueError, match="unknown AI_PROVIDER"):
        get_ai_provider()
```

(Note: this removes `test_screenshot_path_is_served_by_static_mount` — that test targeted the static mount, which Task 4 removes entirely. Task 4 adds its own replacement test for the new proxy endpoint. Removing it here means this task's test run temporarily has no screenshot-serving coverage; that's expected and closed by Task 4, not a gap to fix in this task.)

- [ ] **Step 7: Run scans tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_api_scans.py -v`
Expected: FAIL — auth-related tests fail (401 checks fail because endpoints don't require auth yet; ownership 404 checks fail because there's no ownership scoping yet).

- [ ] **Step 8: Implement the scoping in `scans.py`**

In `backend/app/api/scans.py`:

Add to imports:

```python
from app.models import Project, Run, RunStep, Scan, Scenario, User
from app.auth import get_current_user
```

(replacing the existing `from app.models import Run, RunStep, Scan, Scenario` line — merge, don't duplicate.)

Add a helper function after the existing imports/router/`get_ai_provider` block:

```python
def _get_owned_scan(scan_id: int, user: User, session: Session) -> Scan:
    scan = (
        session.query(Scan)
        .join(Project, Scan.project_id == Project.id)
        .filter(Scan.id == scan_id, Project.user_id == user.id)
        .first()
    )
    if scan is None:
        raise HTTPException(status_code=404, detail="scan not found")
    return scan
```

Change `create_scan`'s signature and add ownership verification. Current:

```python
@router.post("/projects/{project_id}/scans", response_model=ScanOut, status_code=201)
def create_scan(project_id: int, payload: ScanCreate, session: Session = Depends(get_session)):
    scan = Scan(
```

becomes:

```python
@router.post("/projects/{project_id}/scans", response_model=ScanOut, status_code=201)
def create_scan(project_id: int, payload: ScanCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    project = session.query(Project).filter_by(id=project_id, user_id=user.id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    scan = Scan(
```

(the rest of `create_scan`'s body is unchanged).

Change `get_scan`. Current:

```python
@router.get("/scans/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: int, session: Session = Depends(get_session)):
    scan = session.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="scan not found")
    scenarios = session.query(Scenario).filter_by(scan_id=scan.id).all()
    return ScanOut(id=scan.id, target_url=scan.target_url, status=scan.status, scenarios=scenarios)
```

becomes:

```python
@router.get("/scans/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    scan = _get_owned_scan(scan_id, user, session)
    scenarios = session.query(Scenario).filter_by(scan_id=scan.id).all()
    return ScanOut(id=scan.id, target_url=scan.target_url, status=scan.status, scenarios=scenarios)
```

Change `run_scan`'s signature. Current:

```python
@router.post("/scans/{scan_id}/run", response_model=list[RunOut])
def run_scan(scan_id: int, session: Session = Depends(get_session)):
    scan = session.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="scan not found")
```

becomes:

```python
@router.post("/scans/{scan_id}/run", response_model=list[RunOut])
def run_scan(scan_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    scan = _get_owned_scan(scan_id, user, session)
```

(the rest of `run_scan`'s body is unchanged).

- [ ] **Step 9: Run scans tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api_scans.py -v`
Expected: PASS (13 passed — the file now has 13 tests after removing the static-mount test and adding the new auth/ownership tests).

- [ ] **Step 10: Run the full backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 11: Commit**

```bash
git add backend/tests/conftest.py backend/app/api/projects.py backend/app/api/scans.py backend/tests/test_api_projects.py backend/tests/test_api_scans.py
git commit -m "feat: scope projects and scans endpoints to the authenticated user"
```

---

## Task 4: Screenshot proxy endpoint (replaces the static mount)

**Files:**
- Modify: `backend/app/main.py` (remove static mount)
- Modify: `backend/app/api/scans.py` (add proxy endpoint, change `screenshot_path` format)
- Modify: `backend/tests/test_api_scans.py` (replace static-mount test with proxy-endpoint tests)

**Interfaces:**
- Consumes: `get_current_user` (`app.auth`, Task 1), `SCREENSHOTS_DIR` (already exists in `scans.py`), `_get_owned_scan` pattern established in Task 3 (this task writes its own analogous ownership-chain query, one join deeper).
- Produces: `GET /runs/{run_id}/screenshots/{step_index}` endpoint. `RunStep.screenshot_path` now stores `/runs/{run_id}/screenshots/{step_index}` (no file extension). No other task consumes new symbols from this task — it's consumed only by the frontend (Task 5) as a URL pattern, not a Python import.

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_api_scans.py`, first change the existing screenshot-path-format assertion inside `test_run_scan_executes_scenarios_and_persists_results`. Find:

```python
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "passed"
    assert len(runs[0]["steps"]) == 2
    assert all(step["status"] == "passed" for step in runs[0]["steps"])
```

and change it to also assert the new path format:

```python
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "passed"
    assert len(runs[0]["steps"]) == 2
    assert all(step["status"] == "passed" for step in runs[0]["steps"])
    run_id = runs[0]["id"]
    for index, step in enumerate(runs[0]["steps"]):
        assert step["screenshot_path"] == f"/runs/{run_id}/screenshots/{index}"
```

Then add new tests at the end of the file:

```python
def test_screenshot_proxy_serves_file_to_owner(authenticated_client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.scans.SCREENSHOTS_DIR", tmp_path)

    project = authenticated_client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url=FIXTURE_URL, elements=[PageElement(tag="button", role="button", selector="#submit", text="Log in")])
    fake_scenarios = [
        GeneratedScenario(
            title="Submit button has correct label",
            steps=[ScenarioStep(action="goto", value=FIXTURE_URL)],
        )
    ]

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        scan = authenticated_client.post(f"/projects/{project['id']}/scans", json={
            "target_url": FIXTURE_URL,
            "description": "x",
        }).json()

    run_resp = authenticated_client.post(f"/scans/{scan['id']}/run")
    run_id = run_resp.json()[0]["id"]
    on_disk_path = tmp_path / str(run_id) / "0.png"
    assert on_disk_path.is_file()
    expected_bytes = on_disk_path.read_bytes()

    resp = authenticated_client.get(f"/runs/{run_id}/screenshots/0")

    assert resp.status_code == 200
    assert resp.content == expected_bytes


def test_screenshot_proxy_requires_auth(client):
    resp = client.get("/runs/1/screenshots/0")
    assert resp.status_code == 401


def test_screenshot_proxy_returns_404_for_run_owned_by_another_user(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.api.scans.SCREENSHOTS_DIR", tmp_path)

    token_a = client.post("/auth/register", json={"email": "a@example.com", "password": "pw"}).json()["access_token"]
    project = client.post("/projects", json={"name": "A's project", "base_url": "https://example.com"}, headers={"Authorization": f"Bearer {token_a}"}).json()

    fake_structure = PageStructure(url=FIXTURE_URL, elements=[PageElement(tag="button", role="button", selector="#submit", text="Log in")])
    fake_scenarios = [GeneratedScenario(title="Submit button has correct label", steps=[ScenarioStep(action="goto", value=FIXTURE_URL)])]
    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        scan = client.post(f"/projects/{project['id']}/scans", json={"target_url": FIXTURE_URL, "description": "x"}, headers={"Authorization": f"Bearer {token_a}"}).json()
    run_id = client.post(f"/scans/{scan['id']}/run", headers={"Authorization": f"Bearer {token_a}"}).json()[0]["id"]

    token_b = client.post("/auth/register", json={"email": "b@example.com", "password": "pw"}).json()["access_token"]
    resp = client.get(f"/runs/{run_id}/screenshots/0", headers={"Authorization": f"Bearer {token_b}"})

    assert resp.status_code == 404


def test_screenshot_proxy_returns_404_for_nonexistent_run(authenticated_client):
    resp = authenticated_client.get("/runs/999999/screenshots/0")
    assert resp.status_code == 404
```

Then delete the now-obsolete `test_screenshot_path_is_served_by_static_mount` function entirely (it tests the static mount, which this task removes).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_api_scans.py -v`
Expected: FAIL — the path-format assertion fails (`/screenshots/...` still produced), and the new proxy tests fail with 404 (route doesn't exist yet).

- [ ] **Step 3: Remove the static mount from `main.py`**

Replace the full contents of `backend/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db import Base, engine
from app.api.auth import router as auth_router
from app.api.projects import router as projects_router
from app.api.scans import router as scans_router

Base.metadata.create_all(engine)

app = FastAPI(title="testcrafter")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(scans_router)
```

- [ ] **Step 4: Add the proxy endpoint and change the stored path format in `scans.py`**

In `backend/app/api/scans.py`, add the import:

```python
from fastapi.responses import FileResponse
```

Change the screenshot path construction in `run_scan`. Current:

```python
        for index, result in enumerate(results):
            screenshot_path = f"/screenshots/{run.id}/{Path(result.screenshot_path).name}" if result.screenshot_path else None
            session.add(RunStep(run_id=run.id, step_index=index, status=result.status, log_message=result.log_message, screenshot_path=screenshot_path))
```

becomes:

```python
        for index, result in enumerate(results):
            screenshot_path = f"/runs/{run.id}/screenshots/{index}" if result.screenshot_path else None
            session.add(RunStep(run_id=run.id, step_index=index, status=result.status, log_message=result.log_message, screenshot_path=screenshot_path))
```

Add the proxy endpoint at the end of the file:

```python
@router.get("/runs/{run_id}/screenshots/{step_index}")
def get_screenshot(run_id: int, step_index: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    owned = (
        session.query(RunStep)
        .join(Run, RunStep.run_id == Run.id)
        .join(Scenario, Run.scenario_id == Scenario.id)
        .join(Scan, Scenario.scan_id == Scan.id)
        .join(Project, Scan.project_id == Project.id)
        .filter(RunStep.run_id == run_id, RunStep.step_index == step_index, Project.user_id == user.id)
        .first()
    )
    if owned is None:
        raise HTTPException(status_code=404, detail="screenshot not found")
    file_path = SCREENSHOTS_DIR / str(run_id) / f"{step_index}.png"
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="screenshot not found")
    return FileResponse(file_path)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_api_scans.py -v`
Expected: PASS (16 passed)

- [ ] **Step 6: Run the full backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/app/api/scans.py backend/tests/test_api_scans.py
git commit -m "feat: replace screenshot static mount with an authorizing proxy endpoint"
```

---

## Task 5: Frontend auth + authenticated screenshot fetch + docs

**Files:**
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/App.jsx`
- Modify: `docs/architecture.md`
- Modify: `docs/api-spec.md`
- Modify: `docs/data-model.md`
- Modify: `CONTRIBUTING.md`
- Modify: `README.md`
- Modify: `README.tr.md`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `POST /auth/register`, `POST /auth/login`, `GET /runs/{run_id}/screenshots/{step_index}` (Tasks 2 and 4, HTTP only, no Python-level dependency).
- Produces: nothing consumed by later tasks (final task in this plan).

- [ ] **Step 1: Add `SECRET_KEY` to `.env.example`**

Edit `.env.example`, add a line:

```
SECRET_KEY=
```

- [ ] **Step 2: Rewrite `frontend/src/api.js`**

Replace the full contents:

```js
export const BASE_URL = "http://localhost:8000";

function getToken() {
  return localStorage.getItem("token");
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function handleResponse(res) {
  if (res.status === 401) {
    localStorage.removeItem("token");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `Request failed with status ${res.status}`);
  }
  return res.json();
}

export async function register(email, password) {
  const res = await fetch(`${BASE_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const body = await handleResponse(res);
  localStorage.setItem("token", body.access_token);
  return body;
}

export async function login(email, password) {
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const body = await handleResponse(res);
  localStorage.setItem("token", body.access_token);
  return body;
}

export function logout() {
  localStorage.removeItem("token");
}

export function isAuthenticated() {
  return !!getToken();
}

export async function createProject(name, baseUrl) {
  const res = await fetch(`${BASE_URL}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, base_url: baseUrl }),
  });
  return handleResponse(res);
}

export async function createScan(projectId, targetUrl, description) {
  const res = await fetch(`${BASE_URL}/projects/${projectId}/scans`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ target_url: targetUrl, description }),
  });
  return handleResponse(res);
}

export async function runScan(scanId) {
  const res = await fetch(`${BASE_URL}/scans/${scanId}/run`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handleResponse(res);
}

export async function fetchScreenshotUrl(path) {
  const res = await fetch(`${BASE_URL}${path}`, { headers: { ...authHeaders() } });
  if (!res.ok) {
    throw new Error(`Failed to load screenshot (status ${res.status})`);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}
```

- [ ] **Step 3: Rewrite `frontend/src/App.jsx`**

Replace the full contents:

```jsx
import { useState, useEffect } from "react";
import { createProject, createScan, runScan, register, login, logout, isAuthenticated, fetchScreenshotUrl } from "./api";

function Screenshot({ path, stepIndex }) {
  const [src, setSrc] = useState(null);

  useEffect(() => {
    let objectUrl;
    let cancelled = false;
    fetchScreenshotUrl(path).then((url) => {
      if (cancelled) return;
      objectUrl = url;
      setSrc(url);
    }).catch(() => {});
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [path]);

  if (!src) return null;
  return <img src={src} alt={`Step ${stepIndex} screenshot`} loading="lazy" style={{ maxWidth: 200 }} />;
}

function AuthForm({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
      onAuthenticated();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{ maxWidth: 320, margin: "4rem auto", fontFamily: "sans-serif" }}>
      <h1>testcrafter</h1>
      <form onSubmit={handleSubmit}>
        <input placeholder="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <input placeholder="Password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <button type="submit" disabled={submitting}>{mode === "login" ? "Log in" : "Register"}</button>
      </form>
      {error && <p style={{ color: "red" }}>{error}</p>}
      <button onClick={() => setMode(mode === "login" ? "register" : "login")} style={{ marginTop: 8 }}>
        {mode === "login" ? "Need an account? Register" : "Have an account? Log in"}
      </button>
    </div>
  );
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(isAuthenticated());
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [scan, setScan] = useState(null);
  const [loading, setLoading] = useState(false);
  const [runs, setRuns] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);

  if (!authenticated) {
    return <AuthForm onAuthenticated={() => setAuthenticated(true)} />;
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setRuns(null);
    setLoading(true);
    try {
      const project = await createProject("Ad-hoc scan", url);
      const result = await createScan(project.id, url, description);
      setScan(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleRun() {
    setError(null);
    setRunning(true);
    try {
      const result = await runScan(scan.id);
      setRuns(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setRunning(false);
    }
  }

  function handleLogout() {
    logout();
    setAuthenticated(false);
    setScan(null);
    setRuns(null);
  }

  return (
    <div style={{ maxWidth: 640, margin: "2rem auto", fontFamily: "sans-serif" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>testcrafter</h1>
        <button onClick={handleLogout}>Log out</button>
      </div>
      <form onSubmit={handleSubmit}>
        <input placeholder="Target URL" value={url} onChange={(e) => setUrl(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <textarea placeholder="What should be tested?" value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <button type="submit" disabled={loading}>{loading ? "Generating..." : "Generate scenarios"}</button>
      </form>
      {error && <p style={{ color: "red" }}>{error}</p>}
      {scan && (
        <div>
          <h2>Status: {scan.status}</h2>
          <ul>
            {scan.scenarios.map((s) => (
              <li key={s.id}>{s.title}</li>
            ))}
          </ul>
          {scan.status === "ready" && (
            <button onClick={handleRun} disabled={running}>{running ? "Running..." : "Run scenarios"}</button>
          )}
        </div>
      )}
      {runs && (
        <div>
          <h2>Results</h2>
          <ul>
            {runs.map((run) => (
              <li key={run.id}>
                Scenario {run.scenario_id}: {run.status}
                <ul>
                  {run.steps.map((step) => (
                    <li key={step.id}>
                      Step {step.step_index}: {step.status} {step.log_message ? `— ${step.log_message}` : ""}
                      {step.screenshot_path && (
                        <div>
                          <Screenshot path={step.screenshot_path} stepIndex={step.step_index} />
                        </div>
                      )}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Manually verify in the browser**

Run: `cd backend && python -m uvicorn app.main:app --reload` (in one terminal, with `SECRET_KEY` set in the environment — e.g. `SECRET_KEY=dev-only-secret python -m uvicorn app.main:app --reload`) and `cd frontend && npm run dev` (in another). Open `http://localhost:5173`, confirm the login form appears, register a new account, confirm you land on the main scan form, submit a scan against a reachable URL with a real AI provider configured if available (check `.env` for an existing key — if none is available, at minimum verify the register/login/logout flow works and the main form renders after auth), run it, and confirm results (and screenshots, if a real provider call succeeded) render. Log out and confirm the login form reappears and a protected API call without a token fails. This is a manual check — no automated browser test is in scope.

- [ ] **Step 5: Update `docs/architecture.md`**

Read the current file first. Add a new section (after the existing "Flow" or "AI provider abstraction" section — implementer's judgment on placement, keep it near the other architectural descriptions) titled `## Auth`, covering: JWT-based, stateless (no session store), `bcrypt` password hashing, why JWT was chosen over server-side sessions (matches the existing FastAPI/SPA architecture, no session store needed, consistent with the "no hosting yet but SaaS-ready" posture). Update any existing sentence that still describes `_demo_user`/no-auth as the current state (search for `_demo_user` and "no auth" in the file) to reflect that auth is now implemented.

- [ ] **Step 6: Update `docs/api-spec.md`**

Read the current file first. Update the `POST /projects` section — remove the `_demo_user` reference, replace with: creates a project owned by the authenticated caller (`Depends(get_current_user)`), the `user_id` FK usage described previously is now exercised for real. Update `GET /projects` to note it's now scoped to the caller's own projects (closing a real gap — previously it returned every project regardless of owner). Update `POST /projects/{project_id}/scans`, `GET /scans/{scan_id}`, `POST /scans/{scan_id}/run` to note they require auth and 404 (not 403) on a project/scan not owned by the caller. Replace the screenshot-serving paragraph (currently describing the static mount) with a description of the new `GET /runs/{run_id}/screenshots/{step_index}` endpoint and why it exists (the static mount had no ownership check — flagged by the screenshot-capture feature's final review, closed here). Add a new section for `POST /auth/register` / `POST /auth/login` explaining the design choices: same generic error for wrong password vs. nonexistent email (don't leak which), immediate login on register (no email verification, out of scope per this feature's spec), stateless JWT (no server-side session/revocation list — a known, accepted MVP limitation).

- [ ] **Step 7: Update `docs/data-model.md`**

Read the current file first. Add `password_hash | string | bcrypt hash, never logged or returned by any endpoint |` to the `users` table. Update the `run_steps.screenshot_path` row's description to reflect the new `/runs/{run_id}/screenshots/{step_index}` endpoint-path format (not a public static URL) and that it now requires the caller to own the run.

- [ ] **Step 8: Update `CONTRIBUTING.md`**

Read the current file first. Add a note under "Setup" that after pulling this change, developers must delete their local `testcrafter.db` (schema has no migration tooling — a new non-nullable `password_hash` column was added to an existing table) and that `SECRET_KEY` must be set in `.env` for the backend to start.

- [ ] **Step 9: Update `README.md`**

Change:

```
cp .env.example .env   # set AI_PROVIDER and add the matching API key (ANTHROPIC_API_KEY or GEMINI_API_KEY)
```

to:

```
cp .env.example .env   # set AI_PROVIDER, the matching API key (ANTHROPIC_API_KEY or GEMINI_API_KEY), and SECRET_KEY
```

Add a brief note after "Quick start" (one line, not a tutorial) that the app now requires registering an account on first use.

- [ ] **Step 10: Update `README.tr.md`**

Apply the equivalent Turkish-language edits to the same two spots (the setup command comment and the one-line registration note), matching the existing file's tone/register.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/api.js frontend/src/App.jsx docs/architecture.md docs/api-spec.md docs/data-model.md CONTRIBUTING.md README.md README.tr.md .env.example
git commit -m "feat: add frontend auth UI and authenticated screenshot fetch, update docs"
```
