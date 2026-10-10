"""Master upgrade tests: seed idempotency, closest matches, intelligence,
TruePrice, custom offers, trust/reviews, discover states, auth preserved."""

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
        from seed import seed_demo
        seed_demo()
    with app.test_client() as c:
        yield c


def login(c, email, pw="secret123"):
    # demo users use known passwords; seed uses traveler123 etc for demo accounts
    for candidate in (pw, "traveler123", "operator123", "admin123"):
        r = c.post("/api/auth/login", json={"email": email, "password": candidate})
        if r.status_code == 200:
            return r
    return r


def test_seed_varied_without_duplication(client):
    with client.application.app_context():
        from seed import seed_demo
        n1 = TravelPackage.query.count()
        assert n1 >= 20, f"expected 20+ sample packages, got {n1}"
        dests = {p.destination for p in TravelPackage.query.all()}
        assert len(dests) >= 10
        seed_demo()
        assert TravelPackage.query.count() == n1  # idempotent
        assert TravelPackage.query.filter_by(is_demo=True).count() == n1


def test_existing_records_preserved(client):
    with client.application.app_context():
        t = User(name="Keep", email="keep@x.com", role="traveler")
        t.set_password("secret123")
        db.session.add(t)
        db.session.commit()
        from seed import seed_demo
        seed_demo()
        u = User.query.filter_by(email="keep@x.com").first()
        assert u is not None and u.check_password("secret123")
        demo = User.query.filter_by(email="traveler@vybe.demo").first()
        assert demo.check_password("traveler123")  # password untouched


def test_arbitrary_prefs_match(client):
    login(client, "traveler@vybe.demo", "traveler123")
    r = client.get("/api/packages/recommended?max_price=30000")
    assert r.status_code == 200
    assert len(r.get_json()["packages"]) >= 5


def test_strict_impossible_explained(client):
    login(client, "traveler@vybe.demo", "traveler123")
    r = client.get("/api/packages/recommended?max_price=100&min_duration=60")
    j = r.get_json()
    assert j["packages"] == []
    assert "empty_reason" in j and j.get("suggest_widen") is True


def test_closest_matches_relax_soft_only(client):
    login(client, "traveler@vybe.demo", "traveler123")
    r = client.get("/api/packages/recommended?max_price=100&min_duration=60&closest=1")
    j = r.get_json()
    assert "relaxed" in j and "note" in j
    assert "max_price" not in j["relaxed"]  # hard ceiling preserved
    for p in j["packages"]:
        assert p["price"] <= 100


def test_contradiction_notice(client):
    login(client, "traveler@vybe.demo", "traveler123")
    client.put("/api/profile", json={"budget_per_person": 3000, "travel_style": "luxury"})
    j = client.get("/api/packages/recommended").get_json()
    assert "clarification" in j and "3,000" in j["clarification"]


def test_match_intelligence_and_reasons(client):
    from services.recommendation import apply_match_intelligence, rank_packages
    with client.application.app_context():
        pkgs = TravelPackage.query.filter_by(is_demo=True).limit(6).all()
        prefs = {"budget_per_person": 50000}
        base = rank_packages(pkgs, prefs, apply_filter=False)
        boosted = apply_match_intelligence(
            base, {"liked": [], "saved": [pkgs[0]], "passed": [], "enquired": [pkgs[1]]})
        by_id = {r["package"].id: r for r in boosted}
        assert by_id[pkgs[1].id]["score"] >= by_id[pkgs[2].id]["score"]
        assert any("saved" in x or "enquired" in x for x in by_id[pkgs[0].id]["reasons"])
        # deterministic tie-break
        again = apply_match_intelligence(
            base, {"liked": [], "saved": [pkgs[0]], "passed": [], "enquired": [pkgs[1]]})
        assert [r["package"].id for r in boosted] == [r["package"].id for r in again]


def test_trueprice_sums_and_unknowns(client):
    with client.application.app_context():
        p = TravelPackage.query.filter_by(is_demo=True).first()
        b = p.price_breakdown
        assert b is not None
        assert b["base"] + b["accommodation"] + b["transport"] + b["meals"] + b["activities"] + b["taxes"] == p.price
        assert p.price_kind == "demo_estimate"


