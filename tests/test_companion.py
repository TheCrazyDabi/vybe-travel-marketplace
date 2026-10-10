"""Roamly companion integration: itinerary, packing, AI guide (ported behavior)."""

import pytest

from app import create_app
from config import Config
from models import PackItem, Stop, TripPlan, User, db


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    with app.app_context():
        t = User(name="T", email="t@t.com", role="traveler"); t.set_password("secret123")
        o = User(name="O", email="o@o.com", role="traveler"); o.set_password("secret123")
        db.session.add_all([t, o]); db.session.commit()
    with app.test_client() as c:
        yield c


def login(c, email="t@t.com"):
    return c.post("/api/auth/login", json={"email": email, "password": "secret123"})


def test_provision_and_pages(client):
    login(client)
    r = client.get("/api/trips/current").get_json()["trip"]
    assert r["destination"] == "Singapore" and len(r["days"]) == 5
    assert sum(len(d["stops"]) for d in r["days"]) == 11
    assert client.get("/packing").status_code == 200
    assert client.get("/companion").status_code == 200
    # itinerary page temporarily hidden -> redirects to My Trips (data/APIs intact)
    r = client.get("/trips")
    assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard")
    p = client.get("/api/packing").get_json()
    assert p["total"] == 23 and set(
        i["category"] for i in p["items"]) >= {"documents", "health"}


def test_ai_branches_and_chips(client):
    login(client)
    cases = [
        ("What should I explore near Marina Bay?", "Gardens by the Bay"),
        ("Explain the history simply", "Temasek"),
        ("What should I pack?", "Type-G"),
        ("Any precautions?", "Littering"),
        ("What can I do with three hours free?", "Bumboat"),
        ("Help reorganise, it may rain", "Cloud Forest"),
        ("Tell me about hawker food", "Choping"),
        ("What activities are planned for today?", "Day 1"),
    ]
    for q, needle in cases:
        r = client.post("/api/companion/ask", json={"message": q})
        assert r.status_code == 201, q
        body = r.get_json()["message"]
        assert needle in body["body"], (q, body["body"][:80])
        assert body["chips"], q
    r = client.post("/api/companion/ask", json={"message": "blarg nonsense xyz"})
    assert "noted your question" in r.get_json()["message"]["body"]
    assert client.post("/api/companion/ask", json={"message": "  "}).status_code == 400
    assert len(client.get("/api/companion/messages").get_json()["messages"]) >= 2 * (len(cases) + 1)


def test_visit_activity_departure(client):
    login(client)
    trip = client.get("/api/trips/current").get_json()["trip"]
    stop = trip["days"][0]["stops"][0]
    act = stop["activities"][0]
    assert client.post(f"/api/trips/stops/{stop['id']}/visit",
                       json={"visited": True}).status_code == 200
    r = client.post(f"/api/trips/activities/{act['id']}/toggle")
    assert r.get_json()["activity"]["done"] != act["done"]
    r = client.post(f"/api/trips/stops/{stop['id']}/departure")
    assert r.get_json()["stop"]["departure_ack"] is True
    assert r.get_json()["stop"]["visited"] is True


def test_packing_crud_and_isolation(client):
    login(client)
    r = client.post("/api/packing", json={"title": "Sun hat", "category": "clothing"})
    assert r.status_code == 201
    item_id = r.get_json()["item"]["id"]
    assert client.post("/api/packing", json={"title": "", "category": "x"}).status_code == 400
    assert client.post(f"/api/packing/{item_id}/toggle").get_json()["item"]["packed"] is True
    assert client.delete(f"/api/packing/{item_id}").status_code == 200
    # other traveler's data is unreachable
    client.post("/api/auth/logout")
    login(client, "o@o.com")
    with client.application.app_context():
        other_stop = Stop.query.first().id
        other_item = PackItem.query.first().id
    assert client.post(f"/api/trips/stops/{other_stop}/visit",
                       json={"visited": True}).status_code == 404
    assert client.post(f"/api/packing/{other_item}/toggle").status_code == 404


def test_requires_login(client):
    assert client.get("/packing").status_code == 302
    assert client.get("/api/trips/current").status_code == 302
    assert client.post("/api/companion/ask", json={"message": "hi"}).status_code in (302, 401)
