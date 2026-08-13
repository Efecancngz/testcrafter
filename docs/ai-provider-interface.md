# AIProvider Interface

## Contract

```python
class AIProvider(ABC):
    @abstractmethod
    def generate_scenarios(self, page_structure: PageStructure, description: str) -> list[GeneratedScenario]:
        ...
```

Defined in `backend/app/ai/base.py`. `PageStructure`, `GeneratedScenario`, and `ScenarioStep` are Pydantic models in `backend/app/schemas.py`.

- `generate_scenarios` must return already-validated `GeneratedScenario` objects, or raise `ValueError` if the underlying model's output can't be parsed into that schema. Callers (see `backend/app/api/scans.py`) treat a `ValueError` as a scan failure (`status = "failed"`), not a crash.
- Implementations own their own prompt construction and response parsing; the interface only constrains the boundary.

## Adding a new provider

1. Create `backend/app/ai/<name>_provider.py` with a class implementing `AIProvider`.
2. Write `backend/tests/test_ai_<name>_provider.py` following the pattern in `test_ai_claude_provider.py` — fake the underlying SDK client, assert on parsed output and on the invalid-JSON error path.
3. Add a branch for it in `get_ai_provider()` in `backend/app/api/scans.py`, keyed on the `AI_PROVIDER` env var.

## Existing adapters

- `ClaudeProvider` (`backend/app/ai/claude_provider.py`) — uses the `anthropic` SDK's `messages.create`, expects a JSON array as the entire response text (see `SYSTEM_PROMPT` in that file).
- `GeminiProvider` (`backend/app/ai/gemini_provider.py`) — uses the `google-genai` SDK's `client.models.generate_content`, expects a JSON array as the entire response text (same `SYSTEM_PROMPT` pattern as `ClaudeProvider`).

## Selecting the active provider

Set `AI_PROVIDER` in `.env` to `claude` (default) or `gemini`. `get_ai_provider()` in `backend/app/api/scans.py` reads this at request time — no restart needed to pick up a changed value, since it's read fresh on every call. An unrecognized value raises `ValueError`, which `create_scan` treats as a scan failure like any other AI-provider error.
