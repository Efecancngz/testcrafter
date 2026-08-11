from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

def make_engine(url: str = "sqlite:///./testcrafter.db"):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)

engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
