"""Phase 2 tests: onboarding, packages, matching, swipes, enquiries, auth."""

import pytest

from app import create_app
from config import Config
from models import TravelCompany, TravelPackage, User, db


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture()
def app_client():
    app = create_app(TestConfig)
    with app.app_context():
        t = User(name="Trav", email="trav@t.com", role="traveler"); t.set_password("secret123")
        o = User(name="Oper", email="oper@o.com", role="operator"); o.set_password("secret123")
        a = User(name="Adm", email="adm@a.com", role="admin"); a.set_password("secret123")
        db.session.add_all([t, o, a]); db.session.flush()
        co = TravelCompany(user_id=o.id, company_name="Co", business_email="oper@o.com",
                           status="approved", is_verified=True)
        db.session.add(co); db.session.flush()
        db.session.add(TravelPackage(operator_id=co.id, title="Hill Escape", destination="Munnar",
                                     price=9000, duration_days=3, is_active=True,
                                     region_tags=["mountains"], scenery_tags=["mountains"],
                                     interest_tags=["nature"], activities=["trekking"],
                                     climate_tags=["cool"], mood_tags=["relaxation"],
                                     min_group_size=2, max_group_size=12, capacity=20, seats_remaining=10))
        db.session.add(TravelPackage(operator_id=co.id, title="Beach Party", destination="Goa",
                                     price=50000, duration_days=5, is_active=True,
                                     region_tags=["beaches"], interest_tags=["nightlife"],
                                     mood_tags=["party"]))
        db.session.commit()
    with app.test_client() as c:
        yield c


def login(c, email):
    return c.post("/api/auth/login", json={"email": email, "password": "secret123"})


def test_onboarding_persistence(app_client):
    login(app_client, "trav@t.com")
    r = app_client.put("/api/profile", json={
        "travel_moods": ["adventure"], "travel_pace": "balanced",
        "destination_prefs": ["hills and mountains"], "activity_prefs": ["trekking"],
        "budget_per_person": 12000, "num_travellers": 2, "travel_style": "comfort",
        "ideal_trip_text": "slow tea gardens",
    })
    assert r.status_code == 200
    prof = r.get_json()["profile"]
    assert "adventure" in prof["travel_moods"]
    assert prof["budget_per_person"] == 12000
    # legacy HTML POST still works
    r = app_client.post("/onboarding", data={"budget_max": "14000", "duration_days": "4"})
    assert r.status_code == 200


def test_package_validation_and_ownership(app_client):
    login(app_client, "oper@o.com")
    # negative price rejected
    r = app_client.post("/api/packages", json={"title": "Bad", "destination": "X", "price": -5})
    assert r.status_code == 400
    # min > max rejected
    r = app_client.post("/api/packages", json={"title": "Bad2", "destination": "Y", "price": 100,
                                                "min_group_size": 10, "max_group_size": 2})
    assert r.status_code == 400
    # valid with new fields
    r = app_client.post("/api/packages", json={"title": "Good", "destination": "Ooty", "price": 7000,
                                                "duration_days": 3, "min_group_size": 2, "max_group_size": 10,
                                                "suitable_groups": ["family"], "capacity": 20})
    assert r.status_code == 201
    pkg_id = r.get_json()["package"]["id"]
    # traveler cannot edit operator package
    app_client.post("/api/auth/logout")
    login(app_client, "trav@t.com")
    r = app_client.put(f"/api/packages/{pkg_id}", json={"price": 1})
    assert r.status_code == 403


