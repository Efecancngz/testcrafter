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
