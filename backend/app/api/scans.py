import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from playwright.sync_api import Error as PlaywrightError
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import Run, RunStep, Scan, Scenario
from app.crawler import extract_page_structure
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

class ScanCreate(BaseModel):
    target_url: str
    description: str

class ScenarioOut(BaseModel):
    id: int
    title: str
    steps_json: str
    model_config = {"from_attributes": True}

class ScanOut(BaseModel):
    id: int
    target_url: str
    status: str
    scenarios: list[ScenarioOut]

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
    finished_at: datetime
    steps: list[RunStepOut]
    model_config = {"from_attributes": True}

@router.post("/projects/{project_id}/scans", response_model=ScanOut, status_code=201)
def create_scan(project_id: int, payload: ScanCreate, session: Session = Depends(get_session)):
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
    except PlaywrightError:
        # Bad/unreachable target_url is external input, not a bug in our code —
        # record the scan as failed instead of a 500, per docs/api-spec.md.
        logger.exception("crawl failed for scan %s (%s)", scan.id, payload.target_url)
        scan.status = "failed"
        session.commit()
        session.refresh(scan)
        return ScanOut(id=scan.id, target_url=scan.target_url, status=scan.status, scenarios=[])

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
    return ScanOut(id=scan.id, target_url=scan.target_url, status=scan.status, scenarios=scenarios)

@router.get("/scans/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: int, session: Session = Depends(get_session)):
    scan = session.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="scan not found")
    scenarios = session.query(Scenario).filter_by(scan_id=scan.id).all()
    return ScanOut(id=scan.id, target_url=scan.target_url, status=scan.status, scenarios=scenarios)

@router.post("/scans/{scan_id}/run", response_model=list[RunOut])
def run_scan(scan_id: int, session: Session = Depends(get_session)):
    scan = session.get(Scan, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="scan not found")

    scenarios = session.query(Scenario).filter_by(scan_id=scan.id).all()
    runs: list[Run] = []
    for scenario in scenarios:
        steps = [ScenarioStep(**s) for s in json.loads(scenario.steps_json)]
        generated = GeneratedScenario(title=scenario.title, steps=steps)

        run = Run(scenario_id=scenario.id, status="pending", started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc))
        session.add(run)
        session.flush()

        results = run_scenario(generated, base_url="", screenshot_dir=SCREENSHOTS_DIR / str(run.id))
        run.finished_at = datetime.now(timezone.utc)
        run.status = "passed" if all(r.status == "passed" for r in results) else "failed"

        for index, result in enumerate(results):
            screenshot_path = f"/screenshots/{run.id}/{index}.png" if result.screenshot_path else None
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
