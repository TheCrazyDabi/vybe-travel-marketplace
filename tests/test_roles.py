"""Role-based access tests: traveler / operator / admin (spec Definition of Done)."""

import pytest

from app import create_app
from config import Config
from models import TravelCompany, TravelPackage, User, VerificationRecord, db


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        # deterministic role fixtures
        t = User(name="T", email="t@t.com", role="traveler"); t.set_password("secret123")
        o = User(name="O", email="o@o.com", role="operator"); o.set_password("secret123")
        a = User(name="A", email="a@a.com", role="admin"); a.set_password("secret123")
        p = User(name="P", email="p@p.com", role="operator"); p.set_password("secret123")
        db.session.add_all([t, o, a, p]); db.session.flush()
        approved = TravelCompany(user_id=o.id, company_name="Approved Co",
                                 business_email="o@o.com", status="approved", is_verified=True)
        pending = TravelCompany(user_id=p.id, company_name="Pending Co",
                                business_email="p@p.com", status="pending")
        db.session.add_all([approved, pending]); db.session.flush()
        db.session.add(VerificationRecord(company_id=pending.id, submitted_by=p.id))
        db.session.add(TravelPackage(operator_id=approved.id, title="Pkg", destination="Goa",
                                      price=5000, duration_days=2, is_active=True))
        db.session.commit()
    with app.test_client() as c:
        yield c


def login(c, email):
    return c.post("/api/auth/login", json={"email": email, "password": "secret123"})


def test_login_redirects_by_role(app):
    assert login(app, "t@t.com").status_code == 200
    app.post("/api/auth/logout")
    r = app.post("/login", data={"email": "a@a.com", "password": "secret123"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/admin")
    app.get("/logout")
    r = app.post("/login", data={"email": "o@o.com", "password": "secret123"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/operator")
    app.get("/logout")
    r = app.post("/login", data={"email": "t@t.com", "password": "secret123"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/discover")


def test_cross_role_blocked(app):
    login(app, "t@t.com")
    assert app.get("/operator").status_code == 403
    assert app.get("/admin").status_code == 403
    assert app.get("/api/admin/overview").status_code == 403
    app.post("/api/auth/logout")
    login(app, "o@o.com")
    assert app.get("/admin").status_code == 403
    assert app.get("/admin/verifications").status_code == 403


def test_pending_operator_cannot_publish(app):
    login(app, "p@p.com")
    r = app.post("/api/packages", json={"title": "X", "destination": "Y", "price": 100})
    assert r.status_code == 403
    r = app.get("/operator/packages/new")
    assert r.status_code == 302  # redirected to dashboard with flash


def test_approval_enables_publish_and_discovery(app):
    login(app, "a@a.com")
    recs = app.get("/api/admin/verifications").get_json()["verifications"]
    rec = next(r for r in recs if r["company_name"] == "Pending Co")
    assert app.post("/api/admin/verifications/%d/decision" % rec["id"],
                    json={"decision": "approve"}).status_code == 200
    app.post("/api/auth/logout")
    login(app, "p@p.com")
    r = app.post("/api/packages", json={"title": "New Trip", "destination": "Ooty",
                                        "price": 7000, "duration_days": 3})
    assert r.status_code == 201
    app.post("/api/auth/logout")
    login(app, "t@t.com")
    titles = [x["title"] for x in app.get("/api/packages/recommended").get_json()["packages"]]
    assert "New Trip" in titles


def test_suspend_blocks_login_and_session(app):
    login(app, "a@a.com")
    with app.application.app_context():
        uid = User.query.filter_by(email="t@t.com").first().id
    assert app.post("/api/admin/users/%d/status" % uid,
                    json={"status": "suspended", "reason": "demo"}).status_code == 200
    app.post("/api/auth/logout")
    assert login(app, "t@t.com").status_code == 403


def test_report_flow(app):
    login(app, "t@t.com")
    r = app.post("/api/reports", json={"target_type": "package", "target_id": 1,
                                       "reason": "spam", "details": "demo"})
    assert r.status_code == 201
    rep_id = r.get_json()["report"]["id"]
    app.post("/api/auth/logout")
    login(app, "a@a.com")
    assert app.get("/api/admin/reports").status_code == 200
    r = app.post("/api/admin/reports/%d/review" % rep_id,
                 json={"status": "resolved", "action_taken": "warned operator"})
    assert r.status_code == 200 and r.get_json()["report"]["status"] == "resolved"
    stats = app.get("/api/admin/overview").get_json()
    assert stats["users_total"] >= 4 and stats["packages"] >= 1


def test_admin_dashboard_renders(app):
    login(app, "a@a.com")
    assert app.get("/admin").status_code == 200
