from pathlib import Path
from app.schemas import GeneratedScenario, ScenarioStep
from app.runner import run_scenario

FIXTURE_URL = (Path(__file__).parent / "fixtures" / "login_page.html").as_uri()

def test_run_scenario_passes_when_expectation_met():
    scenario = GeneratedScenario(
        title="Submit button has correct label",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_text", selector="#submit", expected="Log in"),
        ],
    )

    results = run_scenario(scenario, base_url="")

    assert all(r.status == "passed" for r in results)
    assert len(results) == 2

def test_run_scenario_fails_when_expectation_not_met():
    scenario = GeneratedScenario(
        title="Submit button has wrong label",
        steps=[
            ScenarioStep(action="goto", value=FIXTURE_URL),
            ScenarioStep(action="expect_text", selector="#submit", expected="Sign up"),
        ],
    )

    results = run_scenario(scenario, base_url="")

    assert results[-1].status == "failed"