def test_matching_weights_and_filter(app_client):
    from services.recommendation import MATCH_WEIGHTS, filter_packages, score_package
    from types import SimpleNamespace
    assert abs(sum(MATCH_WEIGHTS.values()) - 1.0) < 1e-6
    assert MATCH_WEIGHTS["budget"] == 0.25
    pkg = SimpleNamespace(
        interest_tags=["nature"], activities=["trekking"], region_tags=["mountains"],
        scenery_tags=["mountains"], climate_tags=["cool"], mood_tags=["relaxation"],
        accommodation="3-star hotel", suitable_travel_styles=["comfort"],
        suitable_groups=["friends"], price=9000, duration_days=3,
        destination="Munnar", is_active=True, max_group_size=12, capacity=20,
        seats_remaining=10, min_group_size=1,
    )
    prefs = {"budget_per_person": 10000, "destination_prefs": ["hills and mountains"],
             "preferred_regions": ["mountains"], "activity_prefs": ["trekking"],
             "interests": ["nature"], "travel_moods": ["relaxation"], "current_mood": "relaxation",
             "accommodation_prefs": ["hotel"], "travel_style": "comfort",
             "group_type": "friends", "num_travellers": 2, "duration_days": 3}
    score, reasons, _ = score_package(pkg, prefs)
    assert score > 50 and reasons
    # hard filter: over budget + flex excluded
    pkgs = [SimpleNamespace(price=50000, is_active=True, destination="Goa",
                            max_group_size=None, capacity=None, seats_remaining=None)]
    kept, excluded = filter_packages(pkgs, {"budget_per_person": 10000, "budget_flex_pct": 10})
    assert len(kept) == 0 and excluded


def test_swipe_save_undo_persistence(app_client):
    login(app_client, "trav@t.com")
    pkgs = app_client.get("/api/packages/recommended").get_json()["packages"]
    assert pkgs
    pid = pkgs[0]["id"]
    assert app_client.post(f"/api/packages/{pid}/swipe", json={"action": "like"}).status_code == 200
    # duplicate like idempotent
    assert app_client.post(f"/api/packages/{pid}/swipe", json={"action": "like"}).status_code == 200
    # save + unsave
    assert app_client.post(f"/api/packages/{pid}/save").status_code == 200
    assert app_client.delete(f"/api/packages/{pid}/save").status_code == 200
    # undo removes like
    assert app_client.post(f"/api/packages/{pid}/undo").status_code == 200
    # invalid action
    assert app_client.post(f"/api/packages/{pid}/swipe", json={"action": "bogus"}).status_code == 400


def test_enquiry_quote_confirm_flow(app_client):
    login(app_client, "trav@t.com")
    pkg_id = app_client.get("/api/packages").get_json()["packages"][0]["id"]
    r = app_client.post("/api/enquiries", json={"package_id": pkg_id, "num_travellers": 2})
    assert r.status_code in (200, 201)
    enq_id = r.get_json()["enquiry"]["id"]
    app_client.post("/api/auth/logout")
    login(app_client, "oper@o.com")
    r = app_client.post(f"/api/enquiries/{enq_id}/quote",
                        json={"price_per_person": 9500, "message": "Available!"})
    assert r.status_code == 201
    # negative quote rejected
    assert app_client.post(f"/api/enquiries/{enq_id}/quote",
                           json={"price_per_person": -1}).status_code == 400
    app_client.post("/api/auth/logout")
    login(app_client, "trav@t.com")
    r = app_client.post(f"/api/enquiries/{enq_id}/confirm",
                        json={"traveller_details": {"name": "Trav", "phone": "123"}})
    assert r.status_code == 201
    assert r.get_json()["booking"]["payment_status"] == "simulated_pending"
    # booking listed in dashboard API
    assert app_client.get("/api/bookings").status_code == 200
    # unauthorized: operator cannot confirm traveller enquiry as traveller-only
    app_client.post("/api/auth/logout")
    login(app_client, "oper@o.com")
    # operator viewing other's enquiry list is scoped (should not include traveller private? here operator owns company so allowed to view)
    assert app_client.get(f"/api/enquiries/{enq_id}").status_code == 200


def test_role_auth_and_invalid(app_client):
    login(app_client, "trav@t.com")
    assert app_client.get("/operator").status_code == 403
    assert app_client.get("/api/admin/overview").status_code == 403
    # invalid status transition: confirm without quote on fresh expensive package
    pkgs = app_client.get("/api/packages").get_json()["packages"]
    # create enquiry then cancel then try confirm -> 400
    pid = pkgs[0]["id"]
    r = app_client.post("/api/enquiries", json={"package_id": pid, "num_travellers": 1})
    eid = r.get_json()["enquiry"]["id"]
    app_client.post(f"/api/enquiries/{eid}/cancel")
    r = app_client.post(f"/api/enquiries/{eid}/confirm", json={"traveller_details": {}})
    assert r.status_code == 400
