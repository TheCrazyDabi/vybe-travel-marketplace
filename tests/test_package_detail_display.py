"""Tests for VYBE Package Details Display Behavior & Acceptance Criteria:
1. Complete package details in API and view
2. Availability and expiry state accuracy
3. Booking & Enquiry validation against package state
4. Safe fallbacks for missing optional information
"""

import os
from datetime import datetime, timedelta, timezone
import pytest

from app import create_app
from config import Config
from models import TravelCompany, TravelPackage, User, db
from models.booking import Enquiry


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    SERVER_NAME = "localhost"


@pytest.fixture
def app_and_client():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()

        # Create operator & company
        op_user = User(name="Alpine Ops", email="op_detail@vybe.test", role="operator", is_email_verified=True)
        op_user.set_password("Operator123!")
        db.session.add(op_user)
        db.session.flush()

        company = TravelCompany(
            user_id=op_user.id,
            company_name="Alpine Voyages",
            is_verified=True,
            status="approved",
            business_email="ops@alpinevoyages.test"
        )
        db.session.add(company)
        db.session.flush()

        # Create traveler
        traveler = User(name="Jane Traveler", email="traveler_detail@vybe.test", role="traveler", is_email_verified=True)
        traveler.set_password("Traveler123!")
        db.session.add(traveler)
        db.session.flush()

        now = datetime.utcnow()
        # 1. Active, fully populated package
        pkg_active = TravelPackage(
            operator_id=company.id,
            title="Kashmir Winter Wonderland",
            destination="Gulmarg, Kashmir",
            cover_image="https://images.unsplash.com/photo-1548013146-72479768bada",
            duration_days=6,
            nights=5,
            price=32000,
            currency="INR",
            price_breakdown={
                "base": 18000,
                "accommodation": 7000,
                "transport": 3000,
                "meals": 2500,
                "activities": 1500,
                "taxes": 0,
            },
            price_kind="operator_quote",
            short_desc="Pristine powder snow, gondola rides and cozy pine chalets.",
            itinerary="Day 1: Arrival in Srinagar\nDay 2: Gulmarg Gondola Phase 1 & 2\nDay 3: Heli-skiing\nDay 4: Snowshoeing\nDay 5: Dal lake shikara\nDay 6: Departure",
            included=["Gondola passes", "Breakfast and dinner", "Chauffeured 4x4", "Ski equipment rental"],
            excluded=["Airfare", "Personal snow gear", "Lunches"],
            accommodation="Pine Palace Resort (4-star heated)",
            transportation="Private 4x4 Scorpio with snow chains",
            capacity=12,
            seats_remaining=4,
            group_size="4-12 people",
            trip_start_date=now + timedelta(days=20),
            trip_end_date=now + timedelta(days=26),
            booking_deadline=now + timedelta(days=15),
            valid_until=now + timedelta(days=15),
            cancellation_terms="Full refund up to 7 days before departure.",
            status="active",
            is_active=True
        )
        db.session.add(pkg_active)

        # 2. Expired package
        pkg_expired = TravelPackage(
            operator_id=company.id,
            title="Autumn Colors in Manali",
            destination="Manali, Himachal Pradesh",
            cover_image="https://images.unsplash.com/photo-1506744038136-46273834b3fb",
            duration_days=4,
            nights=3,
            price=15000,
            currency="INR",
            short_desc="Past trip in autumn.",
            itinerary="Day 1-4: Rohtang pass and Solang valley",
            capacity=10,
            seats_remaining=0,
            valid_until=now - timedelta(days=2),
            booking_deadline=now - timedelta(days=5),
            status="expired",
            is_active=False
        )
        db.session.add(pkg_expired)
        db.session.commit()

        yield app, app.test_client(), op_user.id, traveler.id, pkg_active.id, pkg_expired.id
        db.session.remove()
        db.drop_all()


def test_package_detail_api_completeness(app_and_client):
    app, client, _, _, active_id, _ = app_and_client
    res = client.get(f"/api/packages/{active_id}")
    assert res.status_code == 200
    data = res.get_json()
    assert "package" in data
    pkg = data["package"]

    # Verify all required fields from Requirement 2
    assert pkg["title"] == "Kashmir Winter Wonderland"
    assert pkg["destination"] == "Gulmarg, Kashmir"
    assert "cover_image" in pkg and pkg["cover_image"].startswith("http")
    assert pkg["duration_days"] == 6
    assert pkg["nights"] == 5
    assert pkg["price"] == 32000
    assert pkg["operator"]["company_name"] == "Alpine Voyages"
    assert pkg["operator"]["is_verified"] is True
    assert pkg["availability_status"] == "Available"
    assert pkg["seats_remaining"] == 4
    assert pkg["capacity"] == 12
    assert "Pristine powder snow" in pkg["short_desc"]
    assert "Gondola Phase 1 & 2" in pkg["itinerary"]
    assert "Gondola passes" in pkg["included"]
    assert "Airfare" in pkg["excluded"]
    assert "Pine Palace" in pkg["accommodation"]
    assert "4x4" in pkg["transportation"]
    assert pkg["trip_start_date"] is not None
    assert pkg["trip_end_date"] is not None
    assert pkg["booking_deadline"] is not None
    assert pkg["valid_until"] is not None
    assert pkg["is_bookable"] is True

    # TruePrice breakdown
    assert pkg["price_breakdown"]["base"] == 18000
    assert pkg["price_breakdown"]["accommodation"] == 7000


def test_expired_package_behavior(app_and_client):
    app, client, _, traveler_id, _, expired_id = app_and_client
    res = client.get(f"/api/packages/{expired_id}")
    assert res.status_code == 200
    pkg = res.get_json()["package"]

    assert pkg["status"] == "expired"
    assert pkg["is_bookable"] is False
    assert pkg["availability_status"] in ("Sold out / Hidden", "Expired")

    # Enquiries against expired package must be rejected
    login_res = client.post("/api/auth/login", json={"email": "traveler_detail@vybe.test", "password": "Traveler123!"})
    assert login_res.status_code == 200

    enq_res = client.post("/api/enquiries", json={"package_id": expired_id, "num_travellers": 2})
    assert enq_res.status_code in (400, 404)
    err = enq_res.get_json()["error"].lower()
    assert any(term in err for term in ("expired", "unavailable", "not available"))


def test_html_detail_page_renders_with_details(app_and_client):
    app, client, _, _, active_id, _ = app_and_client
    res = client.get(f"/packages/{active_id}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    assert "Kashmir Winter Wonderland" in html
    assert "Gulmarg, Kashmir" in html
    assert "32,000" in html
    assert "Alpine Voyages" in html
    assert "Back to trips" in html
    assert "TruePrice" in html
    assert "Itinerary" in html
    assert "Gondola passes" in html
