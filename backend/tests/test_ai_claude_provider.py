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
