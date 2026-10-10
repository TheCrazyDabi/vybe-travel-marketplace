"""Demo catalogue seeding (current mechanism: seed_demo upsert + legacy expansion pack).

Covers: originals kept, expansion titles present, reruns add nothing,
user-created packages and interests preserved, fields valid, features wired.
"""

import json
import os

import pytest

from app import create_app
from config import Config
from models import Interest, TravelCompany, TravelPackage, User, db
from seed import seed_demo, seed_demo_packages, seed_if_empty

ORIGINALS = {
    "Ooty Heritage Toy-Train Trip", "Munnar Tea Trails Escape",
    "Wayanad Wild & Waterfalls", "Goa Slow Coast Weekender",
    "Jaipur Royal Heritage Rush",
}


def _seed_titles():
    base = os.path.join(os.path.dirname(__file__), "..", "data")
    titles = set()
    for f in ("sample_packages.json", "more_packages.json"):
        p = os.path.join(base, f)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                titles.update(x["title"] for x in json.load(fh).get("packages", []))
    return titles


SEED_TITLES = _seed_titles()


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    with app.app_context():
        seed_if_empty()
        seed_demo_packages()  # legacy pack: no-op once titles exist (idempotent)
    with app.test_client() as c:
        yield c


def _titles(client):
    with client.application.app_context():
        return {t for (t,) in db.session.query(TravelPackage.title).all()}


def test_originals_preserved_and_expansion_present(client):
    titles = _titles(client)
    assert ORIGINALS <= titles
    assert SEED_TITLES <= titles


def test_rerun_adds_nothing_and_preserves_user_data(client):
    with client.application.app_context():
        traveler = User.query.filter_by(email="traveler@vybe.demo").first()
        traveler_id = traveler.id
        co = TravelCompany.query.filter_by(status="approved").first()
        mine = TravelPackage(operator_id=co.id, title="My Custom Trek",
                             destination="Coorg", price=5000, duration_days=2,
                             is_active=True)
        db.session.add(mine)
        db.session.flush()
        mine_id = mine.id
        db.session.add(Interest(traveler_id=traveler_id, package_id=mine_id, action="like"))
        db.session.commit()
        n_before = TravelPackage.query.count()
    with client.application.app_context():
        seed_demo()
        assert seed_demo_packages() == 0  # legacy pack: nothing new
        assert TravelPackage.query.count() == n_before
        mine = TravelPackage.query.filter_by(title="My Custom Trek").first()
        assert mine is not None and mine.price == 5000  # user package untouched
        assert Interest.query.filter_by(
            traveler_id=traveler_id, package_id=mine_id, action="like").count() == 1


def test_required_fields_and_images(client):
    with client.application.app_context():
        pkgs = TravelPackage.query.all()
        assert len(pkgs) >= 27
        for p in pkgs:
            assert p.title and p.destination and p.operator_id
            assert isinstance(p.price, int) and p.price > 0
            assert isinstance(p.duration_days, int) and p.duration_days >= 1
            assert (p.cover_image or "").startswith(("http", "/static/"))
            assert p.lat is not None and p.lng is not None
            assert p.is_active is True


def test_packages_on_approved_companies(client):
    with client.application.app_context():
        demo_pkgs = TravelPackage.query.filter(
            TravelPackage.title.in_(list(SEED_TITLES))).all()
        assert demo_pkgs
        for p in demo_pkgs:
            assert p.operator.status == "approved"
            assert p.operator.is_verified is True
            assert p.to_dict()["operator"]["is_verified"] is True


def test_explore_discover_swipe_save_filter(client):
    client.post("/api/auth/login",
                json={"email": "traveler@vybe.demo", "password": "traveler123"})
    titles = [p["title"] for p in client.get("/api/packages").get_json()["packages"]]
    assert len(titles) >= 27 and "Dubai City & Desert Experience" in titles
    recs = client.get("/api/packages/recommended").get_json()["packages"]
    assert any(p["title"] == "Coorg Coffee Estate Retreat" for p in recs)
    target = next(p for p in recs if p["title"] == "Coorg Coffee Estate Retreat")
    assert client.post(f"/api/packages/{target['id']}/swipe",
                       json={"action": "like"}).status_code == 200
    saver = next(p for p in recs if p["title"] == "Varkala Cliff & Coastal Escape")
    assert client.post(f"/api/packages/{saver['id']}/save").status_code == 200
    interests = client.get("/api/interests").get_json()["interests"]
    assert {i["package_id"] for i in interests} >= {target["id"], saver["id"]}
    again = [p["id"] for p in client.get("/api/packages/recommended").get_json()["packages"]]
    assert target["id"] not in again
    assert client.get("/packages").status_code == 200
    r = client.get("/map")
    assert r.status_code == 302 and r.headers["Location"].endswith("/discover")
