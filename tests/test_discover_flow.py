"""Discover-first flow: gating, onboarding validation, preference-driven ranking."""

import pytest

from app import create_app
from config import Config
from models import TravelCompany, TravelPackage, User, db


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    with app.app_context():
        t = User(name="T", email="t@t.com", role="traveler"); t.set_password("secret123")
        o = User(name="O", email="o@o.com", role="operator"); o.set_password("secret123")
        db.session.add_all([t, o]); db.session.flush()
        co = TravelCompany(user_id=o.id, company_name="Co", business_email="o@o.com",
                           status="approved", is_verified=True)
        db.session.add(co); db.session.flush()
        db.session.add(TravelPackage(operator_id=co.id, title="Budget Hills", destination="Ooty",
                                      price=8000, duration_days=3, is_active=True,
                                      region_tags=["mountains"], interest_tags=["nature"],
                                      mood_tags=["relaxation"]))
        db.session.add(TravelPackage(operator_id=co.id, title="Luxury Coast", destination="Goa",
                                      price=45000, duration_days=5, is_active=True,
                                      region_tags=["beaches"], interest_tags=["nightlife"],
                                      mood_tags=["party"]))
        db.session.commit()
    with app.test_client() as c:
        yield c


def login(c, email="t@t.com"):
    assert c.post("/api/auth/login",
                  json={"email": email, "password": "secret123"}).status_code == 200


def complete_onboarding(c, **fields):
    data = {"current_mood": "relaxation", "budget_per_person": "12000",
            "duration_days": "3", "preferred_destinations": "Ooty",
            "onboarding_completed": "1", "onboarding_step": "5"}
    data.update(fields)
    return c.post("/onboarding", data=data)


def test_new_traveler_full_flow(client):
    login(client)
    # 1-2. missing prefs -> onboarding with explanation
    r = client.get("/discover")
    assert r.status_code == 302 and r.headers["Location"].endswith("/onboarding")
    # 3-4. completion attempt without required fields fails open
    r = client.post("/onboarding", data={"onboarding_completed": "1", "onboarding_step": "5"})
    assert r.status_code == 200 and b"Almost there" in r.data
    with client.application.app_context():
        assert User.query.filter_by(email="t@t.com").first().profile.onboarding_completed is not True
    # 5-6. valid completion saves + redirects to discover
    r = complete_onboarding(client)
    assert r.status_code == 302 and r.headers["Location"].endswith("/discover")
    with client.application.app_context():
        p = User.query.filter_by(email="t@t.com").first().profile
        assert p.onboarding_completed is True and p.budget_per_person == 12000
    # 7. ranked recs from saved prefs (budget 12000 excludes 45000 package)
    recs = client.get("/api/packages/recommended").get_json()["packages"]
    assert [p["title"] for p in recs] == ["Budget Hills"]
    assert recs[0]["match_score"] > 0 and recs[0]["match_reasons"]
    assert client.get("/discover").status_code == 200  # returning: straight in


def test_updated_prefs_change_recommendations(client):
    login(client)
    complete_onboarding(client)
    assert len(client.get("/api/packages/recommended").get_json()["packages"]) == 1
    client.put("/api/profile", json={"budget_max": 60000, "budget_per_person": 60000})
    recs = client.get("/api/packages/recommended").get_json()["packages"]
    assert len(recs) == 2  # luxury package now affordable


def test_operator_bypasses_gate_and_map_hidden(client):
    login(client, "o@o.com")
    assert client.get("/discover").status_code == 200  # no traveler prefs needed
    body = client.get("/").data.decode()
    assert 'href="/map"' not in body  # absent from nav
    r = client.get("/map")  # old route redirects, auth intact
    assert r.status_code == 302 and r.headers["Location"].endswith("/discover")
    c2 = client.application.test_client()
    assert c2.get("/map").status_code == 302  # logged out -> login


def test_independent_histories(client):
    login(client)
    complete_onboarding(client)
    pid = client.get("/api/packages/recommended").get_json()["packages"][0]["id"]
    assert client.post(f"/api/packages/{pid}/swipe", json={"action": "pass"}).status_code == 200
    assert client.get("/api/packages/recommended").get_json()["packages"] == []
