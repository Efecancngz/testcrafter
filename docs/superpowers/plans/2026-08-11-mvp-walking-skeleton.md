# testcrafter MVP Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first end-to-end working slice of testcrafter: submit a URL + description via the API, generate test scenarios via a (mocked-in-tests) AI provider, run them with Playwright, and see pass/fail results — backend fully tested, minimal frontend to prove the loop works.

**Architecture:** FastAPI backend with SQLAlchemy/SQLite, a provider-agnostic `AIProvider` interface with a Claude adapter, a Playwright-based crawler and runner, REST endpoints wiring it together, and a minimal React page to trigger a scan and view results. Full rationale in `docs/architecture.md`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x, SQLite, pytest, httpx, Playwright (Python), anthropic SDK, React + Vite, Docker Compose.

## Global Constraints

- Never add a "Co-Authored-By: Claude" trailer to any commit (see `CLAUDE.md`).
- AI provider JSON output must be validated against a Pydantic schema; a mismatch is an error, never silently accepted.
- User-facing errors are human-readable; stack traces stay in backend logs only.
- Comments only for non-obvious WHY, never WHAT.
- No speculative abstraction beyond what's specified below.

---

## File Structure

```
backend/
├── pyproject.toml
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI app, router mounting
│   ├── db.py                  # SQLAlchemy engine/session setup
│   ├── models.py               # ORM models: User, Project, Scan, Scenario, Run, RunStep
│   ├── schemas.py              # Pydantic request/response + AI-output schemas
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── base.py              # AIProvider ABC
│   │   └── claude_provider.py   # ClaudeProvider implementation
│   ├── crawler.py              # extract_page_structure(url) -> PageStructure
│   ├── runner.py                # run_scenario(scenario) -> RunResult
│   └── api/
│       ├── __init__.py
│       ├── projects.py          # /projects endpoints
│       └── scans.py             # /projects/{id}/scans, /scans/{id}, /scans/{id}/run endpoints
├── tests/
│   ├── conftest.py              # test DB fixture, FastAPI TestClient fixture
│   ├── test_models.py
│   ├── test_ai_claude_provider.py
│   ├── test_crawler.py
│   ├── test_runner.py
│   ├── test_api_projects.py
│   └── test_api_scans.py
frontend/
├── package.json
├── index.html
├── src/
│   ├── main.jsx
│   ├── App.jsx                  # form to start a scan + results list
│   └── api.js                   # fetch wrappers for backend
docker-compose.yml
```

---

### Task 1: Backend scaffold and DB models

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_models.py`

**Interfaces:**
- Produces: `Base` (SQLAlchemy declarative base) from `app.db`, `get_session()` context manager from `app.db`, ORM classes `User`, `Project`, `Scan`, `Scenario`, `Run`, `RunStep` from `app.models` with columns exactly as in `docs/architecture.md` §5.

- [ ] **Step 1: Create `backend/pyproject.toml`**

```toml
[project]
name = "testcrafter-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy>=2.0",
    "pydantic>=2.9",
    "anthropic>=0.39",
    "playwright>=1.48",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "httpx>=0.27", "pytest-asyncio>=0.24"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Write the failing test for models**

```python
# backend/tests/test_models.py
from app.models import User, Project, Scan, Scenario, Run, RunStep

def test_can_create_full_chain(db_session):
    user = User(email="demo@testcrafter.local")
    db_session.add(user)
    db_session.flush()

    project = Project(user_id=user.id, name="Demo Site", base_url="https://example.com")
    db_session.add(project)
    db_session.flush()

    scan = Scan(
        project_id=project.id,
        target_url="https://example.com/login",
        description="Login form should validate empty fields",
        page_structure_json="{}",
        ai_provider="claude",
        status="pending",
    )
    db_session.add(scan)
    db_session.flush()

    scenario = Scenario(scan_id=scan.id, title="Empty login shows error", steps_json="[]")
    db_session.add(scenario)
    db_session.flush()

    run = Run(scenario_id=scenario.id, status="pending")
    db_session.add(run)
    db_session.flush()

    step = RunStep(run_id=run.id, step_index=0, status="passed", log_message="ok")
    db_session.add(step)
    db_session.commit()

    assert db_session.query(RunStep).count() == 1
    assert step.run_id == run.id
    assert run.scenario_id == scenario.id
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models'` (and no `db_session` fixture yet)

