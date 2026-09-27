"""Integration tests for GET /articles/{run_id} and GET /articles/{run_id}/assets/{filename} endpoints."""
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.config import get_settings
from apps.api.main import app
from apps.api.dependencies import get_db
from apps.api.db.base import Base
from apps.api.db.models import User, Run, RunStatus, RunVisibility
from apps.api.auth.sessions import create_session

settings = get_settings()

engine = create_engine(settings.TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


from sqlalchemy import text

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    app.dependency_overrides[get_db] = override_get_db
    client.cookies.clear()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM run_events; DELETE FROM runs; DELETE FROM sessions; DELETE FROM users;"))
    yield
    client.cookies.clear()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM run_events; DELETE FROM runs; DELETE FROM sessions; DELETE FROM users;"))
    app.dependency_overrides.pop(get_db, None)


def test_get_article_public_completed():
    with TestingSessionLocal() as db:
        run = Run(
            id="art-public-1",
            original_input="Public RAG",
            topic="RAG Systems in Production",
            status=RunStatus.COMPLETED.value,
            visibility=RunVisibility.PUBLIC.value,
            article_title="RAG Systems Guide",
            article_markdown="# RAG Systems Guide\n\nDetailed content here.",
            article_excerpt="Detailed content here.",
            completed_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()

    res = client.get("/articles/art-public-1")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "art-public-1"
    assert data["article_title"] == "RAG Systems Guide"
    assert data["article_markdown"] == "# RAG Systems Guide\n\nDetailed content here."
    assert data["visibility"] == "public"


def test_get_article_private_unauthorized():
    with TestingSessionLocal() as db:
        run = Run(
            id="art-private-1",
            original_input="Private AI",
            topic="Private AI",
            status=RunStatus.COMPLETED.value,
            visibility=RunVisibility.PRIVATE.value,
            article_title="Private AI Title",
            article_markdown="# Private AI",
        )
        db.add(run)
        db.commit()

    res = client.get("/articles/art-private-1")
    assert res.status_code == 404


def test_get_article_private_owner_authorized():
    with TestingSessionLocal() as db:
        user = User(google_sub="sub-owner-1", email="owner@example.com")
        db.add(user)
        db.commit()

        _, raw_token = create_session(db, user_id=user.id)
        client.cookies.set(settings.SESSION_COOKIE_NAME, raw_token)

        run = Run(
            id="art-private-owner",
            user_id=user.id,
            original_input="Private AI Owner",
            topic="Private AI Owner",
            status=RunStatus.COMPLETED.value,
            visibility=RunVisibility.PRIVATE.value,
            article_title="Owner Private Title",
            article_markdown="# Owner Private Content",
        )
        db.add(run)
        db.commit()

    res = client.get("/articles/art-private-owner")
    assert res.status_code == 200
    data = res.json()
    assert data["article_title"] == "Owner Private Title"


def test_get_article_asset_public(monkeypatch):
    with TestingSessionLocal() as db:
        assets = [
            {
                "filename": "arch.png",
                "public_id": "blog-agent/runs/art-public-2/images/arch",
                "asset_id": "a-123",
                "format": "png",
            }
        ]
        run = Run(
            id="art-public-2",
            original_input="Public Arch",
            topic="Public Arch",
            status=RunStatus.COMPLETED.value,
            visibility=RunVisibility.PUBLIC.value,
            article_title="Public Architecture",
            article_assets=assets,
        )
        db.add(run)
        db.commit()

    monkeypatch.setattr("apps.api.routers.articles.is_cloudinary_configured", lambda: True)
    monkeypatch.setattr(
        "apps.api.routers.articles.generate_signed_image_url",
        lambda pid: f"https://res.cloudinary.com/signed/{pid}",
    )

    res = client.get("/articles/art-public-2/assets/arch.png", follow_redirects=False)
    assert res.status_code == 307
    assert "https://res.cloudinary.com/signed/" in res.headers["location"]
