# Runner Action-Vocabulary Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop AI-generated scenarios from failing at the step level due to action-name mismatches. Extract a shared, action-constrained `SYSTEM_PROMPT` into `backend/app/ai/prompts.py`; add synonym normalization in the runner as a defense-in-depth layer; add a genuinely new `expect_visible` action the runner didn't support before.

**Architecture:** `backend/app/ai/prompts.py` becomes the single source of the prompt text both AI adapters send; `backend/app/runner.py` gains a `_normalize_action` helper called before action dispatch, plus a new `expect_visible` branch using Playwright's `page.is_visible()`.

**Tech Stack:** No new dependencies — pure Python/Playwright, existing test patterns.

## Global Constraints

- `ScenarioStep.action` stays a plain `str` — no `Literal` type, no schema-level rejection of unrecognized actions (normalization happens at the runner layer, not validation).
- An action that's neither a canonical name nor a known synonym still fails with `"unknown action: {step.action}"` — normalization tolerates known variants, it doesn't silently swallow everything.
- Follow existing repo conventions: no comments except non-obvious WHY, no speculative abstractions.
- Never add a "Co-Authored-By: Claude" (or any AI attribution) trailer to commits — hard rule for this repo.
- No new action types beyond `expect_visible` — don't speculatively add more.

---

## Task 1: Extract shared `SYSTEM_PROMPT` with explicit action list

**Files:**
- Create: `backend/app/ai/prompts.py`
- Modify: `backend/app/ai/claude_provider.py`
- Modify: `backend/app/ai/gemini_provider.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `SYSTEM_PROMPT: str` importable as `from app.ai.prompts import SYSTEM_PROMPT`. Task 2's runner changes don't consume this (runner doesn't touch the prompt), but the prompt's action list must stay in sync with what Task 2 implements — both list exactly these six actions: `goto`, `click`, `fill`, `expect_text`, `expect_url`, `expect_visible`.

- [ ] **Step 1: Create the shared prompt module**

Create `backend/app/ai/prompts.py`:

```python
SYSTEM_PROMPT = (
    "You are a QA engineer. Given a page structure and a description, output a JSON array "
    "of test scenarios. Each scenario has a 'title' and 'steps'.\n\n"
    "Each step has an 'action' field, which MUST be exactly one of these six values "
    "(no others are supported):\n"
    "- goto: navigate to a URL (value = target URL)\n"
    "- click: click an element (selector)\n"
    "- fill: type text into an input (selector, value)\n"
    "- expect_text: assert an element's text contains a substring (selector, expected)\n"
    "- expect_url: assert the current URL contains a substring (expected)\n"
    "- expect_visible: assert an element is visible on the page (selector)\n\n"
    "Output ONLY the JSON array, no prose."
)
```

- [ ] **Step 2: Update `claude_provider.py` to import the shared prompt**

In `backend/app/ai/claude_provider.py`, replace:

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
```

with:

```python
import json

from pydantic import ValidationError

from app.ai.base import AIProvider
from app.ai.prompts import SYSTEM_PROMPT
from app.schemas import PageStructure, GeneratedScenario
```

(the rest of the file — the `ClaudeProvider` class — is unchanged).

- [ ] **Step 3: Update `gemini_provider.py` to import the shared prompt**

In `backend/app/ai/gemini_provider.py`, replace:

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
```

with:

```python
import json

from pydantic import ValidationError

from app.ai.base import AIProvider
from app.ai.prompts import SYSTEM_PROMPT
from app.schemas import PageStructure, GeneratedScenario
```

(the rest of the file — the `GeminiProvider` class — is unchanged).

- [ ] **Step 4: Run the existing AI-provider tests to confirm no regression**

Run: `cd backend && python -m pytest tests/test_ai_claude_provider.py tests/test_ai_gemini_provider.py -v`
Expected: PASS (4 passed) — neither test file imports or asserts on `SYSTEM_PROMPT` directly, both only exercise `generate_scenarios`, so this is a pure refactor with no test changes needed.

- [ ] **Step 5: Run the full backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 6: Commit**

```bash
git add backend/app/ai/prompts.py backend/app/ai/claude_provider.py backend/app/ai/gemini_provider.py
git commit -m "refactor: extract shared SYSTEM_PROMPT with explicit action list"
```

---

## Task 2: Runner — action-synonym normalization and `expect_visible`

**Files:**
- Modify: `backend/app/runner.py`
- Modify: `backend/app/schemas.py` (comment only)
- Modify: `backend/tests/fixtures/login_page.html`
- Modify: `backend/tests/test_runner.py`

**Interfaces:**
- Consumes: nothing from Task 1 (independent change to a different layer).
- Produces: `_normalize_action(action: str) -> str` (module-private in `runner.py`, not imported elsewhere) and the new `"expect_visible"` action value now accepted by `_run_step`. No other task consumes new symbols from this task — it's the final task in this plan.

- [ ] **Step 1: Add a hidden element to the test fixture for visibility testing**

Modify `backend/tests/fixtures/login_page.html` — add a `hidden` element so tests can assert both visible and not-visible cases. Replace the full file contents:

```html
<!DOCTYPE html>
<html>
<body>
  <form id="login-form">
    <input id="email" type="email" name="email" />
    <input id="password" type="password" name="password" />
    <button id="submit" type="submit">Log in</button>
  </form>
  <a href="/forgot-password">Forgot password?</a>
  <div id="hidden-banner" style="display: none;">You should not see this</div>