- [ ] **Step 4: Create `backend/app/db.py`**

```python
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

def make_engine(url: str = "sqlite:///./testcrafter.db"):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)

engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 5: Create `backend/app/models.py`**

```python
from datetime import datetime, timezone
from sqlalchemy import String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String)
    base_url: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

class Scan(Base):
    __tablename__ = "scans"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    target_url: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text)
    page_structure_json: Mapped[str] = mapped_column(Text)
    ai_provider: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

class Scenario(Base):
    __tablename__ = "scenarios"
    id: Mapped[int] = mapped_column(primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"))
    title: Mapped[str] = mapped_column(String)
    steps_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)

class Run(Base):
    __tablename__ = "runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    scenario_id: Mapped[int] = mapped_column(ForeignKey("scenarios.id"))
    status: Mapped[str] = mapped_column(String, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class RunStep(Base):
    __tablename__ = "run_steps"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    step_index: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    screenshot_path: Mapped[str | None] = mapped_column(String, nullable=True)
    log_message: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 6: Create `backend/tests/conftest.py`**

```python
import pytest
from sqlalchemy.orm import sessionmaker
from app.db import Base, make_engine

@pytest.fixture
def db_session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()
```

- [ ] **Step 7: Run test to verify it passes**

Run: `cd backend && pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
cd backend && git add pyproject.toml app/__init__.py app/db.py app/models.py tests/conftest.py tests/test_models.py
git commit -m "feat: add DB models and in-memory test fixture"
```

---

### Task 2: AIProvider interface and Claude adapter

**Files:**
- Create: `backend/app/schemas.py`
- Create: `backend/app/ai/__init__.py`
- Create: `backend/app/ai/base.py`
- Create: `backend/app/ai/claude_provider.py`
- Test: `backend/tests/test_ai_claude_provider.py`

**Interfaces:**
- Consumes: nothing from Task 1 directly (schemas are standalone Pydantic models).
- Produces: `PageStructure` and `ScenarioStep`/`GeneratedScenario` Pydantic models from `app.schemas`; `AIProvider` ABC with method `generate_scenarios(page_structure: PageStructure, description: str) -> list[GeneratedScenario]` from `app.ai.base`; `ClaudeProvider(AIProvider)` from `app.ai.claude_provider`, constructed as `ClaudeProvider(client=<anthropic.Anthropic-like object>)`.

- [ ] **Step 1: Create `backend/app/schemas.py`**

```python
from pydantic import BaseModel

class PageElement(BaseModel):
    tag: str
    role: str  # "button" | "input" | "link" | "form"
    selector: str
    text: str | None = None

class PageStructure(BaseModel):
    url: str
    elements: list[PageElement]

class ScenarioStep(BaseModel):
    action: str      # "click" | "fill" | "goto" | "expect_text" | "expect_url"
    selector: str | None = None
    value: str | None = None
    expected: str | None = None

class GeneratedScenario(BaseModel):
    title: str
    steps: list[ScenarioStep]
```

- [ ] **Step 2: Write the failing test for the Claude adapter**

```python
# backend/tests/test_ai_claude_provider.py
import json
import pytest
from app.ai.claude_provider import ClaudeProvider
from app.schemas import PageStructure, PageElement

class FakeMessage:
    def __init__(self, text: str):
        self.content = [type("Block", (), {"text": text})()]

class FakeMessagesAPI:
    def __init__(self, response_text: str):
        self._response_text = response_text
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return FakeMessage(self._response_text)

class FakeAnthropicClient:
    def __init__(self, response_text: str):
        self.messages = FakeMessagesAPI(response_text)

def test_generate_scenarios_parses_valid_json():
    payload = json.dumps([
        {
            "title": "Empty login shows validation error",
            "steps": [
                {"action": "goto", "value": "https://example.com/login"},
                {"action": "click", "selector": "#submit"},
                {"action": "expect_text", "selector": "#error", "expected": "required"},
            ],
        }
    ])
    fake_client = FakeAnthropicClient(payload)
    provider = ClaudeProvider(client=fake_client)
    page = PageStructure(
        url="https://example.com/login",
        elements=[PageElement(tag="input", role="input", selector="#email"),
                  PageElement(tag="button", role="button", selector="#submit", text="Log in")],
    )

    scenarios = provider.generate_scenarios(page, "Login form should validate empty fields")

    assert len(scenarios) == 1
    assert scenarios[0].title == "Empty login shows validation error"
    assert scenarios[0].steps[0].action == "goto"
    assert fake_client.messages.last_kwargs["model"].startswith("claude-")

def test_generate_scenarios_raises_on_invalid_json():
    fake_client = FakeAnthropicClient("not json at all")
    provider = ClaudeProvider(client=fake_client)
    page = PageStructure(url="https://example.com", elements=[])

    with pytest.raises(ValueError, match="invalid AI response"):
        provider.generate_scenarios(page, "anything")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/test_ai_claude_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ai.claude_provider'`

- [ ] **Step 4: Create `backend/app/ai/base.py`**

```python
from abc import ABC, abstractmethod
from app.schemas import PageStructure, GeneratedScenario

class AIProvider(ABC):
    @abstractmethod
    def generate_scenarios(self, page_structure: PageStructure, description: str) -> list[GeneratedScenario]:
        ...
```

- [ ] **Step 5: Create `backend/app/ai/claude_provider.py`**

```python
import json
from pydantic import ValidationError
from app.ai.base import AIProvider
from app.schemas import PageStructure, GeneratedScenario

SYSTEM_PROMPT = (
    "You are a QA engineer. Given a page structure and a description, output a JSON array "
    "of test scenarios. Each scenario has a 'title' and 'steps' (action, selector, value, expected). "
    "Output ONLY the JSON array, no prose."
)

class ClaudeProvider(AIProvider):
    def __init__(self, client, model: str = "claude-sonnet-4-5"):
        self._client = client
        self._model = model

    def generate_scenarios(self, page_structure: PageStructure, description: str) -> list[GeneratedScenario]:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Page structure: {page_structure.model_dump_json()}\nDescription: {description}",
            }],
        )
        raw_text = message.content[0].text
        try:
            parsed = json.loads(raw_text)
            return [GeneratedScenario.model_validate(item) for item in parsed]
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"invalid AI response: {exc}") from exc
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/test_ai_claude_provider.py -v`
Expected: PASS (both tests)

- [ ] **Step 7: Commit**

```bash
cd backend && git add app/schemas.py app/ai/ tests/test_ai_claude_provider.py
git commit -m "feat: add AIProvider interface and Claude adapter"
```

---

### Task 3: Crawler — page structure extraction

**Files:**
- Create: `backend/app/crawler.py`
- Test: `backend/tests/test_crawler.py`
- Create: `backend/tests/fixtures/login_page.html`

**Interfaces:**
- Consumes: `PageStructure`, `PageElement` from `app.schemas` (Task 2).
- Produces: `extract_page_structure(url: str) -> PageStructure` from `app.crawler`.

- [ ] **Step 1: Create the test fixture page**

```html
<!-- backend/tests/fixtures/login_page.html -->
<!DOCTYPE html>
<html>
<body>
  <form id="login-form">
    <input id="email" type="email" name="email" />
    <input id="password" type="password" name="password" />
    <button id="submit" type="submit">Log in</button>
  </form>
  <a href="/forgot-password">Forgot password?</a>
</body>
</html>
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_crawler.py
from pathlib import Path
from app.crawler import extract_page_structure

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "login_page.html").as_uri()

def test_extract_page_structure_finds_inputs_and_buttons():
    structure = extract_page_structure(FIXTURE_URL)

    roles = {el.role for el in structure.elements}
    assert "input" in roles
    assert "button" in roles
    assert "link" in roles

    submit_button = next(el for el in structure.elements if el.selector == "#submit")
    assert submit_button.text == "Log in"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/test_crawler.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.crawler'`

- [ ] **Step 4: Create `backend/app/crawler.py`**

```python
from playwright.sync_api import sync_playwright
from app.schemas import PageStructure, PageElement

_SELECTORS = {
    "input": "input",
    "button": "button, input[type=submit]",
    "link": "a[href]",
    "form": "form",
}

def extract_page_structure(url: str) -> PageStructure:
    elements: list[PageElement] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(url)

        for role, css in _SELECTORS.items():
            for i, handle in enumerate(page.query_selector_all(css)):
                el_id = handle.get_attribute("id")
                selector = f"#{el_id}" if el_id else f"{css} >> nth={i}"
                elements.append(PageElement(
                    tag=handle.evaluate("el => el.tagName.toLowerCase()"),
                    role=role,
                    selector=selector,
                    text=handle.text_content(),
                ))

        browser.close()
    return PageStructure(url=url, elements=elements)
```

- [ ] **Step 5: Install Playwright browser binaries**

Run: `cd backend && playwright install chromium`
Expected: downloads succeed (only needs to run once per machine)

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && pytest tests/test_crawler.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
cd backend && git add app/crawler.py tests/test_crawler.py tests/fixtures/login_page.html
git commit -m "feat: add Playwright-based page structure crawler"
```

---

### Task 4: Runner — scenario execution

**Files:**
- Create: `backend/app/runner.py`
- Test: `backend/tests/test_runner.py`

**Interfaces:**
- Consumes: `ScenarioStep`, `GeneratedScenario` from `app.schemas` (Task 2).
- Produces: `StepResult` (dataclass: `status: str`, `log_message: str`) and `run_scenario(scenario: GeneratedScenario, base_url: str) -> list[StepResult]` from `app.runner`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_runner.py
from pathlib import Path
from app.schemas import GeneratedScenario, ScenarioStep
from app.runner import run_scenario

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "login_page.html").as_uri()

def test_run_scenario_passes_when_expectation_met():
    scenario = GeneratedScenario(
        title="Submit button has correct label",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_text", selector="#submit", expected="Log in"),
        ],
    )

    results = run_scenario(scenario, base_url="")

    assert all(r.status == "passed" for r in results)
    assert len(results) == 2

def test_run_scenario_fails_when_expectation_not_met():
    scenario = GeneratedScenario(
        title="Submit button has wrong label",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_text", selector="#submit", expected="Sign up"),
        ],
    )

    results = run_scenario(scenario, base_url="")

    assert results[-1].status == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.runner'`

- [ ] **Step 3: Create `backend/app/runner.py`**

```python
from dataclasses import dataclass
from playwright.sync_api import sync_playwright
from app.schemas import GeneratedScenario

@dataclass
class StepResult:
    status: str
    log_message: str

def run_scenario(scenario: GeneratedScenario, base_url: str) -> list[StepResult]:
    results: list[StepResult] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            for step in scenario.steps:
                results.append(_run_step(page, step, base_url))
        finally:
            browser.close()
    return results

def _run_step(page, step, base_url: str) -> StepResult:
    try:
        if step.action == "goto":
            page.goto(step.value)
        elif step.action == "click":
            page.click(step.selector)
        elif step.action == "fill":
            page.fill(step.selector, step.value)
        elif step.action == "expect_text":
            actual = page.text_content(step.selector) or ""
            if step.expected not in actual:
                return StepResult(status="failed", log_message=f"expected '{step.expected}' in '{actual}'")
        elif step.action == "expect_url":
            if step.expected not in page.url:
                return StepResult(status="failed", log_message=f"expected url containing '{step.expected}', got '{page.url}'")
        else:
            return StepResult(status="failed", log_message=f"unknown action: {step.action}")
        return StepResult(status="passed", log_message="ok")
    except Exception as exc:
        return StepResult(status="failed", log_message=str(exc))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd backend && git add app/runner.py tests/test_runner.py
git commit -m "feat: add Playwright-based scenario runner"
```

---

### Task 5: API endpoints — projects and scans

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/projects.py`
- Create: `backend/app/api/scans.py`
- Modify: `backend/tests/conftest.py` (add `client` fixture with DB override)
- Test: `backend/tests/test_api_projects.py`
- Test: `backend/tests/test_api_scans.py`

**Interfaces:**
- Consumes: `Base`, `get_session` from `app.db`; `User`, `Project`, `Scan`, `Scenario`, `Run`, `RunStep` from `app.models`; `PageStructure` from `app.schemas`; `extract_page_structure` from `app.crawler`; `AIProvider` from `app.ai.base`.
- Produces: FastAPI `app` object in `app.main`; routes `POST /projects`, `GET /projects`, `POST /projects/{project_id}/scans`, `GET /scans/{scan_id}`.

- [ ] **Step 1: Add `client` fixture to `backend/tests/conftest.py`**

```python
# append to backend/tests/conftest.py
from fastapi.testclient import TestClient
from app.db import Base, get_session
from app.main import app

@pytest.fixture
def client(db_session):
    def override_get_session():
        yield db_session
    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Write the failing tests**

```python
# backend/tests/test_api_projects.py
def test_create_and_list_project(client):
    resp = client.post("/projects", json={"name": "Demo Site", "base_url": "https://example.com"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Demo Site"

    list_resp = client.get("/projects")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1
```

```python
# backend/tests/test_api_scans.py
from unittest.mock import patch
from app.schemas import PageStructure, PageElement, GeneratedScenario, ScenarioStep

def test_create_scan_generates_scenarios(client):
    project = client.post("/projects", json={"name": "Demo", "base_url": "https://example.com"}).json()

    fake_structure = PageStructure(url="https://example.com", elements=[PageElement(tag="button", role="button", selector="#submit", text="Go")])
    fake_scenarios = [GeneratedScenario(title="Click submit", steps=[ScenarioStep(action="click", selector="#submit")])]

    with patch("app.api.scans.extract_page_structure", return_value=fake_structure), \
         patch("app.api.scans.get_ai_provider") as mock_get_provider:
        mock_get_provider.return_value.generate_scenarios.return_value = fake_scenarios
        resp = client.post(f"/projects/{project['id']}/scans", json={
            "target_url": "https://example.com",
            "description": "Check submit button",
        })

    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "ready"
    assert len(body["scenarios"]) == 1
    assert body["scenarios"][0]["title"] == "Click submit"

def test_get_scan_not_found_returns_404(client):
    resp = client.get("/scans/999")
    assert resp.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_api_projects.py tests/test_api_scans.py -v`
Expected: FAIL — `ImportError: cannot import name 'app' from 'app.main'`

- [ ] **Step 4: Create `backend/app/api/projects.py`**

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import Project, User

router = APIRouter()

class ProjectCreate(BaseModel):
    name: str
    base_url: str

class ProjectOut(BaseModel):
    id: int
    name: str
    base_url: str
    model_config = {"from_attributes": True}

def _demo_user(session: Session) -> User:
    user = session.query(User).filter_by(email="demo@testcrafter.local").first()
    if user is None:
        user = User(email="demo@testcrafter.local")
        session.add(user)
        session.flush()
    return user

@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, session: Session = Depends(get_session)):
    user = _demo_user(session)
    project = Project(user_id=user.id, name=payload.name, base_url=payload.base_url)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project

