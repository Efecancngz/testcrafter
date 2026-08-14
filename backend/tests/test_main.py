from datetime import datetime, timezone
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.db import Base, make_engine
import app.db as db_module
from app.models import Project, Run, Scan, Scenario, User


def test_startup_marks_interrupted_pending_and_running_runs_as_failed(tmp_path, monkeypatch):
    test_engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(test_engine)
    TestSessionLocal = sessionmaker(bind=test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "SessionLocal", TestSessionLocal)

    setup_session = TestSessionLocal()
    user = User(email="startup@example.com", password_hash="x")
    setup_session.add(user)
    setup_session.flush()
    project = Project(user_id=user.id, name="Demo", base_url="https://example.com")
    setup_session.add(project)
    setup_session.flush()
    scan = Scan(project_id=project.id, target_url="https://example.com", description="d", page_structure_json="{}", ai_provider="claude", status="ready")
    setup_session.add(scan)
    setup_session.flush()
    pending_scenario = Scenario(scan_id=scan.id, title="Pending scenario", steps_json="[]")
    running_scenario = Scenario(scan_id=scan.id, title="Running scenario", steps_json="[]")
    passed_scenario = Scenario(scan_id=scan.id, title="Passed scenario", steps_json="[]")
    setup_session.add(pending_scenario)
    setup_session.add(running_scenario)
    setup_session.add(passed_scenario)
    setup_session.flush()

    pending_run = Run(scenario_id=pending_scenario.id, status="pending", started_at=datetime.now(timezone.utc))
    running_run = Run(scenario_id=running_scenario.id, status="running", started_at=datetime.now(timezone.utc))
    already_passed_run = Run(
        scenario_id=passed_scenario.id,
        status="passed",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )
    setup_session.add(pending_run)
    setup_session.add(running_run)
    setup_session.add(already_passed_run)
    setup_session.commit()
    pending_run_id = pending_run.id
    running_run_id = running_run.id
    already_passed_run_id = already_passed_run.id
    setup_session.close()

    # Importing app.main here (after SessionLocal is patched) and using
    # TestClient as a context manager runs FastAPI's startup event handlers
    # before the `with` block body executes.
    from app.main import app

    with TestClient(app):
        pass

    verify_session = TestSessionLocal()
    pending_after = verify_session.get(Run, pending_run_id)
    running_after = verify_session.get(Run, running_run_id)
    passed_after = verify_session.get(Run, already_passed_run_id)

    assert pending_after.status == "failed"
    assert pending_after.finished_at is not None

    assert running_after.status == "failed"
    assert running_after.finished_at is not None

    # Runs that already finished before startup must not be touched.
    assert passed_after.status == "passed"
    verify_session.close()
