import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from playwright.sync_api import Error as PlaywrightError
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import Project, Run, RunStep, Scan, Scenario, User
from app.auth import get_current_user
from app.crawler import extract_page_structure, BotChallengeDetected
from app.ai.base import AIProvider
from app.runner import run_scenario
from app.schemas import GeneratedScenario, ScenarioStep

router = APIRouter()
logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "screenshots"

def get_ai_provider() -> AIProvider:
    provider_name = os.getenv("AI_PROVIDER", "claude")
    if provider_name == "claude":
        from app.ai.claude_provider import ClaudeProvider
        import anthropic
        return ClaudeProvider(client=anthropic.Anthropic())
    if provider_name == "gemini":
        from app.ai.gemini_provider import GeminiProvider
        from google import genai
        return GeminiProvider(client=genai.Client())
    raise ValueError(f"unknown AI_PROVIDER: {provider_name}")

def _get_owned_scan(scan_id: int, user: User, session: Session) -> Scan:
    scan = (
        session.query(Scan)
        .join(Project, Scan.project_id == Project.id)
        .filter(Scan.id == scan_id, Project.user_id == user.id)
        .first()
    )
    if scan is None:
        raise HTTPException(status_code=404, detail="scan not found")
    return scan

class ScanCreate(BaseModel):
    target_url: str
    description: str

    @field_validator("target_url")
    @classmethod
    def _normalize_target_url(cls, value: str) -> str:
        value = value.strip()
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value):
            value = f"https://{value}"
        return value

class ScenarioOut(BaseModel):
    id: int
    title: str
    steps_json: str
    model_config = {"from_attributes": True}

class ScanOut(BaseModel):
    id: int
    target_url: str
    status: str
    blocked_reason: str | None = None
    scenarios: list[ScenarioOut]

def _scan_out(scan: Scan, scenarios: list[Scenario]) -> "ScanOut":
    return ScanOut(
        id=scan.id,
        target_url=scan.target_url,
        status=scan.status,
        blocked_reason=scan.blocked_reason,
        scenarios=scenarios,
    )

class RunStepOut(BaseModel):
    id: int
    step_index: int
    status: str
    log_message: str | None = None
    screenshot_path: str | None = None
    model_config = {"from_attributes": True}

class RunOut(BaseModel):
    id: int
    scenario_id: int
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    steps: list[RunStepOut]
    model_config = {"from_attributes": True}

@router.post("/projects/{project_id}/scans", response_model=ScanOut, status_code=201)
def create_scan(project_id: int, payload: ScanCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    project = session.query(Project).filter_by(id=project_id, user_id=user.id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    scan = Scan(
        project_id=project_id,
        target_url=payload.target_url,
        description=payload.description,
        page_structure_json="",
        ai_provider=os.getenv("AI_PROVIDER", "claude"),
        status="analyzing",
    )
    session.add(scan)
    session.flush()

    try:
        page_structure = extract_page_structure(payload.target_url)
    except BotChallengeDetected as e:
        logger.info("bot challenge detected for scan %s (%s): %s", scan.id, payload.target_url, e.provider)
        scan.status = "blocked"
        scan.blocked_reason = e.provider
        session.commit()
        session.refresh(scan)
        return _scan_out(scan, [])
    except PlaywrightError:
        # Bad/unreachable target_url is external input, not a bug in our code —
        # record the scan as failed instead of a 500, per docs/api-spec.md.
        logger.exception("crawl failed for scan %s (%s)", scan.id, payload.target_url)
        scan.status = "failed"
        session.commit()
        session.refresh(scan)
        return _scan_out(scan, [])

    scan.page_structure_json = page_structure.model_dump_json()

    try:
        provider = get_ai_provider()
        generated = provider.generate_scenarios(page_structure, payload.description)
        for g in generated:
            session.add(Scenario(scan_id=scan.id, title=g.title, steps_json=json.dumps([s.model_dump() for s in g.steps])))
        scan.status = "ready"
    except ValueError:
        logger.exception("AI provider returned an invalid response for scan %s", scan.id)
        scan.status = "failed"
    except Exception:
        # Catches AI-provider construction/config failures too, e.g. missing
        # ANTHROPIC_API_KEY raises TypeError from anthropic.Anthropic(), which
        # a bare `except ValueError` would let escape as an unhandled 500.
        logger.exception("AI provider is not configured for scan %s", scan.id)
        scan.status = "failed"

    session.commit()
    session.refresh(scan)
    scenarios = session.query(Scenario).filter_by(scan_id=scan.id).all()
    return _scan_out(scan, scenarios)

@router.get("/scans/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    scan = _get_owned_scan(scan_id, user, session)
    scenarios = session.query(Scenario).filter_by(scan_id=scan.id).all()
    return _scan_out(scan, scenarios)

@router.post("/scans/{scan_id}/run", response_model=list[RunOut])
def run_scan(scan_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    scan = _get_owned_scan(scan_id, user, session)

    scenarios = session.query(Scenario).filter_by(scan_id=scan.id).all()
    runs: list[Run] = []
    for scenario in scenarios:
        steps = [ScenarioStep(**s) for s in json.loads(scenario.steps_json)]
        generated = GeneratedScenario(title=scenario.title, steps=steps)

        run = Run(scenario_id=scenario.id, status="pending", started_at=datetime.now(timezone.utc), finished_at=None)
        session.add(run)
        session.flush()
        session.commit()

        results = run_scenario(generated, base_url="", screenshot_dir=SCREENSHOTS_DIR / str(run.id))
        run.finished_at = datetime.now(timezone.utc)
        run.status = "passed" if all(r.status == "passed" for r in results) else "failed"

        for index, result in enumerate(results):
            screenshot_path = f"/runs/{run.id}/screenshots/{index}" if result.screenshot_path else None
            session.add(RunStep(run_id=run.id, step_index=index, status=result.status, log_message=result.log_message, screenshot_path=screenshot_path))
        runs.append(run)

    session.commit()

    run_ids = [run.id for run in runs]
    steps_by_run: dict[int, list[RunStep]] = {run_id: [] for run_id in run_ids}
    for run_step in session.query(RunStep).filter(RunStep.run_id.in_(run_ids)).all():
        steps_by_run[run_step.run_id].append(run_step)

    return [
        RunOut(
            id=run.id,
            scenario_id=run.scenario_id,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            steps=steps_by_run[run.id],
        )
        for run in runs
    ]

@router.get("/runs/{run_id}/screenshots/{step_index}")
def get_screenshot(run_id: int, step_index: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    owned = (
        session.query(RunStep)
        .join(Run, RunStep.run_id == Run.id)
        .join(Scenario, Run.scenario_id == Scenario.id)
        .join(Scan, Scenario.scan_id == Scan.id)
        .join(Project, Scan.project_id == Project.id)
        .filter(RunStep.run_id == run_id, RunStep.step_index == step_index, Project.user_id == user.id)
        .first()
    )
    if owned is None:
        raise HTTPException(status_code=404, detail="screenshot not found")
    file_path = SCREENSHOTS_DIR / str(run_id) / f"{step_index}.png"
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="screenshot not found")
    return FileResponse(file_path)