</body>
</html>
```

- [ ] **Step 2: Write the failing tests**

Add to `backend/tests/test_runner.py` (after the existing tests, before nothing — append at the end of the file):

```python
def test_run_scenario_expect_visible_passes_for_visible_element(tmp_path):
    scenario = GeneratedScenario(
        title="Submit button is visible",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_visible", selector="#submit"),
        ],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert results[-1].status == "passed"

def test_run_scenario_expect_visible_fails_for_hidden_element(tmp_path):
    scenario = GeneratedScenario(
        title="Hidden banner is not visible",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_visible", selector="#hidden-banner"),
        ],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert results[-1].status == "failed"
    assert "not visible" in results[-1].log_message

def test_run_scenario_normalizes_known_action_synonyms(tmp_path):
    scenario = GeneratedScenario(
        title="Synonym actions resolve correctly",
        steps=[
            ScenarioStep(action="navigate", value=FIXTURE_URL),
            ScenarioStep(action="assertVisibility", selector="#submit"),
            ScenarioStep(action="assert_text", selector="#submit", expected="Log in"),
            ScenarioStep(action="assertUrl", expected="login_page"),
        ],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert all(r.status == "passed" for r in results)

def test_run_scenario_fails_for_genuinely_unknown_action(tmp_path):
    scenario = GeneratedScenario(
        title="Unrecognized action",
        steps=[ScenarioStep(action="do_a_backflip", selector="#submit")],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert results[0].status == "failed"
    assert "unknown action" in results[0].log_message
```

Also add `ScenarioStep` to the existing import line at the top of the file if not already present (it already is, per the current file's `from app.schemas import GeneratedScenario, ScenarioStep` — verify before editing, don't duplicate).

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_runner.py -v`
Expected: FAIL — the 4 new tests fail (`expect_visible`/synonym actions all currently fall into the `else` branch and produce `"unknown action: ..."`, so `status == "passed"` assertions fail; the "genuinely unknown action" test may already pass by coincidence since that behavior already exists — check its actual result, it should already be green even before Task 2's implementation, confirming the baseline).

- [ ] **Step 4: Implement normalization and `expect_visible` in `runner.py`**

Replace the full contents of `backend/app/runner.py`:

```python
import logging
from dataclasses import dataclass
from pathlib import Path
from playwright.sync_api import sync_playwright
from app.schemas import GeneratedScenario

logger = logging.getLogger(__name__)

_ACTION_SYNONYMS = {
    "navigate": "goto",
    "visit": "goto",
    "open": "goto",
    "tap": "click",
    "press": "click",
    "type": "fill",
    "input": "fill",
    "enter_text": "fill",
    "assert_text": "expect_text",
    "asserttext": "expect_text",
    "check_text": "expect_text",
    "assert_url": "expect_url",
    "asserturl": "expect_url",
    "assertvisibility": "expect_visible",
    "assert_visible": "expect_visible",
    "checkvisibility": "expect_visible",
}

@dataclass
class StepResult:
    status: str
    log_message: str
    screenshot_path: str | None = None

def run_scenario(scenario: GeneratedScenario, base_url: str, screenshot_dir: Path) -> list[StepResult]:
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    results: list[StepResult] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            for index, step in enumerate(scenario.steps):
                results.append(_run_step(page, step, base_url, screenshot_dir, index))
        finally:
            browser.close()
    return results

def _normalize_action(action: str) -> str:
    return _ACTION_SYNONYMS.get(action.lower(), action)

def _run_step(page, step, base_url: str, screenshot_dir: Path, step_index: int) -> StepResult:
    action = _normalize_action(step.action)
    try:
        if action == "goto":
            page.goto(step.value)
        elif action == "click":
            page.click(step.selector)
        elif action == "fill":
            page.fill(step.selector, step.value)
        elif action == "expect_text":
            actual = page.text_content(step.selector) or ""
            if step.expected not in actual:
                return _finish(page, screenshot_dir, step_index, "failed", f"expected '{step.expected}' in '{actual}'")
        elif action == "expect_url":
            if step.expected not in page.url:
                return _finish(page, screenshot_dir, step_index, "failed", f"expected url containing '{step.expected}', got '{page.url}'")
        elif action == "expect_visible":
            if not page.is_visible(step.selector):
                return _finish(page, screenshot_dir, step_index, "failed", f"element '{step.selector}' is not visible")
        else:
            return _finish(page, screenshot_dir, step_index, "failed", f"unknown action: {step.action}")
        return _finish(page, screenshot_dir, step_index, "passed", "ok")
    except Exception as exc:
        return _finish(page, screenshot_dir, step_index, "failed", str(exc))

def _finish(page, screenshot_dir: Path, step_index: int, status: str, log_message: str) -> StepResult:
    screenshot_path = screenshot_dir / f"{step_index}.png"
    try:
        page.screenshot(path=screenshot_path)
        captured_path = str(screenshot_path)
    except Exception:
        logger.exception("screenshot capture failed for step %d", step_index)
        captured_path = None
    return StepResult(status=status, log_message=log_message, screenshot_path=captured_path)
```

- [ ] **Step 5: Update the `ScenarioStep.action` comment in `schemas.py`**

In `backend/app/schemas.py`, change:

```python
    action: str      # "click" | "fill" | "goto" | "expect_text" | "expect_url"
```

to:

```python
    action: str      # "click" | "fill" | "goto" | "expect_text" | "expect_url" | "expect_visible"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_runner.py -v`
Expected: PASS (all tests in the file, including the 4 new ones).

- [ ] **Step 7: Run the full backend test suite**

Run: `cd backend && python -m pytest -v`
Expected: PASS, no regressions.

- [ ] **Step 8: Commit**

```bash
git add backend/app/runner.py backend/app/schemas.py backend/tests/fixtures/login_page.html backend/tests/test_runner.py
git commit -m "feat: normalize action synonyms and add expect_visible to the runner"
```

---

## Task 3: Documentation

**Files:**
- Modify: `docs/ai-provider-interface.md`

**Interfaces:**
- Consumes: nothing code-level — documentation only, reflecting Tasks 1-2's finished behavior.
- Produces: nothing consumed by later tasks (final task in this plan).

- [ ] **Step 1: Update `docs/ai-provider-interface.md`**

Replace the "Existing adapters" section's two bullets:

```
- `ClaudeProvider` (`backend/app/ai/claude_provider.py`) — uses the `anthropic` SDK's `messages.create`, expects a JSON array as the entire response text (see `SYSTEM_PROMPT` in that file).
- `GeminiProvider` (`backend/app/ai/gemini_provider.py`) — uses the `google-genai` SDK's `client.models.generate_content`, expects a JSON array as the entire response text (same `SYSTEM_PROMPT` pattern as `ClaudeProvider`).
```

with:

```
- `ClaudeProvider` (`backend/app/ai/claude_provider.py`) — uses the `anthropic` SDK's `messages.create`, expects a JSON array as the entire response text.
- `GeminiProvider` (`backend/app/ai/gemini_provider.py`) — uses the `google-genai` SDK's `client.models.generate_content`, expects a JSON array as the entire response text.

Both share the same `SYSTEM_PROMPT`, defined once in `backend/app/ai/prompts.py`.
```

Add a new section at the end of the file:

```markdown
## Supported scenario actions

The single source of truth for what a generated scenario's `action` field can be is what `backend/app/runner.py`'s `_run_step` actually implements — this list mirrors it, keep both in sync:

- `goto` — navigate to a URL (`value`)
- `click` — click an element (`selector`)
- `fill` — type text into an input (`selector`, `value`)
- `expect_text` — assert an element's text contains a substring (`selector`, `expected`)
- `expect_url` — assert the current URL contains a substring (`expected`)
- `expect_visible` — assert an element is visible on the page (`selector`)

`SYSTEM_PROMPT` (`backend/app/ai/prompts.py`) enumerates exactly these six actions to the AI provider. The runner also normalizes a handful of common synonyms (e.g. `navigate` → `goto`, `assertVisibility` → `expect_visible`) as a tolerance layer — see `_ACTION_SYNONYMS` in `runner.py` — but an action outside both the canonical list and the synonym table still fails that step with `"unknown action: ..."` rather than being silently accepted.
```

- [ ] **Step 2: Commit**

```bash
git add docs/ai-provider-interface.md
git commit -m "docs: document supported scenario actions and prompt sharing"
```
