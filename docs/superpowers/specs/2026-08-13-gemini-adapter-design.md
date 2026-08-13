# Gemini Adapter + Provider Selection — Design Spec

**Date:** 2026-08-13
**Status:** Approved

## 1. Overview

Add a `GeminiProvider` implementing the existing `AIProvider` interface, and make `get_ai_provider()` select the active provider from a new `AI_PROVIDER` environment variable instead of being hardcoded to Claude. First of three planned features (Gemini adapter → screenshot capture → auth system), each with its own spec/plan/implementation cycle.

## 2. Components

### `backend/app/ai/gemini_provider.py`

Mirrors `backend/app/ai/claude_provider.py` structure exactly:

```python
class GeminiProvider(AIProvider):
    def __init__(self, client, model: str = "gemini-2.5-flash"):
        self._client = client
        self._model = model

    def generate_scenarios(self, page_structure: PageStructure, description: str) -> list[GeneratedScenario]:
        ...
```

- Uses the `google-genai` SDK's `client.models.generate_content(...)`.
- Uses the same `SYSTEM_PROMPT` text as `ClaudeProvider` (shared instruction: output a JSON array only, no prose).
- Parses response text as JSON, validates each item against `GeneratedScenario` via Pydantic.
- Raises `ValueError` on `json.JSONDecodeError` or `ValidationError`, matching `ClaudeProvider`'s contract — callers already treat `ValueError` as a scan failure.

### Provider selection (`backend/app/api/scans.py`)

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

- Default remains `"claude"` — no behavior change for existing deployments without `AI_PROVIDER` set.
- Unknown value raises `ValueError`, which the existing `except Exception` branch in `create_scan` already catches and turns into `status = "failed"` — no new error-handling branch needed.
- `create_scan`'s hardcoded `ai_provider="claude"` on the `Scan` row changes to `ai_provider=os.getenv("AI_PROVIDER", "claude")`, so the DB record reflects the provider actually used.

### Config

- `.env.example`: add `AI_PROVIDER=claude` and `GEMINI_API_KEY=`.
- `backend/requirements.txt`: add `google-genai`.

## 3. Testing

- `backend/tests/test_ai_gemini_provider.py` — follows `test_ai_claude_provider.py` pattern: fake the `google-genai` client, assert successful parse into `GeneratedScenario` list, assert invalid-JSON response raises `ValueError`.
- `backend/tests/test_api_scans.py` (or a new small test module) — unit tests for `get_ai_provider()`'s env-var switch: `AI_PROVIDER=gemini` returns a `GeminiProvider` instance, `AI_PROVIDER=claude`/unset returns `ClaudeProvider`, an unrecognized value raises `ValueError`.

## 4. Documentation

- `docs/ai-provider-interface.md`: add Gemini under "Existing adapters"; update the "will need a `.env`-driven switch once more than one provider exists" note since it now exists.
- `README.md` / `README.tr.md`: add Gemini to the provider list and document `AI_PROVIDER` / `GEMINI_API_KEY` setup.

## 5. Out of Scope

- DeepSeek/Qwen adapters (future work, same pattern).
- Runtime provider switching without restart (env var is read at request time via `get_ai_provider()`, so no restart is actually needed — but no UI/API to change it exists or is planned here).