@router.get("/projects", response_model=list[ProjectOut])
def list_projects(session: Session = Depends(get_session)):
    return session.query(Project).all()
```

- [ ] **Step 5: Create `backend/app/api/scans.py`**

```python
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import Scan, Scenario
from app.crawler import extract_page_structure
from app.ai.base import AIProvider

router = APIRouter()

def get_ai_provider() -> AIProvider:
    from app.ai.claude_provider import ClaudeProvider
    import anthropic
    return ClaudeProvider(client=anthropic.Anthropic())

class ScanCreate(BaseModel):
    target_url: str
    description: str

class ScenarioOut(BaseModel):
    id: int
    title: str
    steps_json: str
    model_config = {"from_attributes": True}

class ScanOut(BaseModel):
    id: int
    target_url: str
    status: str
    scenarios: list[ScenarioOut]

@router.post("/projects/{project_id}/scans", response_model=ScanOut, status_code=201)
def create_scan(project_id: int, payload: ScanCreate, session: Session = Depends(get_session)):
    page_structure = extract_page_structure(payload.target_url)
    scan = Scan(
        project_id=project_id,
        target_url=payload.target_url,
        description=payload.description,
        page_structure_json=page_structure.model_dump_json(),
        ai_provider="claude",
        status="analyzing",
    )
    session.add(scan)
    session.flush()

    try:
        provider = get_ai_provider()
        generated = provider.generate_scenarios(page_structure, payload.description)
        for g in generated:
            session.add(Scenario(scan_id=scan.id, title=g.title, steps_json=json.dumps([s.model_dump() for s in g.steps])))
        scan.status = "ready"
    except ValueError:
        scan.status = "failed"

    session.commit()
    session.refresh(scan)
    scenarios = session.query(Scenario).filter_by(scan_id=scan.id).all()
    return ScanOut(id=scan.id, target_url=scan.target_url, status=scan.status, scenarios=scenarios)

