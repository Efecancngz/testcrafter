import json

from pydantic import ValidationError

from app.ai.base import AIProvider
from app.ai.prompts import SYSTEM_PROMPT
from app.schemas import PageStructure, GeneratedScenario


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
            config={"response_mime_type": "application/json"},
        )
        raw_text = response.text
        if raw_text is None:
            raise ValueError("invalid AI response: empty response")
        try:
            parsed = json.loads(raw_text)
            return [GeneratedScenario.model_validate(item) for item in parsed]
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"invalid AI response: {exc}") from exc
