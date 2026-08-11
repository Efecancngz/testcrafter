from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import Project, User

router = APIRouter()

class ProjectCreate(BaseModel):
    name: str
    base_url: str

class ProjectOut(BaseModel):
    id: int
    name: str
    base_url: str
    model_config = {"from_attributes": True}

def _demo_user(session: Session) -> User:
    user = session.query(User).filter_by(email="demo@testcrafter.local").first()
    if user is None:
        user = User(email="demo@testcrafter.local")
        session.add(user)
        session.flush()
    return user

@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(payload: ProjectCreate, session: Session = Depends(get_session)):
    user = _demo_user(session)
    project = Project(user_id=user.id, name=payload.name, base_url=payload.base_url)
    session.add(project)
    session.commit()
    session.refresh(project)
    return project

@router.get("/projects", response_model=list[ProjectOut])
def list_projects(session: Session = Depends(get_session)):
    return session.query(Project).all()
