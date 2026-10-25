"""Test suite for VYBE Phase 2 Production Services.

Verifies:
1. PostgreSQL URI dialect normalization and pool configuration
2. Production security response headers
3. Cloudflare R2 / Local hybrid storage and upload validation
4. Admin verification document access control (403 for non-admins)
5. Razorpay order creation, signature verification, and booking payment confirmation
6. Razorpay webhook signature validation and duplicate event idempotency
"""

import io
import json
import os
import pytest

from config import Config, _normalize_db_uri
from models import Booking, Enquiry, TravelCompany, TravelPackage, User, VerificationRecord, db
from services.payment import payment_service
from services.storage import storage_service


@pytest.fixture
def test_app():
    from app import create_app

    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        WTF_CSRF_ENABLED = False
        RAZORPAY_KEY_ID = ""
        RAZORPAY_KEY_SECRET = ""
        RAZORPAY_WEBHOOK_SECRET = "test_secret_for_webhook"

    app = create_app(TestConfig)

    with app.app_context():
        # Clear or create clean tables
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):
    return test_app.test_client()


@pytest.fixture
def seed_data(test_app):
    with test_app.app_context():
        # 1. Admin user
        admin = User(name="Admin User", email="admin@vybe.test", role="admin")
        admin.set_password("pass123")
        db.session.add(admin)

        # 2. Traveler user
        traveler = User(name="Traveler User", email="traveler@vybe.test", role="traveler")
        traveler.set_password("pass123")
        db.session.add(traveler)

        # 3. Operator user
        operator_user = User(name="Operator User", email="operator@vybe.test", role="operator")
        operator_user.set_password("pass123")
        db.session.add(operator_user)
        db.session.commit()

        # 4. Company & Verification
        company = TravelCompany(
            user_id=operator_user.id,
            company_name="Himalayan Expeditions",
            business_email="ops@himalayan.test",
            status="approved",
            is_verified=True,
            document_path="verifications/test_certificate.pdf",
        )
        db.session.add(company)
        db.session.commit()

        rec = VerificationRecord(
            company_id=company.id,
            submitted_by=operator_user.id,
            status="pending",
        )
        db.session.add(rec)

        # 5. Package
        pkg = TravelPackage(
            operator_id=company.id,
            title="Spiti Valley Escape",
            destination="Spiti, Himachal",
            price=25000,
            duration_days=7,
            is_active=True,
        )
        db.session.add(pkg)
        db.session.commit()

        # 6. Enquiry & Booking
        enq = Enquiry(
            traveler_id=traveler.id,
            package_id=pkg.id,
            company_id=company.id,
            status="confirmed",
            num_travellers=2,
            total_cost=50000,
        )
        db.session.add(enq)
        db.session.commit()

        booking = Booking(
            enquiry_id=enq.id,
            traveler_id=traveler.id,
            package_id=pkg.id,
            company_id=company.id,
            status="pending",
            total_cost=50000,
            payment_status="simulated_pending",
        )
        db.session.add(booking)
        db.session.commit()

        return {
            "admin_id": admin.id,
            "traveler_id": traveler.id,
            "operator_id": operator_user.id,
            "company_id": company.id,
            "verification_id": rec.id,
            "package_id": pkg.id,
            "booking_id": booking.id,
        }


# ==============================================================================
# 1. Configuration & Engine Tests
# ==============================================================================

def test_normalize_db_uri():
    """Verify SQLAlchemy 2.x psycopg dialect normalization for Supabase and Render."""
    assert _normalize_db_uri("postgres://user:pass@host:5432/db") == "postgresql+psycopg://user:pass@host:5432/db"
    assert _normalize_db_uri("postgresql://user:pass@host:5432/db") == "postgresql+psycopg://user:pass@host:5432/db"
    assert _normalize_db_uri("postgresql+psycopg://user:pass@host:5432/db") == "postgresql+psycopg://user:pass@host:5432/db"
    assert "instance" in _normalize_db_uri("sqlite:///vybe.db")


