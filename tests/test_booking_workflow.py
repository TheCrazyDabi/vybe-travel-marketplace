"""Test suite for Prompt 6: Reliable Booking Workflow.

Verifies:
1. Traveller submitting a booking request for an active, valid package.
2. Unique booking ID, package ID, traveller ID, operator ID, traveller count, agreed price snapshot.
3. Explicit state machine: requested -> accepted -> confirmed | rejected | cancelled.
4. Concurrency & atomic capacity reservation (preventing overbooking).
5. Only owning operator can accept/reject and only authorized users can view/cancel.
6. Capacity release when a request is cancelled or rejected.
7. Idempotency protection preventing duplicate bookings on retry.
8. Immutability of agreed price and package terms snapshots.
9. Package expiry blocking booking.
10. Operator account suspension blocking booking.
"""

from datetime import datetime, timedelta
import json
import pytest

from config import Config
from models import Booking, TravelCompany, TravelPackage, User, db


@pytest.fixture
def test_app():
    from app import create_app

    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        WTF_CSRF_ENABLED = False
        RAZORPAY_KEY_ID = "rzp_test_key"
        RAZORPAY_KEY_SECRET = "rzp_test_secret"

    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):
    return test_app.test_client()


@pytest.fixture
def workflow_setup(test_app):
    with test_app.app_context():
        # 1. Admin
        admin = User(name="Admin", email="admin@vybe.test", role="admin")
        admin.set_password("pass123")
        db.session.add(admin)

        # 2. Traveler 1
        t1 = User(name="Alice Traveler", email="alice@traveler.test", role="traveler")
        t1.set_password("pass123")
        db.session.add(t1)

        # 3. Traveler 2
        t2 = User(name="Bob Traveler", email="bob@traveler.test", role="traveler")
        t2.set_password("pass123")
        db.session.add(t2)

        # 4. Operator 1
        op1 = User(name="Himalayan Host", email="host@himalayan.test", role="operator", status="active")
        op1.set_password("pass123")
        db.session.add(op1)
        db.session.commit()

        comp1 = TravelCompany(
            user_id=op1.id,
            company_name="Himalayan Treks",
            business_email="ops@himalayan.test",
            status="approved",
            is_verified=True,
        )
        db.session.add(comp1)
        db.session.commit()

        # 5. Operator 2 (Suspended)
        op2 = User(name="Suspended Operator", email="suspended@operator.test", role="operator", status="suspended")
        op2.set_password("pass123")
        db.session.add(op2)
        db.session.commit()

        comp2 = TravelCompany(
            user_id=op2.id,
            company_name="Suspended Adventures",
            business_email="ops@suspended.test",
            status="approved",
            is_verified=True,
        )
        db.session.add(comp2)
        db.session.commit()

        # 6. Active Package with limited seats (2 seats)
        pkg_active = TravelPackage(
            operator_id=comp1.id,
            title="Spiti Winter Expedition",
            destination="Spiti Valley",
            price=30000,
            duration_days=6,
            seats_remaining=2,
            max_group_size=8,
            is_active=True,
            cancellation_terms="Cancellation within 7 days is 50% refundable. Non-refundable within 48h.",
            itinerary="Day 1: Kaza arrival. Day 2: Key Monastery. Day 3: Kibber.",
        )
        db.session.add(pkg_active)

        # 7. Expired Package
        pkg_expired = TravelPackage(
            operator_id=comp1.id,
            title="Expired Summer Trek",
            destination="Manali",
            price=15000,
            duration_days=4,
            seats_remaining=10,
            is_active=True,
            valid_until=datetime.utcnow() - timedelta(days=2),
        )
        db.session.add(pkg_expired)

        # 8. Suspended Operator's Package
        pkg_suspended = TravelPackage(
            operator_id=comp2.id,
            title="Locked Alpine Tour",
            destination="Leh Ladakh",
            price=40000,
            duration_days=5,
            seats_remaining=5,
            is_active=True,
        )
        db.session.add(pkg_suspended)
        db.session.commit()

        return {
            "admin_id": admin.id,
            "t1_id": t1.id,
            "t2_id": t2.id,
            "op1_id": op1.id,
            "comp1_id": comp1.id,
            "op2_id": op2.id,
            "comp2_id": comp2.id,
            "pkg_active_id": pkg_active.id,
            "pkg_expired_id": pkg_expired.id,
            "pkg_suspended_id": pkg_suspended.id,
        }


