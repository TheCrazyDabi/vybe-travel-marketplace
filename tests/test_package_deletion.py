"""Feature B: operator package soft-delete (archive, history preserved)."""

import pytest

from app import create_app
from config import Config
from models import TravelCompany, TravelPackage, User, db
from models.booking import Booking, Enquiry


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
        p2 = TravelPackage(operator_id=c1.id, title="P2", destination="Ooty",
                           price=6000, duration_days=3, is_active=True)
        db.session.add_all([p1, p2]); db.session.commit()
        ids = {"p1": p1.id, "p2": p2.id, "c1": c1.id, "t": t.id}
    with app.test_client() as c:
        c._ids = ids
        yield c


def login(c, email):
    return c.post("/api/auth/login", json={"email": email, "password": "pw123456"})


def test_delete_without_dependents(client):
    login(client, "o@o.com")
    r = client.post(f"/api/packages/{client._ids['p1']}/delete")
    assert r.status_code == 200 and r.get_json()["ok"]
    with client.application.app_context():
        p = TravelPackage.query.get(client._ids["p1"])
        assert p.is_deleted and not p.is_active


def test_delete_with_enquiry_and_feedback_preserved(client):
    login(client, "t@t.com")
    pid = client._ids["p1"]
    client.post(f"/api/packages/{pid}/swipe",
                json={"action": "pass", "reason": "other", "comment": "x"})
    client.post("/api/auth/logout")
    login(client, "o@o.com")
    assert client.post(f"/api/packages/{pid}/delete").status_code == 200
    with client.application.app_context():
        from models import Interest
        assert Interest.query.filter_by(package_id=pid, action="pass").count() == 1
    # Enquiry history preserved on a second package (enquiry flow removes
    # the pass by design, so use a separate package for the enquiry check).
    login(client, "t@t.com")
    pid2 = client._ids["p2"]
    client.post("/api/enquiries", json={"package_id": pid2, "num_travellers": 1})
    client.post("/api/auth/logout")
    login(client, "o@o.com")
    assert client.post(f"/api/packages/{pid2}/delete").status_code == 200
    with client.application.app_context():
        assert Enquiry.query.filter_by(package_id=pid2).count() >= 1


def test_delete_with_confirmed_booking_preserved(client):
    login(client, "t@t.com")
    pid = client._ids["p2"]
    enq = client.post("/api/enquiries", json={"package_id": pid, "num_travellers": 1}).get_json()["enquiry"]
    client.post("/api/auth/logout")
    login(client, "o@o.com")
    client.post(f"/api/enquiries/{enq['id']}/quote", json={"price_per_person": 6000})
    client.post("/api/auth/logout")
    login(client, "t@t.com")
    client.post(f"/api/enquiries/{enq['id']}/confirm", json={"traveller_details": {"name": "T"}})
    client.post("/api/auth/logout")
    login(client, "o@o.com")
    assert client.post(f"/api/packages/{pid}/delete").status_code == 200
    with client.application.app_context():
        assert Booking.query.filter_by(package_id=pid).count() == 1
        b = Booking.query.filter_by(package_id=pid).first()
        assert b.status == "confirmed"


def test_unauthorized_and_cross_operator_blocked(client):
    # unauthenticated
    assert client.post(f"/api/packages/{client._ids['p1']}/delete").status_code in (302, 401)
    login(client, "t@t.com")
    assert client.post(f"/api/packages/{client._ids['p1']}/delete").status_code == 403
    client.post("/api/auth/logout")
    login(client, "o2@o.com")
    assert client.post(f"/api/packages/{client._ids['p1']}/delete").status_code == 403


def test_deleted_excluded_from_discovery_and_enquiry_blocked(client):
    login(client, "o@o.com")
    pid = client._ids["p1"]
    client.post(f"/api/packages/{pid}/delete")
    client.post("/api/auth/logout")
    login(client, "t@t.com")
    titles = [p["title"] for p in client.get("/api/packages").get_json()["packages"]]
    assert "P1" not in titles
    assert client.post("/api/enquiries", json={"package_id": pid}).status_code == 404
