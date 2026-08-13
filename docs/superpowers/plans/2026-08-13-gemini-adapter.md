# Gemini Adapter + Provider Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `GeminiProvider` implementing `AIProvider`, and make `get_ai_provider()` select Claude or Gemini via a new `AI_PROVIDER` env var (defaulting to `claude`, so existing deployments are unaffected).

**Architecture:** `GeminiProvider` mirrors `ClaudeProvider` (`backend/app/ai/claude_provider.py`) exactly — same `SYSTEM_PROMPT`, same JSON-array-response contract, same `ValueError`-on-invalid-output behavior. `get_ai_provider()` in `backend/app/api/scans.py` becomes a small dispatcher keyed on `os.getenv("AI_PROVIDER", "claude")`.

**Tech Stack:** `google-genai` SDK (Google's current official Python SDK), model `gemini-2.5-flash`.

## Global Constraints

- Default `AI_PROVIDER` is `"claude"` — no behavior change when the env var is unset.
- `GeminiProvider.generate_scenarios` must raise `ValueError` (not a provider-specific exception) on unparseable/invalid output — this is what `create_scan` already catches.
- Follow existing repo conventions: no comments except non-obvious WHY, no speculative abstractions.
- Never add a "Co-Authored-By: Claude" (or any AI attribution) trailer to commits — hard rule for this repo.

---

## Task 1: GeminiProvider

**Files:**
- Create: `backend/app/ai/gemini_provider.py`
- Test: `backend/tests/test_ai_gemini_provider.py`
- Modify: `backend/pyproject.toml` (add `google-genai` dependency)

**Interfaces:**
- Consumes: `AIProvider` (`backend/app/ai/base.py`), `PageStructure` / `GeneratedScenario` (`backend/app/schemas.py`) — all pre-existing, unchanged.
- Produces: `GeminiProvider(client, model="gemini-2.5-flash")` with `.generate_scenarios(page_structure, description) -> list[GeneratedScenario]`, importable as `from app.ai.gemini_provider import GeminiProvider`. Task 2 imports this class by this exact path.

- [ ] **Step 1: Add the `google-genai` dependency**

Edit `backend/pyproject.toml`, add to `dependencies`:

```toml
    "google-genai>=1.0",
```

- [ ] **Step 2: Install it**

Run: `cd backend && pip install -e ".[dev]"`
Expected: installs successfully, no errors.

- [ ] **Step 3: Write the failing tests**

Create `backend/tests/test_ai_gemini_provider.py`:

```python
import json
import pytest
from app.ai.gemini_provider import GeminiProvider
from app.schemas import PageStructure, PageElement


class FakeResponse:
    def __init__(self, text: str):
        self.text = text


class FakeModelsAPI:
    def __init__(self, response_text: str):
        self._response_text = response_text
        self.last_kwargs = None

    def generate_content(self, **kwargs):
        self.last_kwargs = kwargs
        return FakeResponse(self._response_text)


class FakeGenaiClient:
    def __init__(self, response_text: str):
        self.models = FakeModelsAPI(response_text)


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
    fake_client = FakeGenaiClient(payload)
    provider = GeminiProvider(client=fake_client)
    page = PageStructure(
        url="https://example.com/login",
        elements=[PageElement(tag="input", role="input", selector="#email"),
                  PageElement(tag="button", role="button", selector="#submit", text="Log in")],
    )

    scenarios = provider.generate_scenarios(page, "Login form should validate empty fields")

    assert len(scenarios) == 1
    assert scenarios[0].title == "Empty login shows validation error"
    assert scenarios[0].steps[0].action == "goto"
    assert fake_client.models.last_kwargs["model"].startswith("gemini-")


def test_generate_scenarios_raises_on_invalid_json():
    fake_client = FakeGenaiClient("not json at all")
    provider = GeminiProvider(client=fake_client)
    page = PageStructure(url="https://example.com", elements=[])

    with pytest.raises(ValueError, match="invalid AI response"):
        provider.generate_scenarios(page, "anything")
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_ai_gemini_provider.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.ai.gemini_provider'`

- [ ] **Step 5: Implement GeminiProvider**

Create `backend/app/ai/gemini_provider.py`:

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


class GeminiProvider(AIProvider):
    def __init__(self, client, model: str = "gemini-2.5-flash"):
        self._client = client
        self._model = model

    def generate_scenarios(self, page_structure: PageStructure, description: str) -> list[GeneratedScenario]:
        response = self._client.models.generate_content(
            model=self._model,
            contents=(
                f"{SYSTEM_PROMPT}\n\n"
                f"Page structure: {page_structure.model_dump_json()}\nDescription: {description}"
            ),
        )
        raw_text = response.text
        try:
            parsed = json.loads(raw_text)
            return [GeneratedScenario.model_validate(item) for item in parsed]
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"invalid AI response: {exc}") from exc
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_ai_gemini_provider.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit**

```bash
git add backend/app/ai/gemini_provider.py backend/tests/test_ai_gemini_provider.py backend/pyproject.toml
git commit -m "feat: add GeminiProvider implementing AIProvider"
```

---

## Task 2: Provider selection via AI_PROVIDER env var

**Files:**
- Modify: `backend/app/api/scans.py:18-21` (`get_ai_provider`), `backend/app/api/scans.py:62` (hardcoded `ai_provider="claude"`)
- Modify: `backend/tests/test_api_scans.py` (add provider-switch tests)
- Modify: `.env.example`