@router.get("/scans/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: int, session: Session = Depends(get_session)):
    scan = session.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="scan not found")
    scenarios = session.query(Scenario).filter_by(scan_id=scan.id).all()
    return ScanOut(id=scan.id, target_url=scan.target_url, status=scan.status, scenarios=scenarios)
```

- [ ] **Step 6: Create `backend/app/main.py`**

```python
from fastapi import FastAPI
from app.db import Base, engine
from app.api.projects import router as projects_router
from app.api.scans import router as scans_router

Base.metadata.create_all(engine)

app = FastAPI(title="testcrafter")
app.include_router(projects_router)
app.include_router(scans_router)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_api_projects.py tests/test_api_scans.py -v`
Expected: PASS (all tests)

- [ ] **Step 8: Run the full backend test suite**

Run: `cd backend && pytest -v`
Expected: PASS (all tests from Tasks 1-5)

- [ ] **Step 9: Commit**

```bash
cd backend && git add app/main.py app/api/ tests/conftest.py tests/test_api_projects.py tests/test_api_scans.py
git commit -m "feat: add projects and scans API endpoints"
```

---

### Task 6: Minimal frontend

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.jsx`
- Create: `frontend/src/api.js`
- Create: `frontend/src/App.jsx`

**Interfaces:**
- Consumes: backend REST API from Task 5 (`POST /projects`, `POST /projects/{id}/scans`, `GET /scans/{id}`) via `fetch`.
- Produces: a running Vite dev server at `localhost:5173` showing a form (target URL, description) and a results list.

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "testcrafter-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.1",
    "vite": "^5.4.0"
  }
}
```

- [ ] **Step 2: Create `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>testcrafter</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 3: Create `frontend/src/api.js`**

