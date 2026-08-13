# Runner Action-Vocabulary Fix — Design Spec

**Date:** 2026-08-13
**Status:** Approved

## 1. Overview

Fix a real, repeatedly-observed bug: AI providers generate scenario `action` values (e.g. `navigate`, `assertVisibility`) that don't match the Playwright runner's actually-implemented action vocabulary (`goto`, `click`, `fill`, `expect_text`, `expect_url`), so real scans consistently fail at the step level even though the rest of the pipeline (crawl, AI generation, screenshot capture) works correctly. Flagged repeatedly across the last two shipped features (screenshot capture, auth system) as a pre-existing, unrelated issue — this is its dedicated fix.

## 2. Root Cause

`SYSTEM_PROMPT` (duplicated identically in `backend/app/ai/claude_provider.py` and `backend/app/ai/gemini_provider.py`) tells the model to produce "steps (action, selector, value, expected)" without ever enumerating which `action` values are actually valid. The model reasonably invents plausible-sounding alternatives (`navigate` instead of `goto`, `assertVisibility` for a capability the runner doesn't have at all).

## 3. Components

### `backend/app/ai/prompts.py` (new module)

`SYSTEM_PROMPT` is extracted here (previously duplicated verbatim in both provider files — deferred at "only 2 providers" in earlier reviews, but now that the prompt is being meaningfully expanded with an explicit action list, keeping it in sync by hand across two files is a real risk worth removing). New content explicitly enumerates the six supported actions and which fields each uses:

```
- goto: navigate to a URL (value = target URL)
- click: click an element (selector)
- fill: type text into an input (selector, value)
- expect_text: assert an element's text contains a substring (selector, expected)
- expect_url: assert the current URL contains a substring (expected)
- expect_visible: assert an element is visible on the page (selector)
```

Plus an explicit instruction: output ONLY these six action names, nothing else.

Both `backend/app/ai/claude_provider.py` and `backend/app/ai/gemini_provider.py` import `SYSTEM_PROMPT` from this module instead of defining their own copy.

### `backend/app/runner.py` — synonym normalization (defense in depth)

A new `_normalize_action(action: str) -> str` function, called at the top of `_run_step` before the `if/elif` chain, case-insensitively maps common synonyms to the canonical action name:

| Synonym (any case) | Canonical |
|---|---|
| `navigate`, `visit`, `open` | `goto` |
| `tap`, `press` | `click` |
| `type`, `input`, `enter_text` | `fill` |
| `assert_text`, `assertText`, `check_text` | `expect_text` |
| `assert_url`, `assertUrl` | `expect_url` |
| `assertVisibility`, `assert_visible`, `checkVisibility` | `expect_visible` |

Anything not in this table (including the canonical names themselves) passes through unchanged. An action that's neither a canonical name nor a known synonym still falls through to the existing `"unknown action: {step.action}"` failure — this is a tolerance layer for known variants, not a silent catch-all.

### `backend/app/runner.py` — new `expect_visible` action

A new branch in `_run_step`, alongside `expect_text`/`expect_url`:

```python
elif step.action == "expect_visible":
    if not page.is_visible(step.selector):
        return _finish(page, screenshot_dir, step_index, "failed", f"element '{step.selector}' is not visible")
```

Uses Playwright's `page.is_visible()`. Consistent with the existing pattern: a failed assertion is a normal `"failed"` `StepResult`, not an exception.

### `backend/app/schemas.py`

`ScenarioStep.action`'s inline comment (currently `# "click" | "fill" | "goto" | "expect_text" | "expect_url"`) is updated to include `expect_visible`. The field stays a plain `str` (not a `Literal`) — normalization happens at the runner layer, not schema validation, so a scan isn't rejected for a synonym that the runner can still handle.

## 4. Testing

- `backend/tests/test_runner.py`: add tests for `expect_visible` (pass when element visible, fail with a clear message when not — using the existing `login_page.html` fixture or a small addition to it if needed), a test proving each synonym in the table normalizes to its canonical action and executes correctly, and a regression test confirming a genuinely unknown action (not in the table) still produces the `"unknown action: ..."` failure.
- `backend/tests/test_ai_claude_provider.py` / `test_ai_gemini_provider.py`: update the `SYSTEM_PROMPT` import to come from `app.ai.prompts` instead of the provider module (both files reference `SYSTEM_PROMPT` in their fake-client assertions/setup — check each file's actual usage before editing).

## 5. Documentation

- `docs/ai-provider-interface.md`: add a "Supported scenario actions" section — the single source of truth for what `runner.py` actually executes, referencing `backend/app/runner.py` rather than re-explaining the prompt's wording. Update the "Existing adapters" bullets to mention `app.ai.prompts.SYSTEM_PROMPT` as the shared source instead of implying each adapter defines its own.

## 6. Out of Scope

- Converting `ScenarioStep.action` to a `Literal` type / strict schema-level rejection of unknown actions (deliberately rejected in brainstorming — normalization at the runner layer was preferred so synonyms don't cause a scan-level failure).
- Any other new action types beyond `expect_visible` — no other capability gap has been observed in practice; add more only when a real gap is seen, not speculatively.
- Retrying/regenerating a scenario when the AI produces an unrecognized action — out of scope, the existing "step fails, scan still shows partial results" behavior is preserved.
