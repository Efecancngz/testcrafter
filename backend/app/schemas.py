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
    action: str      # "click" | "fill" | "goto" | "expect_text" | "expect_url" | "expect_visible"
    selector: str | None = None
    value: str | None = None
    expected: str | None = None


class GeneratedScenario(BaseModel):
    title: str
    steps: list[ScenarioStep]