```javascript
const BASE_URL = "http://localhost:8000";

export async function createProject(name, baseUrl) {
  const res = await fetch(`${BASE_URL}/projects`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, base_url: baseUrl }),
  });
  return res.json();
}

export async function createScan(projectId, targetUrl, description) {
  const res = await fetch(`${BASE_URL}/projects/${projectId}/scans`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_url: targetUrl, description }),
  });
  return res.json();
}
```

- [ ] **Step 4: Create `frontend/src/App.jsx`**

```jsx
import { useState } from "react";
import { createProject, createScan } from "./api";

export default function App() {
  const [url, setUrl] = useState("");
  const [description, setDescription] = useState("");
  const [scan, setScan] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setLoading(true);
    const project = await createProject("Ad-hoc scan", url);
    const result = await createScan(project.id, url, description);
    setScan(result);
    setLoading(false);
  }

  return (
    <div style={{ maxWidth: 640, margin: "2rem auto", fontFamily: "sans-serif" }}>
      <h1>testcrafter</h1>
      <form onSubmit={handleSubmit}>
        <input placeholder="Target URL" value={url} onChange={(e) => setUrl(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <textarea placeholder="What should be tested?" value={description} onChange={(e) => setDescription(e.target.value)} style={{ width: "100%", marginBottom: 8 }} />
        <button type="submit" disabled={loading}>{loading ? "Generating..." : "Generate scenarios"}</button>
      </form>
      {scan && (
        <div>
          <h2>Status: {scan.status}</h2>
          <ul>
            {scan.scenarios.map((s) => (
              <li key={s.id}>{s.title}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Create `frontend/src/main.jsx`**

```jsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 6: Verify the frontend builds**

