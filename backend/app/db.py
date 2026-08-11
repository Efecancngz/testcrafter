from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

Base = declarative_base()

def make_engine(url: str = "sqlite:///./testcrafter.db"):
    if not url.startswith("sqlite"):
        return create_engine(url)
    # SQLite ":memory:" gives each connection its own private database, and
    # SQLAlchemy's default SingletonThreadPool hands out a new connection per
    # thread — so a request handled on FastAPI's worker thread pool would see
    # an empty database. StaticPool forces every thread to share one
    # connection, keeping the schema/data consistent across threads.
    if ":memory:" in url:
        return create_engine(url, connect_args={"check_same_thread": False}, poolclass=StaticPool)
    return create_engine(url, connect_args={"check_same_thread": False})

engine = make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
