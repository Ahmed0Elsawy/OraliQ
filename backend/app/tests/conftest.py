import os

# The run mode has no default any more; the suite runs explicitly as "test" (in-memory database,
# in-memory signing key, nothing written into the project).
os.environ["ENV"] = "test"
os.environ.pop("SPACE_ID", None)
# The API would otherwise start a real grading worker process (Whisper and all) on startup.
os.environ.setdefault("GRADING_WORKER_MODE", "off")

import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.api import deps
from app.core.database import Base, get_db

# In memory, and on one shared connection so every session in a test sees the same database.
# A file on disk kept rows between runs, so a second run failed on "email already registered".
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module")
def db() -> Generator:
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="module")
def client(db) -> Generator:
    def override_get_db():
        # The module's one session; closing it here would end the shared transaction mid-test
        yield db

    # The endpoints depend on deps.get_db, which is its own function — overriding only the one in
    # core.database left the tests running against the developer's real local database.
    app.dependency_overrides[deps.get_db] = override_get_db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
