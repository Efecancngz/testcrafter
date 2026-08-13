from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import Project, User
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
