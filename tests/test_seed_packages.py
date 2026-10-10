"""Demo expansion pack: 5 originals kept, 22 added, idempotent, wired to features."""

import pytest

from app import create_app
from config import Config
from models import Interest, TravelCompany, TravelPackage, User, db
from seed import seed_demo_packages, seed_if_empty

ORIGINALS = {
    "Ooty Heritage Toy-Train Trip", "Munnar Tea Trails Escape",
    "Wayanad Wild & Waterfalls", "Goa Slow Coast Weekender",
    "Jaipur Royal Heritage Rush",
}
NEW_TITLES = {
    "Alleppey Backwater Houseboat Escape", "Varkala Cliff & Coastal Escape",
    "Kochi Heritage & Café Trails", "Athirappilly Waterfall Adventure",
    "Kumarakom Lakeside Retreat", "Bekal Fort & Northern Coast",
    "Coorg Coffee Estate Retreat", "Gokarna Beach & Coastal Trails",
    "Hampi Ancient Kingdom Explorer", "Pondicherry French Quarter Escape",
    "Kodaikanal Misty Hills Weekend", "Mysuru Palaces & Heritage Trail",
    "Manali Mountain Adventure", "Rishikesh River & Yoga Retreat",
    "Ladakh High-Altitude Explorer", "Meghalaya Waterfalls & Living Root Bridges",
    "Sikkim Himalayan Village Escape", "Amritsar Heritage & Food Walk",
    "Andaman Island-Hopping Escape", "Sri Lanka Coastal Discovery",
    "Bali Tropical Adventure", "Dubai City & Desert Experience",
}


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    with app.app_context():
        seed_if_empty()
        added = seed_demo_packages()
        assert added == 22, f"expected 22 new packages, got {added}"
    with app.test_client() as c:
        yield c


def test_originals_preserved_and_new_added(client):
    with client.application.app_context():
        titles = {t for (t,) in db.session.query(TravelPackage.title).all()}
    assert ORIGINALS <= titles
    assert NEW_TITLES <= titles
    assert len(titles) == 27


def test_rerun_is_idempotent_and_preserves_user_data(client):
    with client.application.app_context():
        traveler = User.query.filter_by(email="traveler@vybe.demo").first()
        traveler_id, traveler_email = traveler.id, traveler.email
        pkg = TravelPackage.query.filter_by(title="Bali Tropical Adventure").first()
        pkg_id = pkg.id
        db.session.add(Interest(traveler_id=traveler_id, package_id=pkg_id, action="like"))
        pkg.price = 12345  # simulate an operator/user edit
        db.session.commit()
        n_before = TravelPackage.query.count()
    with client.application.app_context():
        assert seed_demo_packages() == 0  # nothing new on rerun
        assert TravelPackage.query.count() == n_before
        assert TravelPackage.query.filter_by(title="Bali Tropical Adventure").first().price == 12345
        assert Interest.query.filter_by(
            traveler_id=traveler_id, package_id=pkg_id, action="like").count() == 1


def test_required_fields_and_images(client):
    with client.application.app_context():
        pkgs = TravelPackage.query.all()
        assert len(pkgs) == 27
        for p in pkgs:
            assert p.title and p.destination and p.operator_id
            assert isinstance(p.price, int) and p.price > 0
            assert isinstance(p.duration_days, int) and p.duration_days >= 1
            assert p.cover_image.startswith("https://images.unsplash.com/")
            assert p.lat is not None and p.lng is not None
            assert p.is_active is True


def test_operators_approved_and_verified(client):
    with client.application.app_context():
        for p in TravelPackage.query.all():
            assert p.operator.status == "approved"
            assert p.operator.is_verified is True
            assert p.to_dict()["operator"]["is_verified"] is True
            assert p.to_dict()["availability_status"] == "Available"


def test_explore_discover_swipe_save_filter(client):
    client.post("/api/auth/login",
                json={"email": "traveler@vybe.demo", "password": "traveler123"})
    titles = [p["title"] for p in client.get("/api/packages").get_json()["packages"]]
    assert len(titles) == 27 and "Dubai City & Desert Experience" in titles
    recs = client.get("/api/packages/recommended").get_json()["packages"]
    assert any(p["title"] == "Coorg Coffee Estate Retreat" for p in recs)
    # Ladakh (24999) is correctly over-budget for the demo traveler (15000),
    # so swipe/save use in-budget packages instead
    target = next(p for p in recs if p["title"] == "Coorg Coffee Estate Retreat")
    assert client.post(f"/api/packages/{target['id']}/swipe",
                       json={"action": "like"}).status_code == 200
    saver = next(p for p in recs if p["title"] == "Varkala Cliff & Coastal Escape")
    assert client.post(f"/api/packages/{saver['id']}/save").status_code == 200
    interests = client.get("/api/interests").get_json()["interests"]
    assert {i["package_id"] for i in interests} >= {target["id"], saver["id"]}
    # swiped-away package stays excluded from later recommendations
    again = [p["id"] for p in client.get("/api/packages/recommended").get_json()["packages"]]
    assert target["id"] not in again
    # pages render with expanded data (map UI hidden -> redirects to discover,
    # coordinates stay in the API for other features)
    assert client.get("/packages").status_code == 200
    r = client.get("/map")
    assert r.status_code == 302 and r.headers["Location"].endswith("/discover")
    assert all(p["lat"] and p["lng"] for p in client.get("/api/packages").get_json()["packages"])