Run: `cd frontend && npm install && npm run build`
Expected: build succeeds with no errors

- [ ] **Step 7: Commit**

```bash
cd frontend && git add package.json index.html src/
git commit -m "feat: add minimal frontend to trigger scans and view scenarios"
```

---

### Task 7: Docker Compose wiring

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `docker-compose.yml`

**Interfaces:**
- Consumes: `backend/app/main.py` (Task 5), `frontend` Vite project (Task 6).
- Produces: `docker-compose up` starting backend on port 8000 and frontend on port 5173.

- [ ] **Step 1: Create `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" && playwright install --with-deps chromium
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create `frontend/Dockerfile`**

```dockerfile
FROM node:20-slim
WORKDIR /app
COPY package.json .
RUN npm install
COPY . .
CMD ["npm", "run", "dev", "--", "--host"]
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ./backend:/app

  frontend:
    build: ./frontend
    ports:
      - "5173:5173"
    depends_on:
      - backend
    volumes:
      - ./frontend:/app
```

- [ ] **Step 4: Verify the stack starts**

Run: `docker compose up --build -d && docker compose ps`
Expected: both `backend` and `frontend` services show `running`/`Up`

- [ ] **Step 5: Tear down**

Run: `docker compose down`

- [ ] **Step 6: Commit**

```bash
git add backend/Dockerfile frontend/Dockerfile docker-compose.yml
git commit -m "feat: add Docker Compose setup for local development"
```

---

### Task 8: Documentation set

**Files:**
- Create: `README.md`
- Create: `README.tr.md`
- Create: `CONTRIBUTING.md`
- Create: `LICENSE`
- Create: `docs/api-spec.md`
- Create: `docs/ai-provider-interface.md`
- Create: `docs/data-model.md`

**Interfaces:**
- Consumes: `docs/architecture.md` (existing), the API routes from Task 5 (`POST /projects`, `GET /projects`, `POST /projects/{project_id}/scans`, `GET /scans/{scan_id}`), the models from Task 1, and the `AIProvider` contract from Task 2.
- Produces: no code — this task has no downstream code consumers, only human-facing docs.

This task has no tests to run; "verification" means reading each file back and checking it renders correctly and matches the actual API/schema from Tasks 1, 2, and 5.

- [ ] **Step 1: Create `LICENSE`**

Use the standard MIT license text, copyright line `Copyright (c) 2026 Efecan Cengiz`.

```
MIT License

