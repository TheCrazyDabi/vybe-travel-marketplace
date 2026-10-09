import os
import tempfile

import pytest

from app import create_app
from config import Config


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    with app.test_client() as c:
        with app.app_context():
            yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_landing_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"VYBE" in r.data
    assert b"Find trips that match your vibe" in r.data


def test_register_login_flow(client):
    r = client.post("/api/auth/register", json={
        "name": "Test", "email": "t@t.com", "password": "secret123", "role": "traveler"
    })
    assert r.status_code == 201
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"email": "t@t.com", "password": "secret123"})
    assert r.status_code == 200


def test_recommended_requires_login(client):
    r = client.get("/api/packages/recommended")
    assert r.status_code in (302, 401)  # redirect to login or unauthorized


def test_recommendation_scoring():
    from types import SimpleNamespace

    from services.recommendation import score_package

    pkg = SimpleNamespace(
        interest_tags=["nature", "adventure"], activities=["trekking"],
        region_tags=["mountains"], scenery_tags=["mountains"],
        climate_tags=["cool"], mood_tags=["relaxation"],
        price=9000, duration_days=3,
    )
    prefs = {
        "interests": ["nature"], "preferred_regions": ["mountains"],
        "preferred_climate": ["cool"], "scenery": ["mountains"],
        "budget_max": 10000, "duration_days": 3, "current_mood": "relaxation",
    }
    score, reasons, expl = score_package(pkg, prefs)
    assert score > 50
    assert reasons


def test_preference_extraction_fallback():
    from services.vybe_ai import extract_preferences

    prefs = extract_preferences("cool mountains, trekking, 3 days under 12000, relaxing")
    assert "mountains" in prefs.get("preferred_regions", [])
    assert prefs.get("budget_max") == 12000
    assert prefs.get("duration_days") == 3
