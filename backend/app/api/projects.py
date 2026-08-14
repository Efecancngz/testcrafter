from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import Project, Scan, User
from app.auth import get_current_user

router = APIRouter()

class ProjectCreate(BaseModel):
    name: str
    base_url: str

class ProjectOut(BaseModel):
    id: int
    name: str
    base_url: str
    model_config = {"from_attributes": True}

class ScanSummaryOut(BaseModel):
    id: int
    target_url: str
    status: str
    blocked_reason: str | None = None
    created_at: datetime
    model_config = {"from_attributes": True}

@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    project = Project(user_id=user.id, name=payload.name, base_url=payload.base_url)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project

@router.get("/projects", response_model=list[ProjectOut])
def list_projects(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    return session.query(Project).filter_by(user_id=user.id).all()

@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    project = session.query(Project).filter_by(id=project_id, user_id=user.id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project

@router.get("/projects/{project_id}/scans", response_model=list[ScanSummaryOut])
def list_project_scans(project_id: int, user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    project = session.query(Project).filter_by(id=project_id, user_id=user.id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return (
        session.query(Scan)
        .filter_by(project_id=project_id)
        .order_by(Scan.created_at.desc())
        .all()
    )
