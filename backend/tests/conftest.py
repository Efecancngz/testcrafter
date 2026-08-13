import pytest
from sqlalchemy.orm import sessionmaker
from app.db import Base, make_engine

@pytest.fixture(autouse=True)
def _test_secret_key(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-do-not-use-in-production")

@pytest.fixture
def db_session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()

from fastapi.testclient import TestClient
from app.db import get_session
from app.main import app

@pytest.fixture
def client(db_session):
    def override_get_session():
        yield db_session
    app.dependency_overrides[get_session] = override_get_session
    yield TestClient(app)
    app.dependency_overrides.clear()
