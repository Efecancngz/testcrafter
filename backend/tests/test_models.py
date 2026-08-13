# backend/tests/test_models.py
from app.models import User, Project, Scan, Scenario, Run, RunStep

def test_can_create_full_chain(db_session):
    user = User(email="demo@testcrafter.local", password_hash="not-a-real-hash")
    db_session.add(user)
    db_session.flush()

    project = Project(user_id=user.id, name="Demo Site", base_url="https://example.com")
    db_session.add(project)
    db_session.flush()

    scan = Scan(
        project_id=project.id,
        target_url="https://example.com/login",
        description="Login form should validate empty fields",
        page_structure_json="{}",
        ai_provider="claude",
        status="pending",
    )
    db_session.add(scan)
    db_session.flush()

    scenario = Scenario(scan_id=scan.id, title="Empty login shows error", steps_json="[]")
    db_session.add(scenario)
    db_session.flush()

    run = Run(scenario_id=scenario.id, status="pending")
    db_session.add(run)
    db_session.flush()

    step = RunStep(run_id=run.id, step_index=0, status="passed", log_message="ok")
    db_session.add(step)
    db_session.commit()

    assert db_session.query(RunStep).count() == 1
    assert step.run_id == run.id
    assert run.scenario_id == scenario.id
