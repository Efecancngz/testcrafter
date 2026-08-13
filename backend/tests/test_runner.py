from pathlib import Path
from app.schemas import GeneratedScenario, ScenarioStep
from app.runner import run_scenario

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "login_page.html").as_uri()

def test_run_scenario_passes_when_expectation_met(tmp_path):
    scenario = GeneratedScenario(
        title="Submit button has correct label",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_text", selector="#submit", expected="Log in"),
        ],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert all(r.status == "passed" for r in results)
    assert len(results) == 2

def test_run_scenario_fails_when_expectation_not_met(tmp_path):
    scenario = GeneratedScenario(
        title="Submit button has wrong label",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_text", selector="#submit", expected="Sign up"),
        ],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert results[-1].status == "failed"

def test_run_scenario_captures_screenshot_per_step(tmp_path):
    scenario = GeneratedScenario(
        title="Submit button has correct label",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_text", selector="#submit", expected="Log in"),
        ],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert len(results) == 2
    for index, result in enumerate(results):
        assert result.screenshot_path == str(tmp_path / f"{index}.png")
        assert (tmp_path / f"{index}.png").exists()

def test_run_scenario_screenshot_failure_does_not_change_step_status(tmp_path, monkeypatch):
    scenario = GeneratedScenario(
        title="Submit button has correct label",
        steps=[ScenarioStep(action="goto", value=FIXTURE_URL)],
    )

    from playwright.sync_api import Page
    def broken_screenshot(self, **kwargs):
        raise RuntimeError("simulated screenshot failure")
    monkeypatch.setattr(Page, "screenshot", broken_screenshot)

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert len(results) == 1
    assert results[0].status == "passed"
    assert results[0].screenshot_path is None

def test_run_scenario_expect_visible_passes_for_visible_element(tmp_path):
    scenario = GeneratedScenario(
        title="Submit button is visible",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_visible", selector="#submit"),
        ],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert results[-1].status == "passed"

def test_run_scenario_expect_visible_fails_for_hidden_element(tmp_path):
    scenario = GeneratedScenario(
        title="Hidden banner is not visible",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_visible", selector="#hidden-banner"),
        ],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert results[-1].status == "failed"
    assert "not visible" in results[-1].log_message

def test_run_scenario_normalizes_known_action_synonyms(tmp_path):
    scenario = GeneratedScenario(
        title="Synonym actions resolve correctly",
        steps=[
            ScenarioStep(action="navigate", value=FIXTURE_URL),
            ScenarioStep(action="assertVisibility", selector="#submit"),
            ScenarioStep(action="assert_text", selector="#submit", expected="Log in"),
            ScenarioStep(action="assertUrl", expected="login_page"),
        ],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert all(r.status == "passed" for r in results)

def test_run_scenario_fails_for_genuinely_unknown_action(tmp_path):
    scenario = GeneratedScenario(
        title="Unrecognized action",
        steps=[ScenarioStep(action="do_a_backflip", selector="#submit")],
    )

    results = run_scenario(scenario, base_url="", screenshot_dir=tmp_path)

    assert results[0].status == "failed"
    assert "unknown action" in results[0].log_message