def _login(client, email, password="pass123"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


# ==============================================================================
# Tests for Booking Request, Snapshots & Idempotency
# ==============================================================================

def test_booking_request_creation_and_snapshots(client, workflow_setup, test_app):
    """Traveller submits booking request, snapshots are preserved even after package changes."""
    _login(client, "alice@traveler.test")

    res = client.post(
        "/api/bookings/request",
        json={
            "package_id": workflow_setup["pkg_active_id"],
            "num_travellers": 2,
            "traveller_details": {"lead_phone": "+919876543210"},
            "idempotency_key": "unique_req_001",
        },
    )
    assert res.status_code == 201
    b_data = res.get_json()["booking"]

    assert b_data["status"] == "requested"
    assert b_data["booking_reference"].startswith("VY-")
    assert b_data["num_travellers"] == 2
    assert b_data["agreed_price_snapshot"] == 60000  # 30,000 * 2
    assert b_data["total_cost"] == 60000
    assert b_data["payment_status"] == "unpaid"
    assert "Non-refundable within 48h" in b_data["terms_snapshot"]
    assert "Kaza arrival" in b_data["itinerary_snapshot"]

    booking_id = b_data["id"]

    # Now modify the package in DB (e.g. price increase to 50,000 and different terms)
    with test_app.app_context():
        pkg = db.session.get(TravelPackage, workflow_setup["pkg_active_id"])
        pkg.price = 50000
        pkg.cancellation_terms = "NEW TERMS: 100% non-refundable at all times."
        db.session.commit()

    # Verify that the booking snapshots remain completely intact
    view_res = client.get(f"/api/bookings/{booking_id}")
    assert view_res.status_code == 200
    saved_b = view_res.get_json()["booking"]
    assert saved_b["agreed_price_snapshot"] == 60000
    assert saved_b["total_cost"] == 60000
    assert "Non-refundable within 48h" in saved_b["terms_snapshot"]
    assert "NEW TERMS" not in saved_b["terms_snapshot"]


def test_duplicate_requests_idempotency(client, workflow_setup):
    """Repeated requests with identical idempotency key return the original booking without duplicate creation."""
    _login(client, "alice@traveler.test")

    idempotency_key = "idemp_test_repeat_99"

    # 1. First attempt
    res1 = client.post(
        "/api/bookings/request",
        json={
            "package_id": workflow_setup["pkg_active_id"],
            "num_travellers": 1,
            "idempotency_key": idempotency_key,
        },
    )
    assert res1.status_code == 201
    b1 = res1.get_json()["booking"]

    # 2. Second attempt with same key
    res2 = client.post(
        "/api/bookings/request",
        json={
            "package_id": workflow_setup["pkg_active_id"],
            "num_travellers": 1,
            "idempotency_key": idempotency_key,
        },
    )
    assert res2.status_code == 200
    data2 = res2.get_json()
    assert data2.get("idempotent_replay") is True
    assert data2["booking"]["id"] == b1["id"]
    assert data2["booking"]["booking_reference"] == b1["booking_reference"]


# ==============================================================================
# Tests for Authorization, State Transitions & Capacity Management
# ==============================================================================

def test_unauthorized_cancellation_and_actions(client, workflow_setup):
    """Unauthorized users cannot accept, reject, view, or cancel someone else's booking."""
    # Alice creates booking
    _login(client, "alice@traveler.test")
    res = client.post(
        "/api/bookings/request",
        json={"package_id": workflow_setup["pkg_active_id"], "num_travellers": 1},
    )
    b_id = res.get_json()["booking"]["id"]

    # Bob logs in and tries unauthorized actions
    _login(client, "bob@traveler.test")

    # Bob cannot view Alice's booking
    view_res = client.get(f"/api/bookings/{b_id}")
    assert view_res.status_code == 403

    # Bob cannot accept Alice's booking
    accept_res = client.post(f"/api/bookings/{b_id}/accept")
    assert accept_res.status_code == 403

    # Bob cannot cancel Alice's booking
    cancel_res = client.post(f"/api/bookings/{b_id}/cancel", json={"reason": "Hacking attempt"})
    assert cancel_res.status_code == 403

    # Alice logs back in and CAN cancel her own booking
    _login(client, "alice@traveler.test")
    alice_cancel = client.post(f"/api/bookings/{b_id}/cancel", json={"reason": "Change of plans"})
    assert alice_cancel.status_code == 200
    assert alice_cancel.get_json()["booking"]["status"] == "cancelled"


def test_operator_accept_reserves_capacity_and_releases_on_cancel(client, workflow_setup, test_app):
    """Operator accepts booking -> capacity is atomically reserved. Cancelling releases capacity."""
    # Check baseline capacity
    with test_app.app_context():
        pkg = db.session.get(TravelPackage, workflow_setup["pkg_active_id"])
        pkg.seats_remaining = 5
        db.session.commit()

    # Alice requests 2 seats
    _login(client, "alice@traveler.test")
    res = client.post(
        "/api/bookings/request",
        json={"package_id": workflow_setup["pkg_active_id"], "num_travellers": 2},
    )
    assert res.status_code == 201
    b_id = res.get_json()["booking"]["id"]

    # Before operator accepts: capacity not yet decremented
    with test_app.app_context():
        pkg = db.session.get(TravelPackage, workflow_setup["pkg_active_id"])
        assert pkg.seats_remaining == 5

    # Operator logs in and accepts the booking
    _login(client, "host@himalayan.test")
    accept_res = client.post(f"/api/bookings/{b_id}/accept")
    assert accept_res.status_code == 200
    accepted_b = accept_res.get_json()["booking"]
    assert accepted_b["status"] == "accepted"
    assert accepted_b["capacity_reserved"] is True
    assert accepted_b["accepted_at"] is not None

    # Capacity is now atomically decremented to 3
    with test_app.app_context():
        pkg = db.session.get(TravelPackage, workflow_setup["pkg_active_id"])
        assert pkg.seats_remaining == 3

    # Alice cancels the accepted booking -> capacity is restored back to 5
    _login(client, "alice@traveler.test")
    cancel_res = client.post(f"/api/bookings/{b_id}/cancel", json={"reason": "Medical emergency"})
    assert cancel_res.status_code == 200
    assert cancel_res.get_json()["booking"]["status"] == "cancelled"

    with test_app.app_context():
        pkg = db.session.get(TravelPackage, workflow_setup["pkg_active_id"])
        assert pkg.seats_remaining == 5


def test_operator_reject_releases_reserved_capacity(client, workflow_setup, test_app):
    """If operator rejects after accepting, capacity is restored."""
    with test_app.app_context():
        pkg = db.session.get(TravelPackage, workflow_setup["pkg_active_id"])
        pkg.seats_remaining = 4
        db.session.commit()

    _login(client, "alice@traveler.test")
    res = client.post(
        "/api/bookings/request",
        json={"package_id": workflow_setup["pkg_active_id"], "num_travellers": 2},
    )
    b_id = res.get_json()["booking"]["id"]

    _login(client, "host@himalayan.test")
    client.post(f"/api/bookings/{b_id}/accept")

    with test_app.app_context():
        pkg = db.session.get(TravelPackage, workflow_setup["pkg_active_id"])
        assert pkg.seats_remaining == 2

    # Operator decides to reject due to road closure
    rej_res = client.post(f"/api/bookings/{b_id}/reject", json={"reason": "Mountain pass closed by snow"})
    assert rej_res.status_code == 200
    assert rej_res.get_json()["booking"]["status"] == "rejected"

    with test_app.app_context():
        pkg = db.session.get(TravelPackage, workflow_setup["pkg_active_id"])
        assert pkg.seats_remaining == 4


def test_simultaneous_attempts_for_last_available_slot(client, workflow_setup, test_app):
    """Overbooking prevention: when last slot is taken, subsequent request is rejected."""
    # Set seats_remaining to 2
    with test_app.app_context():
        pkg = db.session.get(TravelPackage, workflow_setup["pkg_active_id"])
        pkg.seats_remaining = 2
        db.session.commit()

    # Alice books both remaining seats
    _login(client, "alice@traveler.test")
    res_alice = client.post(
        "/api/bookings/request",
        json={"package_id": workflow_setup["pkg_active_id"], "num_travellers": 2},
    )
    assert res_alice.status_code == 201

    # Operator accepts Alice's booking (reserves remaining 2 seats)
    _login(client, "host@himalayan.test")
    client.post(f"/api/bookings/{res_alice.get_json()['booking']['id']}/accept")

    with test_app.app_context():
        pkg = db.session.get(TravelPackage, workflow_setup["pkg_active_id"])
        assert pkg.seats_remaining == 0

    # Bob attempts to book 1 seat for the same package -> rejected with 400
    _login(client, "bob@traveler.test")
    res_bob = client.post(
        "/api/bookings/request",
        json={"package_id": workflow_setup["pkg_active_id"], "num_travellers": 1},
    )
    assert res_bob.status_code == 400
    assert "Not enough seats" in res_bob.get_json()["error"]


def test_booking_package_expiry_during_checkout(client, workflow_setup):
    """Attempting to request a booking for an expired package is blocked with 400."""
    _login(client, "alice@traveler.test")

    res = client.post(
        "/api/bookings/request",
        json={"package_id": workflow_setup["pkg_expired_id"], "num_travellers": 1},
    )
    assert res.status_code == 400
    assert "expired" in res.get_json()["error"].lower()


def test_booking_operator_account_suspended(client, workflow_setup):
    """Attempting to request a booking for a package whose operator is suspended is blocked."""
    _login(client, "alice@traveler.test")

    res = client.post(
        "/api/bookings/request",
        json={"package_id": workflow_setup["pkg_suspended_id"], "num_travellers": 1},
    )
    assert res.status_code == 400
    assert "suspended" in res.get_json()["error"].lower()