def test_custom_offer_flow_and_isolation(client):
    login(client, "traveler@vybe.demo", "traveler123")
    pid = client.get("/api/packages").get_json()["packages"][0]["id"]
    r = client.post("/api/custom-offers", json={"package_id": pid, "num_travellers": 2})
    assert r.status_code == 201
    oid = r.get_json()["offer"]["id"]
    assert r.get_json()["offer"]["status"] == "pending"
    client.post("/api/auth/logout")
    login(client, "operator@vybe.demo", "operator123")
    r = client.post(f"/api/custom-offers/{oid}/respond",
                    json={"revised_price": 12000, "operator_note": "new dates"})
    assert r.status_code == 201
    assert r.get_json()["offer"]["version"] == 2
    client.post("/api/auth/logout")
    login(client, "traveler@vybe.demo", "traveler123")
    assert client.post(f"/api/custom-offers/{oid}/reply", json={"action": "accept"}).status_code == 200
    # another operator cannot touch it
    client.post("/api/auth/logout")
    r = client.post("/api/auth/register", json={"name": "O2", "email": "o2@x.com",
                                                 "password": "secret123", "role": "operator"})
    assert r.status_code == 201
    with client.application.app_context():
        from models import TravelCompany as TC
        other = TC(user_id=r.get_json()["user"]["id"], company_name="Other Co",
                   business_email="o2@x.com", status="approved", is_verified=True)
        db.session.add(other)
        db.session.commit()
    assert client.post(f"/api/custom-offers/{oid}/respond",
                       json={"revised_price": 1}).status_code == 403


def test_trust_badges_and_demo_labels(client):
    with client.application.app_context():
        co = TravelCompany.query.filter(TravelCompany.company_name.like("%(demo)%")).first()
        assert co is not None and co.is_demo
    login(client, "traveler@vybe.demo", "traveler123")
    pkgs = client.get("/api/packages").get_json()["packages"]
    demo = next(p for p in pkgs if p.get("is_demo"))
    assert demo["price_kind"] == "demo_estimate"


def test_review_eligibility_and_uniqueness(client):
    login(client, "traveler@vybe.demo", "traveler123")
    # no booking yet -> review rejected
    assert client.post("/api/reviews", json={"booking_id": 9999, "rating": 5}).status_code in (400, 404)
    # create enquiry->quote->confirm->review
    pid = client.get("/api/packages").get_json()["packages"][0]["id"]
    enq = client.post("/api/enquiries", json={"package_id": pid, "num_travellers": 1}).get_json()["enquiry"]
    client.post("/api/auth/logout")
    login(client, "operator@vybe.demo", "operator123")
    client.post(f"/api/enquiries/{enq['id']}/quote", json={"price_per_person": 9000})
    client.post("/api/auth/logout")
    login(client, "traveler@vybe.demo", "traveler123")
    booking = client.post(f"/api/enquiries/{enq['id']}/confirm",
                          json={"traveller_details": {"name": "T"}}).get_json()["booking"]
    assert client.post("/api/reviews", json={"booking_id": booking["id"], "rating": 6}).status_code == 400
    r = client.post("/api/reviews", json={"booking_id": booking["id"], "rating": 5, "text": "Lovely"})
    assert r.status_code == 201
    assert client.post("/api/reviews", json={"booking_id": booking["id"], "rating": 4}).status_code == 400


def test_discover_states_and_auth(client):
    assert client.get("/").status_code == 200
    r = client.get("/discover")
    assert r.status_code in (200, 302)
    login(client, "traveler@vybe.demo", "traveler123")
    assert client.get("/discover").status_code == 200
    assert client.get("/api/packages/recommended?closest=1").status_code == 200


def test_thin_queries_top_up_to_five(client):
    login(client, "traveler@vybe.demo", "traveler123")
    # refined queries always return a usable deck (auto top-up, honest note)
    for url in ("/api/packages/recommended?destination=Goa&deck=1",
                "/api/packages/recommended?destination=Hampi&deck=1",
                "/api/packages/recommended?style=luxury&deck=1",
                "/api/packages/recommended?closest=1&destination=Goa"):
        j = client.get(url).get_json()
        assert len(j["packages"]) >= 5, url
        assert "note" in j
    # bare API calls keep exact filters (no silent padding)
    assert len(client.get(
        "/api/packages/recommended?destination=Goa").get_json()["packages"]) == 2
    # ?strict=1 opts out of deck padding too
    assert len(client.get(
        "/api/packages/recommended?destination=Goa&deck=1&strict=1").get_json()["packages"]) == 2
    # impossible constraints still explained, never a crash
    j = client.get("/api/packages/recommended?max_price=100&min_duration=60").get_json()
    assert j["packages"] == [] and j.get("suggest_widen") is True


def test_original_five_preserved_with_local_covers(client):
    with client.application.app_context():
        for title in ("Ooty Heritage Toy-Train Trip", "Munnar Tea Trails Escape",
                      "Wayanad Wild & Waterfalls", "Goa Slow Coast Weekender",
                      "Jaipur Royal Heritage Rush"):
            assert TravelPackage.query.filter_by(title=title).first() is not None
        assert TravelPackage.query.filter(
            ~TravelPackage.cover_image.startswith("/static/")).count() == 0