Copyright (c) 2026 Efecan Cengiz

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Create `docs/data-model.md`**

```markdown
# Data Model

ER diagram and column reference for the SQLAlchemy models in `backend/app/models.py`.

## Entity-Relationship Diagram

\`\`\`
User 1──N Project 1──N Scan 1──N Scenario 1──N Run 1──N RunStep
\`\`\`

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
```

- [ ] **Step 3: Create `docs/ai-provider-interface.md`**

```markdown
# AIProvider Interface

## Contract

\`\`\`python
class AIProvider(ABC):
    @abstractmethod
    def generate_scenarios(self, page_structure: PageStructure, description: str) -> list[GeneratedScenario]:
        ...
\`\`\`

Defined in `backend/app/ai/base.py`. `PageStructure`, `GeneratedScenario`, and `ScenarioStep` are Pydantic models in `backend/app/schemas.py`.

- `generate_scenarios` must return already-validated `GeneratedScenario` objects, or raise `ValueError` if the underlying model's output can't be parsed into that schema. Callers (see `backend/app/api/scans.py`) treat a `ValueError` as a scan failure (`status = "failed"`), not a crash.
- Implementations own their own prompt construction and response parsing; the interface only constrains the boundary.

## Adding a new provider

1. Create `backend/app/ai/<name>_provider.py` with a class implementing `AIProvider`.
2. Write `backend/tests/test_ai_<name>_provider.py` following the pattern in `test_ai_claude_provider.py` — fake the underlying SDK client, assert on parsed output and on the invalid-JSON error path.
3. Wire it into `get_ai_provider()` in `backend/app/api/scans.py` (currently hardcoded to Claude; will need a `.env`-driven switch once more than one provider exists).

## Existing adapters

- `ClaudeProvider` (`backend/app/ai/claude_provider.py`) — uses the `anthropic` SDK's `messages.create`, expects a JSON array as the entire response text (see `SYSTEM_PROMPT` in that file).
```

