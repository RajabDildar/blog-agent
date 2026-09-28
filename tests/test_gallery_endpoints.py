"""Integration tests for GET /gallery and GET /featured endpoints with pagination and sorting."""
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from apps.api.config import get_settings
from apps.api.main import app
from apps.api.dependencies import get_db
from apps.api.db.base import Base
from apps.api.db.models import Run, RunStatus, RunVisibility

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
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM run_events; DELETE FROM runs; DELETE FROM sessions; DELETE FROM users;"))
    yield
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM run_events; DELETE FROM runs; DELETE FROM sessions; DELETE FROM users;"))
    app.dependency_overrides.pop(get_db, None)


def test_gallery_filtering_and_pagination():
    with TestingSessionLocal() as db:
        now = datetime.now(timezone.utc)

        # 1. Public completed article 1
        r1 = Run(
            id="gal-1",
            original_input="Topic 1",
            topic="Topic 1",
            status=RunStatus.COMPLETED.value,
            visibility=RunVisibility.PUBLIC.value,
            article_title="Article 1",
            completed_at=now - timedelta(minutes=10),
        )
        # 2. Public completed article 2 (newer)
        r2 = Run(
            id="gal-2",
            original_input="Topic 2",
            topic="Topic 2",
            status=RunStatus.COMPLETED.value,
            visibility=RunVisibility.PUBLIC.value,
            article_title="Article 2",
            completed_at=now,
        )
        # 3. Private completed article (must be excluded)
        r3 = Run(
            id="gal-3",
            original_input="Topic 3",
            topic="Topic 3",
            status=RunStatus.COMPLETED.value,
            visibility=RunVisibility.PRIVATE.value,
            article_title="Article 3",
            completed_at=now,
        )
        # 4. Public non-completed article (must be excluded)
        r4 = Run(
            id="gal-4",
            original_input="Topic 4",
            topic="Topic 4",
            status=RunStatus.RUNNING.value,
            visibility=RunVisibility.PUBLIC.value,
            article_title="Article 4",
        )
        db.add_all([r1, r2, r3, r4])
        db.commit()

    res = client.get("/gallery?page=1&page_size=10")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2
    # Ordered completed_at DESC -> gal-2 first, then gal-1
    assert items[0]["id"] == "gal-2"
    assert items[1]["id"] == "gal-1"


def test_featured_articles():
    with TestingSessionLocal() as db:
        now = datetime.now(timezone.utc)

        r1 = Run(
            id="feat-1",
            original_input="Feat 1",
            topic="Feat 1",
            status=RunStatus.COMPLETED.value,
            visibility=RunVisibility.PUBLIC.value,
            featured=True,
            article_title="Featured Article 1",
            completed_at=now,
        )
        r2 = Run(
            id="feat-2",
            original_input="Non-Feat 2",
            topic="Non-Feat 2",
            status=RunStatus.COMPLETED.value,
            visibility=RunVisibility.PUBLIC.value,
            featured=False,
            article_title="Ordinary Article 2",
            completed_at=now,
        )
        db.add_all([r1, r2])
        db.commit()

    res = client.get("/featured")
    assert res.status_code == 200
    items = res.json()
    assert len(items) == 1
    assert items[0]["id"] == "feat-1"


def test_negative_pagination_rejected():
    """Negative pagination inputs to /gallery and /runs must be rejected with 422."""
    # Negative page_size
    res1 = client.get("/gallery?page_size=-1")
    assert res1.status_code == 422

    # Negative limit
    res2 = client.get("/gallery?limit=-1")
    assert res2.status_code == 422

    # Negative offset
    res3 = client.get("/gallery?offset=-1")
    assert res3.status_code == 422

    # Negative page
    res4 = client.get("/gallery?page=0")
    assert res4.status_code == 422

    # Runs negative limit
    res5 = client.get("/runs?limit=-1")
    assert res5.status_code == 422

    # Runs negative offset
    res6 = client.get("/runs?offset=-1")
    assert res6.status_code == 422