**Interfaces:**
- Consumes: `GeminiProvider` from Task 1 (`app.ai.gemini_provider.GeminiProvider`), `ClaudeProvider` (pre-existing, `app.ai.claude_provider.ClaudeProvider`).
- Produces: `get_ai_provider()` (unchanged signature: `() -> AIProvider`), now reading `AI_PROVIDER` from the environment. No other task depends on new symbols from this task.

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_api_scans.py` (new imports at top: `import os`, `from unittest.mock import patch as mock_patch` is unnecessary — `patch` is already imported via `from unittest.mock import patch`):

```python
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

Add `import pytest` to the top of `backend/tests/test_api_scans.py` if not already present (it is not, per the current file).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_api_scans.py -v -k get_ai_provider`
Expected: FAIL — `test_get_ai_provider_selects_gemini` and `test_get_ai_provider_rejects_unknown_value` fail because `get_ai_provider` doesn't yet branch on `AI_PROVIDER`.

- [ ] **Step 3: Implement the provider switch**

In `backend/app/api/scans.py`, replace:

```python
def get_ai_provider() -> AIProvider:
    from app.ai.claude_provider import ClaudeProvider
    import anthropic
    return ClaudeProvider(client=anthropic.Anthropic())
```

with:

```python
def get_ai_provider() -> AIProvider:
    provider_name = os.getenv("AI_PROVIDER", "claude")
    if provider_name == "claude":
        from app.ai.claude_provider import ClaudeProvider
        import anthropic
        return ClaudeProvider(client=anthropic.Anthropic())
    if provider_name == "gemini":
        from app.ai.gemini_provider import GeminiProvider
        from google import genai
        return GeminiProvider(client=genai.Client())
    raise ValueError(f"unknown AI_PROVIDER: {provider_name}")
```

Add `import os` to the top of `backend/app/api/scans.py` (not currently imported).

Then, in `create_scan`, replace the hardcoded:

```python
        ai_provider="claude",
```

with:

```python
        ai_provider=os.getenv("AI_PROVIDER", "claude"),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_api_scans.py -v`
Expected: PASS (all tests in the file, including the 3 new ones and the pre-existing ones — `test_create_scan_marks_failed_when_ai_provider_not_configured` still passes because `get_ai_provider` still raises on `anthropic.Anthropic()` construction failure via the default `"claude"` branch)

- [ ] **Step 5: Update `.env.example`**

Edit `.env.example`, change:

```
ANTHROPIC_API_KEY=
```

to:

```
AI_PROVIDER=claude
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
```

- [ ] **Step 6: Run the full backend test suite**

Run: `cd backend && pytest -v`
Expected: PASS, all tests green (no regressions in other test files).

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/scans.py backend/tests/test_api_scans.py .env.example
git commit -m "feat: select AI provider via AI_PROVIDER env var"
```

---

## Task 3: Documentation updates

**Files:**
- Modify: `docs/ai-provider-interface.md`
- Modify: `README.md`
- Modify: `README.tr.md`

**Interfaces:**
- Consumes: nothing code-level — documentation only, reflecting Tasks 1-2's finished behavior.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Update `docs/ai-provider-interface.md`**

In the "Adding a new provider" section, replace step 3's text:

```
3. Wire it into `get_ai_provider()` in `backend/app/api/scans.py` (currently hardcoded to Claude; will need a `.env`-driven switch once more than one provider exists).
```

with:

```
3. Add a branch for it in `get_ai_provider()` in `backend/app/api/scans.py`, keyed on the `AI_PROVIDER` env var.
```

In the "Existing adapters" section, add below the `ClaudeProvider` bullet:

```
- `GeminiProvider` (`backend/app/ai/gemini_provider.py`) — uses the `google-genai` SDK's `client.models.generate_content`, expects a JSON array as the entire response text (same `SYSTEM_PROMPT` pattern as `ClaudeProvider`).
```

Add a new section at the end of the file:

```markdown
## Selecting the active provider

Set `AI_PROVIDER` in `.env` to `claude` (default) or `gemini`. `get_ai_provider()` in `backend/app/api/scans.py` reads this at request time — no restart needed to pick up a changed value, since it's read fresh on every call. An unrecognized value raises `ValueError`, which `create_scan` treats as a scan failure like any other AI-provider error.
```

- [ ] **Step 2: Update `README.md`**

Change line 13:

```
FastAPI · SQLAlchemy · SQLite · Playwright · React (Vite) · Claude API (pluggable AI provider layer)
```

to:

```
FastAPI · SQLAlchemy · SQLite · Playwright · React (Vite) · Claude / Gemini (pluggable AI provider layer)
```

Change line 20:

```
cp .env.example .env   # add your ANTHROPIC_API_KEY
```

to:

```
cp .env.example .env   # set AI_PROVIDER and add the matching API key (ANTHROPIC_API_KEY or GEMINI_API_KEY)
```

- [ ] **Step 3: Update `README.tr.md`**

Read `README.tr.md` first to find the corresponding lines (mirrors of the two lines above), and apply the equivalent Turkish-language edits — same content change, same meaning, translated.

- [ ] **Step 4: Commit**

```bash
git add docs/ai-provider-interface.md README.md README.tr.md
git commit -m "docs: document Gemini adapter and AI_PROVIDER selection"
```
