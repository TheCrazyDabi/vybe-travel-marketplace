"""Dedicated Profile page: separate from onboarding, safe demo editing."""

import pytest

from app import create_app
from config import Config
from models import User, db


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    with app.test_client() as c:
        yield c


def register(c, name="Zed", email="zed@z.com", role="traveler"):
    r = c.post("/api/auth/register",
               json={"name": name, "email": email, "password": "secret123", "role": role})
    assert r.status_code == 201
    return r.get_json()["user"]


def test_profile_requires_login(client):
    assert client.get("/profile").status_code == 302


def test_profile_shows_current_user_not_hardcoded(client):
    register(client, name="Zed Zee", email="zed@z.com")
    body = client.get("/profile").data.decode()
    assert "Zed Zee" in body and "zed@z.com" in body and "Traveler" in body
    assert "••••••••" in body  # masked password, no plaintext
    client.post("/api/auth/logout")
    register(client, name="Op",
             email="op@o.com", role="operator")
    body = client.get("/profile").data.decode()
    assert "Op" in body and "Operator" in body


def test_nav_separation_and_onboarding_intact(client):
    register(client)
    body = client.get("/").data.decode()
    assert 'href="/profile"' in body
    # /onboarding page + backend stay intact (homepage button intentionally removed)
    assert client.get("/onboarding").status_code == 200
    assert client.get("/profile").status_code == 200


def test_name_update_persists_and_validates(client):
    register(client)
    r = client.put("/api/profile", json={"name": "Zed Updated", "start_city": "Kochi"})
    assert r.status_code == 200
    assert r.get_json()["user"]["name"] == "Zed Updated"
    assert "Kochi" in client.get("/profile").data.decode()
    assert client.put("/api/profile", json={"name": "  "}).status_code == 400
    assert client.put("/api/profile", json={"name": "x" * 121}).status_code == 400


def test_demo_fields_ignored_and_password_untouched(client):
    register(client)
    r = client.put("/api/profile",
                   json={"phone": "+91 1", "bio": "hi", "password": "hacked"})
    assert r.status_code == 200  # unknown fields ignored, not stored
    with client.application.app_context():
        u = User.query.filter_by(email="zed@z.com").first()
        assert u.name == "Zed" and u.check_password("secret123")
        assert not hasattr(u, "phone")
    assert client.get("/logout").status_code == 302  # logout still works


def test_profile_has_no_preferences_questionnaire(client):
    register(client)
    client.post("/api/preferences", json={"budget_max": 20000, "current_mood": "adventure",
                                          "preferred_regions": ["mountains"],
                                          "duration_days": 3})
    body = client.get("/profile").data.decode()
    # personal account info only: no prefs table, no budget/mood values
    assert "Travel preferences" not in body
    assert "20,000" not in body
    assert "Zed" in body and "zed@z.com" in body
    # preferences live on Discover (Edit preferences) + /onboarding page instead
    assert client.get("/onboarding").status_code == 200
    disc = client.get("/discover").data.decode()
    assert disc and "Edit preferences" in disc