- [ ] **Step 4: Create `docs/api-spec.md`**

```markdown
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
```

- [ ] **Step 5: Create `CONTRIBUTING.md`**

```markdown
# Contributing

## Setup

\`\`\`bash
cd backend && pip install -e ".[dev]" && playwright install chromium
cd frontend && npm install
\`\`\`

Or via Docker: `docker compose up --build`.

## Running tests

\`\`\`bash
cd backend && pytest -v
\`\`\`

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
```

- [ ] **Step 6: Create `README.md`**

```markdown
# testcrafter

AI-powered test scenario generator + automated runner. Give it a URL and a short description of what to test — it crawls the page, asks an AI provider to generate test scenarios, runs them with Playwright, and shows pass/fail results with screenshots.

🇹🇷 [Türkçe](README.tr.md)

## Why

A single project demonstrating backend API design, AI integration, and QA test automation together. See `docs/architecture.md` for the full design rationale.

## Stack

FastAPI · SQLAlchemy · SQLite · Playwright · React (Vite) · Claude API (pluggable AI provider layer)

## Quick start

\`\`\`bash
git clone <repo-url>
cd testcrafter
cp .env.example .env   # add your ANTHROPIC_API_KEY
docker compose up --build
\`\`\`

Backend: http://localhost:8000 (docs at `/docs`)
Frontend: http://localhost:5173

## Documentation

- [Architecture](docs/architecture.md)
- [API spec](docs/api-spec.md)
- [AI provider interface](docs/ai-provider-interface.md)
- [Data model](docs/data-model.md)
- [Contributing](CONTRIBUTING.md)

## License

MIT — see [LICENSE](LICENSE)
```

- [ ] **Step 7: Create `README.tr.md`**

```markdown
# testcrafter

AI destekli test senaryosu üretici + otomatik çalıştırıcı. Bir URL ve kısa bir test açıklaması ver — sayfayı tarar, bir AI sağlayıcısına test senaryoları ürettirir, Playwright ile çalıştırır, pass/fail sonuçlarını ekran görüntüleriyle gösterir.

🇬🇧 [English](README.md)

## Neden

Backend API tasarımı, AI entegrasyonu ve QA test otomasyonunu tek bir projede bir araya getiren bir çalışma. Tam tasarım gerekçesi için `docs/architecture.md`.

## Stack

FastAPI · SQLAlchemy · SQLite · Playwright · React (Vite) · Claude API (değiştirilebilir AI sağlayıcı katmanı)

## Hızlı başlangıç

\`\`\`bash
git clone <repo-url>
cd testcrafter
cp .env.example .env   # ANTHROPIC_API_KEY ekle
docker compose up --build
\`\`\`

Backend: http://localhost:8000 (dokümantasyon `/docs`)
Frontend: http://localhost:5173

## Dokümantasyon

- [Mimari](docs/architecture.md)
- [API spec](docs/api-spec.md)
- [AI sağlayıcı arayüzü](docs/ai-provider-interface.md)
- [Veri modeli](docs/data-model.md)
- [Katkı rehberi](CONTRIBUTING.md)

## Lisans

MIT — bkz. [LICENSE](LICENSE)
```

- [ ] **Step 8: Read each created file back and cross-check against the actual routes/schema**

Confirm: `docs/api-spec.md` endpoint list matches the routes registered in `backend/app/main.py` (Task 5); `docs/data-model.md` columns match `backend/app/models.py` (Task 1) exactly; `docs/ai-provider-interface.md` method signature matches `backend/app/ai/base.py` (Task 2). Fix any drift found.

- [ ] **Step 9: Commit**

```bash
git add README.md README.tr.md CONTRIBUTING.md LICENSE docs/api-spec.md docs/ai-provider-interface.md docs/data-model.md
git commit -m "docs: add README (EN/TR), CONTRIBUTING, LICENSE, and API/data-model docs"
```

---

## Not Covered By This Plan

- Gemini/DeepSeek/Qwen adapters — follow the same pattern as `ClaudeProvider` (Task 2) once the Claude path is proven.
- E2E Playwright test of the dashboard's own flow, and GitHub Actions CI — follow-up plan once the frontend loop is manually verified.
