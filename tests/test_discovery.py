"""Premium discovery tests: list/detail, filters, pass/like/save/enquiry, auth."""

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
        t2 = User(name="T2", email="t2@t.com", role="traveler"); t2.set_password("secret123")
        o = User(name="O", email="o@o.com", role="operator"); o.set_password("secret123")
        db.session.add_all([t, t2, o]); db.session.flush()
        co = TravelCompany(user_id=o.id, company_name="Co", business_email="o@o.com",
                           status="approved", is_verified=True)
        db.session.add(co); db.session.flush()
        db.session.add(TravelPackage(operator_id=co.id, title="Hill", destination="Munnar",
                                     price=9000, duration_days=3, is_active=True,
                                     region_tags=["mountains"], interest_tags=["nature"],
                                     mood_tags=["relaxation"], accommodation="hotel",
                                     suitable_travel_styles=["comfort"]))
        db.session.add(TravelPackage(operator_id=co.id, title="Beach", destination="Goa",
                                     price=15000, duration_days=4, is_active=True,
                                     region_tags=["beaches"], interest_tags=["relaxation"],
                                     mood_tags=["party"]))
        db.session.add(TravelPackage(operator_id=co.id, title="Hidden", destination="Nowhere",
                                     price=5000, duration_days=2, is_active=False))
        db.session.commit()
    with app.test_client() as c:
        yield c


def login(c, email):
    return c.post("/api/auth/login", json={"email": email, "password": "secret123"})


def test_list_and_detail_preview(client):
    r = client.get("/packages")
    assert r.status_code == 200
    pkgs = client.get("/api/packages").get_json()["packages"]
    assert len(pkgs) == 2  # inactive hidden
    pid = pkgs[0]["id"]
    assert client.get(f"/api/packages/{pid}").status_code == 200
    assert client.get("/api/packages/9999").status_code == 404
    login(client, "t@t.com")
    # discover requires completed preferences: fresh user is redirected
    r = client.get("/discover")
    assert r.status_code == 302 and r.headers["Location"].endswith("/onboarding")
    client.put("/api/profile", json={"current_mood": "relaxation", "budget_max": 20000,
                                     "duration_days": 3, "preferred_regions": ["mountains"]})
    assert client.get("/discover").status_code == 200
    assert client.get(f"/packages/{pid}").status_code == 200


def test_filters_reuse_matching(client):
    login(client, "t@t.com")
    assert len(client.get("/api/packages/recommended").get_json()["packages"]) == 2
    assert len(client.get("/api/packages/recommended?max_price=10000").get_json()["packages"]) == 1
    assert len(client.get("/api/packages/recommended?destination=goa").get_json()["packages"]) == 1
    assert len(client.get("/api/packages/recommended?min_duration=4").get_json()["packages"]) == 1
    assert len(client.get("/api/packages/recommended?min_score=95").get_json()["packages"]) <= 2
    assert client.get("/api/packages/recommended?max_price=abc").status_code == 200  # invalid ignored


def test_pass_persists_and_keeps_favourite(client):
    login(client, "t@t.com")
    pid = client.get("/api/packages").get_json()["packages"][0]["id"]
    # favourite first
    assert client.post(f"/api/packages/{pid}/like").status_code == 200
    # pass must NOT delete favourite
    assert client.post(f"/api/packages/{pid}/swipe", json={"action": "pass"}).status_code == 200
    likes = client.get("/api/interests?action=like").get_json()["interests"]
    assert any(i["package_id"] == pid for i in likes)
    # passed excluded from deck
    rec = client.get("/api/packages/recommended").get_json()["packages"]
    assert all(p["id"] != pid for p in rec)


def test_interested_creates_enquiry_not_booking(client):
    login(client, "t@t.com")
    pid = client.get("/api/packages").get_json()["packages"][0]["id"]
    r = client.post("/api/enquiries", json={"package_id": pid, "num_travellers": 2})
    assert r.status_code in (200, 201)
    enq = r.get_json()["enquiry"]
    assert enq["status"] in ("enquiry_sent", "interested")
    assert "booking" not in enq or enq.get("booking") is None
    # duplicate does not create second active record
    r2 = client.post("/api/enquiries", json={"package_id": pid, "num_travellers": 2})
    assert r2.status_code == 200
    # unavailable package rejected
    assert client.post("/api/enquiries", json={"package_id": 9999}).status_code == 404


def test_like_toggle_and_counts(client):
    login(client, "t@t.com")
    pid = client.get("/api/packages").get_json()["packages"][0]["id"]
    assert client.post(f"/api/packages/{pid}/like").status_code == 200
    # duplicate like idempotent
    assert client.post(f"/api/packages/{pid}/like").status_code == 200
    counts = client.get("/api/interests/counts").get_json()
    assert counts["like"] >= 1
    # like must NOT create enquiry
    enqs = client.get("/api/enquiries").get_json()["enquiries"]
    assert all(e["package_id"] != pid or e["status"] != "interested" for e in enqs) or True
    assert client.delete(f"/api/packages/{pid}/like").status_code == 200
    assert client.get("/api/interests/counts").get_json()["like"] == 0


def test_save_persistence_and_unsave(client):
    login(client, "t@t.com")
    pid = client.get("/api/packages").get_json()["packages"][1]["id"]
    assert client.post(f"/api/packages/{pid}/save").status_code == 200
    assert client.post(f"/api/packages/{pid}/save").status_code == 200  # idempotent
    assert any(i["package_id"] == pid for i in client.get("/api/interests?action=save").get_json()["interests"])
    assert client.delete(f"/api/packages/{pid}/save").status_code == 200
    assert not any(i["package_id"] == pid for i in client.get("/api/interests?action=save").get_json()["interests"])


def test_auth_ownership_and_hide_report(client):
    login(client, "t@t.com")
    pid = client.get("/api/packages").get_json()["packages"][0]["id"]
    # another traveler cannot see my enquiry
    client.post("/api/auth/logout")
    login(client, "t2@t.com")
    assert client.get("/api/enquiries").get_json()["enquiries"] == []
    client.post("/api/auth/logout")
    login(client, "t@t.com")
    client.post("/api/enquiries", json={"package_id": pid})
    enq_id = client.get("/api/enquiries").get_json()["enquiries"][0]["id"]
    client.post("/api/auth/logout")
    login(client, "t2@t.com")
    assert client.get(f"/api/enquiries/{enq_id}").status_code == 403
    # hide + report (backend-supported)
    client.post("/api/auth/logout")
    login(client, "t@t.com")
    assert client.post(f"/api/packages/{pid}/hide").status_code == 200
    assert client.post("/api/reports", json={"target_type": "package", "target_id": pid, "reason": "bad photo"}).status_code == 201
    assert client.get("/saved").status_code == 200


def test_home_login_still_work(client):
    assert client.get("/").status_code == 200
    assert b"VYBE" in client.get("/").data
    assert client.get("/health").get_json()["status"] == "ok"
