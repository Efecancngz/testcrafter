import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import Scan, Scenario
from app.crawler import extract_page_structure
from app.ai.base import AIProvider

router = APIRouter()

def get_ai_provider() -> AIProvider:
    from app.ai.claude_provider import ClaudeProvider
    import anthropic
    return ClaudeProvider(client=anthropic.Anthropic())

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

@router.post("/projects/{project_id}/scans", response_model=ScanOut, status_code=201)
def create_scan(project_id: int, payload: ScanCreate, session: Session = Depends(get_session)):
    page_structure = extract_page_structure(payload.target_url)
    scan = Scan(
        project_id=project_id,
        target_url=payload.target_url,
        description=payload.description,
        page_structure_json=page_structure.model_dump_json(),
        ai_provider="claude",
        status="analyzing",
    )
    session.add(scan)
    session.flush()

    try:
        provider = get_ai_provider()
        generated = provider.generate_scenarios(page_structure, payload.description)
        for g in generated:
            session.add(Scenario(scan_id=scan.id, title=g.title, steps_json=json.dumps([s.model_dump() for s in g.steps])))
        scan.status = "ready"
    except ValueError:
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
