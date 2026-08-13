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
