import logging
from dataclasses import dataclass
from pathlib import Path
from playwright.sync_api import sync_playwright
from app.schemas import GeneratedScenario

logger = logging.getLogger(__name__)

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

def _run_step(page, step, base_url: str, screenshot_dir: Path, step_index: int) -> StepResult:
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
                return _finish(page, screenshot_dir, step_index, "failed", f"expected '{step.expected}' in '{actual}'")
        elif step.action == "expect_url":
            if step.expected not in page.url:
                return _finish(page, screenshot_dir, step_index, "failed", f"expected url containing '{step.expected}', got '{page.url}'")
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