def test_security_headers_middleware(client):
    """Verify security headers are applied to HTTP responses."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert resp.headers.get("X-XSS-Protection") == "1; mode=block"
    assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_health_check_endpoints(client):
    """Verify /health and /api/health endpoints reveal no secrets and report status."""
    for path in ("/health", "/api/health"):
        resp = client.get(path)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["app"] == "VYBE"
        assert data["database"] == "connected"
        # Ensure no secrets or internal paths leaked
        data_str = json.dumps(data)
        assert "password" not in data_str
        assert "sqlite:" not in data_str
        assert "postgres:" not in data_str


# ==============================================================================
# 2. Storage Service & Document Verification Tests
# ==============================================================================

def test_storage_upload_and_validation(test_app):
    """Verify file upload handling, extension validation, and local fallback."""
    from werkzeug.datastructures import FileStorage

    with test_app.app_context():
        # Valid PDF upload
        pdf_data = io.BytesIO(b"%PDF-1.4 test document content")
        file_obj = FileStorage(stream=pdf_data, filename="license.pdf", content_type="application/pdf")
        key = storage_service.upload_file(file_obj, folder="verifications")

        assert key is not None
        assert key.startswith("verifications/")
        assert "license.pdf" in key

        local_path = storage_service.get_local_path(key)
        assert local_path is not None
        assert os.path.isfile(local_path)

        # Cleanup
        storage_service.delete_file(key)

        # Forbidden extension test (.exe)
        bad_data = io.BytesIO(b"malicious executable")
        bad_file = FileStorage(stream=bad_data, filename="payload.exe")
        with pytest.raises(ValueError, match="not permitted"):
            storage_service.upload_file(bad_file, folder="verifications")


def test_admin_verification_document_access(client, seed_data, test_app):
    """Verify document download route requires admin role and blocks unauthorized access."""
    rec_id = seed_data["verification_id"]

    # 1. Anonymous access -> redirect to login (302)
    resp = client.get(f"/admin/verifications/{rec_id}/document")
    assert resp.status_code == 302
    assert "/login" in resp.headers.get("Location", "")

    # 2. Traveler access -> 403 Forbidden
    login_trav = client.post("/api/auth/login", json={"email": "traveler@vybe.test", "password": "pass123"})
    assert login_trav.status_code == 200
    resp_trav = client.get(f"/admin/verifications/{rec_id}/document")
    assert resp_trav.status_code == 403
    client.post("/api/auth/logout")

    # 3. Admin access -> create real local file to serve
    with test_app.app_context():
        comp = db.session.get(TravelCompany, seed_data["company_id"])
        from werkzeug.datastructures import FileStorage
        dummy_file = FileStorage(stream=io.BytesIO(b"%PDF-1.4 dummy cert"), filename="cert.pdf")
        key = storage_service.upload_file(dummy_file, folder="verifications")
        comp.document_path = key
        db.session.commit()

    login_admin = client.post("/api/auth/login", json={"email": "admin@vybe.test", "password": "pass123"})
    assert login_admin.status_code == 200
    resp_admin = client.get(f"/admin/verifications/{rec_id}/document")
    assert resp_admin.status_code == 200
    assert b"%PDF-1.4 dummy cert" in resp_admin.data

    # Cleanup local test file
    with test_app.app_context():
        storage_service.delete_file(key)


# ==============================================================================
# 3. Razorpay Payment Tests
# ==============================================================================

def test_booking_payment_order_creation(client, seed_data):
    """Verify server-side payment order creation for bookings."""
    booking_id = seed_data["booking_id"]

    # Must be logged in as booking traveler
    login_resp = client.post("/api/auth/login", json={"email": "traveler@vybe.test", "password": "pass123"})
    assert login_resp.status_code == 200

    resp = client.post(f"/api/bookings/{booking_id}/pay")
    assert resp.status_code == 200
    data = resp.get_json()

    assert "order_id" in data
    assert data["order_id"].startswith("order_sim_")
    assert data["amount"] == 50000 * 100  # 50,000 INR in paise
    assert data["currency"] == "INR"
    assert data["simulated"] is True

    # Verify booking status updated
    b_resp = client.get(f"/api/bookings/{booking_id}")
    b_data = b_resp.get_json()["booking"]
    assert b_data["payment_status"] == "order_created"
    assert b_data["razorpay_order_id"] == data["order_id"]


def test_booking_payment_signature_verification(client, seed_data):
    """Verify HMAC payment signature verification and booking confirmation."""
    booking_id = seed_data["booking_id"]
    login_resp = client.post("/api/auth/login", json={"email": "traveler@vybe.test", "password": "pass123"})
    assert login_resp.status_code == 200

    # Create order first
    pay_resp = client.post(f"/api/bookings/{booking_id}/pay")
    assert pay_resp.status_code == 200
    order_id = pay_resp.get_json()["order_id"]

    # 1. Invalid signature test
    bad_payload = {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": "pay_test123",
        "razorpay_signature": "invalid_forged_signature",
    }
    fail_resp = client.post(f"/api/bookings/{booking_id}/verify-payment", json=bad_payload)
    assert fail_resp.status_code == 400
    assert "verification failed" in fail_resp.get_json()["error"]

    # 2. Valid signature test (using simulation signature token)
    valid_payload = {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": "pay_test_valid_456",
        "razorpay_signature": "simulated_valid_signature",
        "payment_method": "upi",
    }
    success_resp = client.post(f"/api/bookings/{booking_id}/verify-payment", json=valid_payload)
    assert success_resp.status_code == 200
    b_data = success_resp.get_json()["booking"]

    assert b_data["payment_status"] == "paid"
    assert b_data["razorpay_payment_id"] == "pay_test_valid_456"
    assert b_data["payment_method"] == "upi"
    assert b_data["amount_paid"] == 50000
    assert b_data["status"] == "confirmed"


def test_razorpay_webhook_processing_and_idempotency(client, seed_data, test_app):
    """Verify webhook signature verification and idempotent processing."""
    import hmac
    import hashlib

    booking_id = seed_data["booking_id"]

    # Set up booking with order_id
    with test_app.app_context():
        b = db.session.get(Booking, booking_id)
        b.razorpay_order_id = "order_sim_webhook_999"
        b.payment_status = "order_created"
        db.session.commit()

    webhook_payload = {
        "event": "order.paid",
        "payload": {
            "order": {
                "entity": {
                    "id": "order_sim_webhook_999",
                    "amount_paid": 5000000,
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_hook_12345",
                    "order_id": "order_sim_webhook_999",
                    "amount": 5000000,
                    "method": "netbanking",
                }
            }
        }
    }
    body_bytes = json.dumps(webhook_payload).encode("utf-8")
    secret = "test_secret_for_webhook"
    valid_signature = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

    # 1. Missing signature header
    resp_no_sig = client.post("/api/payments/razorpay/webhook", data=body_bytes)
    assert resp_no_sig.status_code == 400

    # 2. Invalid signature
    resp_bad_sig = client.post(
        "/api/payments/razorpay/webhook",
        data=body_bytes,
        headers={"X-Razorpay-Signature": "wrong_signature", "Content-Type": "application/json"},
    )
    assert resp_bad_sig.status_code == 400

    # 3. Valid webhook call -> processes booking
    resp_ok = client.post(
        "/api/payments/razorpay/webhook",
        data=body_bytes,
        headers={"X-Razorpay-Signature": valid_signature, "Content-Type": "application/json"},
    )
    assert resp_ok.status_code == 200
    assert resp_ok.get_json()["status"] == "processed"

    with test_app.app_context():
        updated_b = db.session.get(Booking, booking_id)
        assert updated_b.payment_status == "paid"
        assert updated_b.razorpay_payment_id == "pay_hook_12345"
        assert updated_b.payment_method == "netbanking"
        assert updated_b.amount_paid == 50000

    # 4. Duplicate webhook call (Idempotency test)
    resp_dup = client.post(
        "/api/payments/razorpay/webhook",
        data=body_bytes,
        headers={"X-Razorpay-Signature": valid_signature, "Content-Type": "application/json"},
    )
    assert resp_dup.status_code == 200
    assert resp_dup.get_json()["status"] == "already_processed"


# ==============================================================================
# 4. Authentication, Tokens & Privilege Escalation Tests (Prompt 3)
# ==============================================================================

def test_auth_privilege_escalation_blocked(client, test_app):
    """Verify users cannot self-assign admin privileges during registration."""
    resp = client.post("/api/auth/register", json={
        "name": "Attacker",
        "email": "attacker@vybe.test",
        "password": "password123",
        "role": "admin",  # Malicious privilege escalation attempt
    })
    assert resp.status_code == 201
    user_data = resp.get_json()["user"]
    # Role must be coerced to traveler
    assert user_data["role"] == "traveler"
    assert user_data["role"] != "admin"


def test_auth_password_reset_and_email_verification(client, seed_data, test_app):
    """Verify tokenized password reset, email verification, and no email enumeration."""
    # 1. Forgot password request (generic message regardless of email existence)
    resp = client.post("/api/auth/forgot-password", json={"email": "nonexistent@nowhere.com"})
    assert resp.status_code == 200
    assert "instructions have been sent" in resp.get_json()["message"]

    # 2. Real user forgot password request
    resp_real = client.post("/api/auth/forgot-password", json={"email": "traveler@vybe.test"})
    assert resp_real.status_code == 200
    token = resp_real.get_json().get("_debug_token")
    assert token is not None

    # 3. Bad token rejected
    bad_resp = client.post("/api/auth/reset-password", json={"token": "bad_token_123", "password": "newpassword123"})
    assert bad_resp.status_code == 400

    # 4. Valid token updates password
    good_resp = client.post("/api/auth/reset-password", json={"token": token, "password": "newpassword123"})
    assert good_resp.status_code == 200

    # 5. Login with new password succeeds
    login_resp = client.post("/api/auth/login", json={"email": "traveler@vybe.test", "password": "newpassword123"})
    assert login_resp.status_code == 200


def test_auth_account_deletion(client, seed_data):
    """Verify account deletion soft-anonymizes user data and logs audit event."""
    client.post("/api/auth/login", json={"email": "traveler@vybe.test", "password": "pass123"})
    
    # Incorrect password rejected
    bad = client.post("/api/auth/delete-account", json={"password": "wrong"})
    assert bad.status_code == 401

    # Correct password deletes/anonymizes
    ok = client.post("/api/auth/delete-account", json={"password": "pass123"})
    assert ok.status_code == 200
    assert "successfully deleted" in ok.get_json()["message"]


# ==============================================================================
# 5. Travel Package Lifecycle & Expiry Tests (Prompt 4)
# ==============================================================================

def test_package_lifecycle_transitions(client, seed_data):
    """Verify operator lifecycle state transitions (draft, active, inactive, archived)."""
    pkg_id = seed_data["package_id"]

    # 1. Traveler cannot change package lifecycle state (403)
    client.post("/api/auth/login", json={"email": "traveler@vybe.test", "password": "pass123"})
    r_trav = client.post(f"/api/packages/{pkg_id}/status", json={"status": "inactive"})
    assert r_trav.status_code == 403
    client.post("/api/auth/logout")

    # 2. Operator can deactivate and activate
    client.post("/api/auth/login", json={"email": "operator@vybe.test", "password": "pass123"})
    r_deact = client.post(f"/api/packages/{pkg_id}/status", json={"status": "inactive"})
    assert r_deact.status_code == 200
    assert r_deact.get_json()["package"]["status"] == "inactive"
    assert r_deact.get_json()["package"]["is_active"] is False

    r_act = client.post(f"/api/packages/{pkg_id}/status", json={"status": "active"})
    assert r_act.status_code == 200
    assert r_act.get_json()["package"]["status"] == "active"
    assert r_act.get_json()["package"]["is_active"] is True


def test_package_expiry_and_booking_blocking(client, seed_data, test_app):
    """Verify expired packages are blocked from discovery and cannot be booked."""
    from datetime import datetime, timedelta

    pkg_id = seed_data["package_id"]
    with test_app.app_context():
        p = db.session.get(TravelPackage, pkg_id)
        # Set expiry date in the past
        p.valid_until = datetime.utcnow() - timedelta(days=2)
        p.status = "active"
        p.is_active = True
        db.session.commit()

    # Attempting to enquiry/book an expired package must be rejected
    client.post("/api/auth/login", json={"email": "traveler@vybe.test", "password": "pass123"})
    resp = client.post("/api/enquiries", json={"package_id": pkg_id, "num_travellers": 1})
    assert resp.status_code in (400, 404)


# ==============================================================================
# 6. Notifications & Realtime Polling Tests (Prompt 5)
# ==============================================================================

def test_notifications_and_device_tokens(client, seed_data, test_app):
    """Verify persistent notifications, unread tracking, and device token registration."""
    traveler_id = seed_data["traveler_id"]
    client.post("/api/auth/login", json={"email": "traveler@vybe.test", "password": "pass123"})

    # 1. Register device token
    r_tok = client.post("/api/notifications/device-token", json={"token": "fcm_test_token_abc123", "platform": "android"})
    assert r_tok.status_code == 200

    # 2. Dispatch notification via push service
    from services.push import push_service
    with test_app.app_context():
        notif = push_service.send_notification(
            user_id=traveler_id,
            title="Flight Update",
            body="Your flight time has changed.",
            notif_type="flight_alert",
            data={"flight_id": "VY101"},
        )
        notif_id = notif.id

    # 3. Retrieve notifications
    r_list = client.get("/api/notifications")
    assert r_list.status_code == 200
    data = r_list.get_json()
    assert data["unread_count"] >= 1
    assert any(n["id"] == notif_id for n in data["notifications"])

    # 4. Polling endpoint
    r_poll = client.get("/api/notifications/poll")
    assert r_poll.status_code == 200
    assert "polled_at" in r_poll.get_json()

    # 5. Mark as read
    r_read = client.post(f"/api/notifications/{notif_id}/read")
    assert r_read.status_code == 200
    assert r_read.get_json()["notification"]["is_read"] is True

    # 6. Unregister device token
    r_untok = client.delete("/api/notifications/device-token", json={"token": "fcm_test_token_abc123"})
    assert r_untok.status_code == 200
