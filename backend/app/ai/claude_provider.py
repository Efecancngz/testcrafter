import json

from pydantic import ValidationError

from app.ai.base import AIProvider
from app.ai.prompts import SYSTEM_PROMPT
from app.schemas import PageStructure, GeneratedScenario


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
