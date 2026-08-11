from dataclasses import dataclass
from playwright.sync_api import sync_playwright
from app.schemas import GeneratedScenario

@dataclass
class StepResult:
    status: str
    log_message: str

def run_scenario(scenario: GeneratedScenario, base_url: str) -> list[StepResult]:
    results: list[StepResult] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            for step in scenario.steps:
                results.append(_run_step(page, step, base_url))
        finally:
            browser.close()
    return results

def _run_step(page, step, base_url: str) -> StepResult:
    try:
        if step.action == "goto":
            page.goto(step.value)
        elif step.action == "click":
            page.click(step.selector)
        elif step.action == "fill":
            page.fill(step.selector, step.value)
        elif step.action == "expect_text":
            actual = page.text_content(step.selector) or ""
            if step.expected not in actual:
                return StepResult(status="failed", log_message=f"expected '{step.expected}' in '{actual}'")
        elif step.action == "expect_url":
            if step.expected not in page.url:
                return StepResult(status="failed", log_message=f"expected url containing '{step.expected}', got '{page.url}'")
        else:
            return StepResult(status="failed", log_message=f"unknown action: {step.action}")
        return StepResult(status="passed", log_message="ok")
    except Exception as exc:
        return StepResult(status="failed", log_message=str(exc))
