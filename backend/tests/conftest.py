"""
Test fixtures for AI Second Brain.

Sets up a SQLite in-memory database and overrides FastAPI dependencies
for isolated, repeatable tests.
"""

import pytest
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import get_db
from app.models.base import Base

# ---------------------------------------------------------------------------
# In-memory SQLite engine – tables created once per session, cleared per test.
# ---------------------------------------------------------------------------
engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _override_get_db():
    """Override the global get_db dependency with a test-local session."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Override rate-limit dependencies so they don't block test requests.
# Individual tests that exercise rate limiting re-register their own limiter.
# ---------------------------------------------------------------------------
from fastapi import Request


def _no_rate_limit(request: Request) -> bool:
    return True


@pytest.fixture(autouse=True)
def _setup_db():
    """Create all tables before each test and drop them after.

    This gives every test a clean database without cross-test leakage.
    """
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Provide a clean SQLAlchemy session for direct DB access in tests."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def user(db_session):
    """Create and return a test user."""
    from app.models.user import User
    from app.core.security import hash_password

    test_user = User(
        email="testuser@example.com",
        full_name="Test User",
        hashed_password=hash_password("TestPass123"),
    )
    db_session.add(test_user)
    db_session.commit()
    db_session.refresh(test_user)
    return test_user


@pytest.fixture(autouse=True)
def _override_deps():
    """Install all dependency overrides before each test."""
    app.dependency_overrides[get_db] = _override_get_db
    from app.core.rate_limiter import (
        login_limiter,
        register_limiter,
        refresh_limiter,
        logout_limiter,
    )
    app.dependency_overrides[login_limiter] = _no_rate_limit
    app.dependency_overrides[register_limiter] = _no_rate_limit
    app.dependency_overrides[refresh_limiter] = _no_rate_limit
    app.dependency_overrides[logout_limiter] = _no_rate_limit
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """FastAPI TestClient bound to the test database."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def registered_user(client):
    """Register a user and return (email, password, user_data)."""
    email = "alice@example.com"
    password = "StrongPass1"
    full_name = "Alice Wonderland"

    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": full_name,
        },
    )
    assert response.status_code == 201
    return email, password, response.json()


@pytest.fixture
def auth_headers(client, registered_user):
    """Login a registered user and return Authorization headers."""
    email, password, _ = registered_user
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def api_user(db_session, registered_user):
    """Get the User ORM object for the authenticated API user.

    Bridges the gap between the user created by `auth_headers`
    (via register/login) and the DB session, so tests can create
    data for the same user that the API calls authenticate as.
    """
    from app.models.user import User
    user_id = uuid.UUID(registered_user[2]["id"])
    return db_session.query(User).filter(User.id == user_id).first()
