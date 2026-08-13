from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.db import get_session
from app.models import User
from app.auth import hash_password, verify_password, create_access_token

router = APIRouter()


class AuthRequest(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(payload: AuthRequest, session: Session = Depends(get_session)):
    existing = session.query(User).filter_by(email=payload.email).first()
    if existing is not None:
        raise HTTPException(status_code=400, detail="email already registered")
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    session.add(user)
    session.commit()
    session.refresh(user)
    return TokenOut(access_token=create_access_token(user.id))


@router.post("/auth/login", response_model=TokenOut)
def login(payload: AuthRequest, session: Session = Depends(get_session)):
    user = session.query(User).filter_by(email=payload.email).first()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid email or password")
    return TokenOut(access_token=create_access_token(user.id))
