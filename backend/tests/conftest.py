import pytest
from sqlalchemy.orm import sessionmaker
from app.db import Base, make_engine

@pytest.fixture
def db_session():
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    yield session
    session.close()
