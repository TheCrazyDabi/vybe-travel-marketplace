"""Feature A: traveller rejection feedback + operator visibility."""

import pytest

from app import create_app
from config import Config
from models import Interest, TravelCompany, TravelPackage, User, db


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    with app.app_context():
        t = User(name="T", email="t@t.com", role="traveler"); t.set_password("pw123456")
        o = User(name="O", email="o@o.com", role="operator"); o.set_password("pw123456")
        o2 = User(name="O2", email="o2@o.com", role="operator"); o2.set_password("pw123456")
        db.session.add_all([t, o, o2]); db.session.flush()
        c1 = TravelCompany(user_id=o.id, company_name="C1", business_email="o@o.com",
                           status="approved", is_verified=True)
        c2 = TravelCompany(user_id=o2.id, company_name="C2", business_email="o2@o.com",
                           status="approved", is_verified=True)
        db.session.add_all([c1, c2]); db.session.flush()
        p1 = TravelPackage(operator_id=c1.id, title="P1", destination="Goa",
                           price=5000, duration_days=2, is_active=True)
        p2 = TravelPackage(operator_id=c2.id, title="P2", destination="Ooty",
                           price=6000, duration_days=3, is_active=True)
        db.session.add_all([p1, p2]); db.session.commit()
        ids = {"pkg1": p1.id, "pkg2": p2.id}
    with app.test_client() as c:
        c._ids = ids
        yield c


def login(c, email):
    return c.post("/api/auth/login", json={"email": email, "password": "pw123456"})


def test_pass_without_feedback_ok_skip(client):
    login(client, "t@t.com")
    r = client.post(f"/api/packages/{client._ids['pkg1']}/swipe", json={"action": "pass"})
    assert r.status_code == 200
    with client.application.app_context():
        row = Interest.query.filter_by(action="pass").first()
        assert row is not None and row.reason is None


def test_feedback_submission(client):
    login(client, "t@t.com")
    r = client.post(f"/api/packages/{client._ids['pkg1']}/swipe",
                    json={"action": "pass", "reason": "too_expensive", "comment": "over budget"})
    assert r.status_code == 200
    with client.application.app_context():
        row = Interest.query.filter_by(action="pass").first()
        assert row.reason == "too_expensive" and row.comment == "over budget"


def test_invalid_feedback_rejected(client):
    login(client, "t@t.com")
    r = client.post(f"/api/packages/{client._ids['pkg1']}/swipe",
                    json={"action": "pass", "reason": "bogus"})
    assert r.status_code == 400
    r = client.post(f"/api/packages/{client._ids['pkg1']}/swipe",
                    json={"action": "pass", "reason": "too_expensive", "comment": "x" * 501})
    assert r.status_code == 400


def test_duplicate_retry_idempotent(client):
    login(client, "t@t.com")
    pid = client._ids["pkg1"]
    assert client.post(f"/api/packages/{pid}/swipe",
                       json={"action": "pass", "reason": "other", "comment": "hi"}).status_code == 200
    assert client.post(f"/api/packages/{pid}/swipe",
                       json={"action": "pass", "reason": "other", "comment": "hi"}).status_code == 200
    with client.application.app_context():
        from models import User as U
        t = U.query.filter_by(email="t@t.com").first()
        n = Interest.query.filter_by(traveler_id=t.id, package_id=pid, action="pass").count()
        assert n == 1


def test_operator_feedback_visibility_and_cross_operator_blocked(client):
    login(client, "t@t.com")
    client.post(f"/api/packages/{client._ids['pkg1']}/swipe",
                json={"action": "pass", "reason": "activities", "comment": "no trek"})
    client.post("/api/auth/logout")
    login(client, "o@o.com")
    r = client.get("/api/operator/feedback")
    assert r.status_code == 200
    assert any(f["reason"] == "activities" for f in r.get_json()["feedback"])
    assert client.get("/operator").status_code == 200
    client.post("/api/auth/logout")
    login(client, "o2@o.com")
    r = client.get("/api/operator/feedback")
    assert r.get_json()["feedback"] == []
