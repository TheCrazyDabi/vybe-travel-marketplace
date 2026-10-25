"""Comprehensive Automated Test Suite for VYBE Package Lifecycle, Validity & Safe Cleanup.

Covers all Section F Acceptance Criteria:
1. Package creation, editing, deactivation and reactivation
2. Operator ownership and privilege escalation attempts
3. Invalid and expired timestamps
4. Booking requests against expired packages
5. Exact expiry boundary behaviour
6. Scheduled cleanup retries and idempotency
7. Protected booking records (never hard deleted)
8. Safe image deletion and orphan cleanup
9. Database migration and rollback SQL files
"""

import os
from datetime import datetime, timedelta, timezone
import pytest

from app import create_app
from config import Config
from models import AuditEvent, Interest, TravelCompany, TravelPackage, User, db
from models.booking import Booking, Enquiry
from models.package import PackageImage
from services.package_lifecycle import (
    check_and_expire_packages,
    cleanup_expired_packages,
    get_utc_now,
    is_booking_allowed,
    is_image_referenced_elsewhere,
    safe_delete_package_images,
)


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    CRON_SECRET = "test-cron-secret-xyz123"
    CLEANUP_RETENTION_DAYS = 90
    SECRET_KEY = "test-secret-key-lifecycle"


@pytest.fixture()
def app_instance():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app_instance):
    return app_instance.test_client()


@pytest.fixture()
def setup_users_and_operators(app_instance):
    """Seed test users: traveler, operator A, operator B, admin."""
    with app_instance.app_context():
        traveler = User(name="Test Traveler", email="traveler@test.vybe", role="traveler")
        traveler.set_password("pass123")

        operator_a = User(name="Operator Alpha", email="alpha@test.vybe", role="operator")
        operator_a.set_password("pass123")

        operator_b = User(name="Operator Beta", email="beta@test.vybe", role="operator")
        operator_b.set_password("pass123")

        admin = User(name="Admin User", email="admin@test.vybe", role="admin")
        admin.set_password("pass123")

        db.session.add_all([traveler, operator_a, operator_b, admin])
        db.session.flush()

        comp_a = TravelCompany(
            user_id=operator_a.id,
            company_name="Alpha Adventures",
            business_email="alpha@test.vybe",
            status="approved",
            is_verified=True,
        )
        comp_b = TravelCompany(
            user_id=operator_b.id,
            company_name="Beta Expeditions",
            business_email="beta@test.vybe",
            status="approved",
            is_verified=True,
        )

        db.session.add_all([comp_a, comp_b])
        db.session.commit()

        return {
            "traveler_id": traveler.id,
            "operator_a_id": operator_a.id,
            "operator_b_id": operator_b.id,
            "admin_id": admin.id,
            "company_a_id": comp_a.id,
            "company_b_id": comp_b.id,
        }


# ==============================================================================
# 1. Package Creation, Editing, Deactivation and Reactivation
# ==============================================================================

def test_operator_package_create_edit_deactivate_reactivate(client, setup_users_and_operators):
    # Log in as Operator Alpha
    client.post("/api/auth/login", json={"email": "alpha@test.vybe", "password": "pass123"})

    now = datetime.now(timezone.utc)
    future_start = (now + timedelta(days=30)).isoformat()
    future_end = (now + timedelta(days=35)).isoformat()
    future_deadline = (now + timedelta(days=25)).isoformat()
    future_validity = (now + timedelta(days=20)).isoformat()

    # 1. Create Package with validity and booking deadline
    create_payload = {
        "title": "Himalayan Sunrise Trek",
        "destination": "Manali",
        "price": 14999,
        "duration_days": 5,
        "capacity": 15,
        "trip_start_date": future_start,
        "trip_end_date": future_end,
        "booking_deadline": future_deadline,
        "valid_until": future_validity,
        "status": "active",
    }
    r_create = client.post("/api/packages", json=create_payload)
    assert r_create.status_code == 201
    pkg_data = r_create.get_json()["package"]
    pkg_id = pkg_data["id"]
    assert pkg_data["title"] == "Himalayan Sunrise Trek"
    assert pkg_data["status"] == "active"
    assert pkg_data["is_active"] is True

    # 2. Edit Package
    r_update = client.put(f"/api/packages/{pkg_id}", json={
        "price": 13999,
        "short_desc": "Updated trek itinerary with certified guides.",
    })
    assert r_update.status_code == 200
    updated_pkg = r_update.get_json()["package"]
    assert updated_pkg["price"] == 13999
    assert updated_pkg["short_desc"] == "Updated trek itinerary with certified guides."

    # 3. Deactivate Package
    r_deact = client.post(f"/api/packages/{pkg_id}/status", json={"status": "inactive"})
    assert r_deact.status_code == 200
    assert r_deact.get_json()["package"]["status"] == "inactive"
    assert r_deact.get_json()["package"]["is_active"] is False

    # 4. Reactivate Package
    r_react = client.post(f"/api/packages/{pkg_id}/status", json={"status": "active"})
    assert r_react.status_code == 200
    assert r_react.get_json()["package"]["status"] == "active"
    assert r_react.get_json()["package"]["is_active"] is True


# ==============================================================================
# 2. Operator Ownership and Privilege Escalation Attempts
# ==============================================================================

def test_operator_ownership_and_privilege_escalation(client, setup_users_and_operators, app_instance):
    comp_a_id = setup_users_and_operators["company_a_id"]

    # Create package owned by Operator A
    with app_instance.app_context():
        pkg_a = TravelPackage(
            operator_id=comp_a_id,
            title="Kerala Backwaters Cruise",
            destination="Alleppey",
            price=8500,
            duration_days=3,
            is_active=True,
            status="active",
        )
        db.session.add(pkg_a)
        db.session.commit()
        pkg_a_id = pkg_a.id

    # Traveler attempts to modify package -> 403
    client.post("/api/auth/login", json={"email": "traveler@test.vybe", "password": "pass123"})
    r_trav_edit = client.put(f"/api/packages/{pkg_a_id}", json={"price": 100})
    assert r_trav_edit.status_code == 403

    r_trav_status = client.post(f"/api/packages/{pkg_a_id}/status", json={"status": "inactive"})
    assert r_trav_status.status_code == 403

    r_trav_del = client.post(f"/api/packages/{pkg_a_id}/delete")
    assert r_trav_del.status_code == 403
    client.post("/api/auth/logout")

    # Operator B attempts to modify Operator A's package -> 403
    client.post("/api/auth/login", json={"email": "beta@test.vybe", "password": "pass123"})
    r_beta_edit = client.put(f"/api/packages/{pkg_a_id}", json={"price": 5000})
    assert r_beta_edit.status_code == 403

    r_beta_status = client.post(f"/api/packages/{pkg_a_id}/status", json={"status": "inactive"})
    assert r_beta_status.status_code == 403

    r_beta_del = client.post(f"/api/packages/{pkg_a_id}/delete")
    assert r_beta_del.status_code == 403
    client.post("/api/auth/logout")


# ==============================================================================
# 3. Invalid and Expired Timestamps Validation
# ==============================================================================

def test_invalid_and_expired_timestamps_validation(client, setup_users_and_operators):
    client.post("/api/auth/login", json={"email": "alpha@test.vybe", "password": "pass123"})

    now = datetime.now(timezone.utc)
    past_date = (now - timedelta(days=5)).isoformat()
    future_start = (now + timedelta(days=10)).isoformat()
    future_end = (now + timedelta(days=5)).isoformat()  # End before start

    # 1. Negative Price
    r_neg = client.post("/api/packages", json={"title": "Trip", "destination": "Goa", "price": -500})
    assert r_neg.status_code == 400
    assert "price must be >= 0" in r_neg.get_json()["error"]

    # 2. Duration days 0
    r_days = client.post("/api/packages", json={"title": "Trip", "destination": "Goa", "price": 5000, "duration_days": 0})
    assert r_days.status_code == 400
    assert "duration_days" in r_days.get_json()["error"]

    # 3. Trip start after trip end
    r_inverted = client.post("/api/packages", json={
        "title": "Inverted Dates Trek",
        "destination": "Goa",
        "price": 5000,
        "trip_start_date": future_start,
        "trip_end_date": future_end,
    })
    assert r_inverted.status_code == 400
    assert "cannot be after" in r_inverted.get_json()["error"]

    # 4. Valid until in the past for active package
    r_past_valid = client.post("/api/packages", json={
        "title": "Expired Package",
        "destination": "Goa",
        "price": 5000,
        "valid_until": past_date,
        "status": "active",
    })
    assert r_past_valid.status_code == 400
    assert "past" in r_past_valid.get_json()["error"]


# ==============================================================================
# 4. Booking Requests Against Expired Packages
# ==============================================================================

def test_booking_request_against_expired_package_rejected(client, setup_users_and_operators, app_instance):
    comp_a_id = setup_users_and_operators["company_a_id"]
    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)

    with app_instance.app_context():
        expired_pkg = TravelPackage(
            operator_id=comp_a_id,
            title="Past Monsoon Expedition",
            destination="Meghalaya",
            price=12000,
            valid_until=past,
            status="active",
            is_active=True,
        )
        db.session.add(expired_pkg)
        db.session.commit()
        pkg_id = expired_pkg.id

    client.post("/api/auth/login", json={"email": "traveler@test.vybe", "password": "pass123"})

    # Attempt enquiry creation on expired package -> rejected
    r_enq = client.post("/api/enquiries", json={"package_id": pkg_id, "num_travellers": 1})
    assert r_enq.status_code in (400, 404)

    # Attempt direct booking request -> rejected
    r_book = client.post("/api/bookings/request", json={"package_id": pkg_id, "num_travellers": 1})
    assert r_book.status_code in (400, 404)


# ==============================================================================
# 5. Exact Expiry Boundary Behaviour
# ==============================================================================

def test_exact_expiry_boundary_behaviour(client, setup_users_and_operators, app_instance):
    comp_a_id = setup_users_and_operators["company_a_id"]
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with app_instance.app_context():
        # Package 1: Expires in 1 hour (Valid)
        p_valid = TravelPackage(
            operator_id=comp_a_id,
            title="Valid Boundary Package",
            destination="Jaipur",
            price=4500,
            valid_until=now + timedelta(hours=1),
            booking_deadline=now + timedelta(hours=1),
            trip_start_date=now + timedelta(days=5),
            status="active",
            is_active=True,
            capacity=10,
            seats_remaining=10,
        )
        # Package 2: Expired 2 seconds ago (Invalid)
        p_expired = TravelPackage(
            operator_id=comp_a_id,
            title="Expired Boundary Package",
            destination="Udaipur",
            price=5500,
            valid_until=now - timedelta(seconds=2),
            booking_deadline=now - timedelta(seconds=2),
            trip_start_date=now + timedelta(days=5),
            status="active",
            is_active=True,
            capacity=10,
            seats_remaining=10,
        )
        db.session.add_all([p_valid, p_expired])
        db.session.commit()
        valid_id = p_valid.id
        expired_id = p_expired.id

    client.post("/api/auth/login", json={"email": "traveler@test.vybe", "password": "pass123"})

    # Package 1 can accept booking requests
    r1 = client.post("/api/bookings/request", json={"package_id": valid_id, "num_travellers": 1})
    assert r1.status_code == 201

    # Package 2 is rejected immediately
    r2 = client.post("/api/bookings/request", json={"package_id": expired_id, "num_travellers": 1})
    assert r2.status_code == 400

    # Public discovery feed excludes Package 2
    r_list = client.get("/api/packages")
    assert r_list.status_code == 200
    pkgs = r_list.get_json()["packages"]
    pkg_ids = [p["id"] for p in pkgs]
    assert valid_id in pkg_ids
    assert expired_id not in pkg_ids


# ==============================================================================
# 6. Scheduled Cleanup Retries & Idempotency
# ==============================================================================

def test_scheduled_cleanup_retries_and_idempotency(client, setup_users_and_operators, app_instance):
    comp_a_id = setup_users_and_operators["company_a_id"]
    old_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=120)

    with app_instance.app_context():
        # Expired package older than retention cutoff (90 days) with no protected records
        p_old = TravelPackage(
            operator_id=comp_a_id,
            title="Ancient Desert Safari",
            destination="Jaisalmer",
            price=7000,
            status="expired",
            is_active=False,
            deleted_at=old_date,
            created_at=old_date,
            updated_at=old_date,
        )
        db.session.add(p_old)
        db.session.commit()
        old_pkg_id = p_old.id

    # Unauthorized call rejected (no secret)
    r_unauth = client.post("/api/cron/cleanup")
    assert r_unauth.status_code == 401

    # Authorized call with valid X-Cron-Secret
    headers = {"X-Cron-Secret": "test-cron-secret-xyz123"}
    r1 = client.post("/api/cron/cleanup?retention_days=90", headers=headers)
    assert r1.status_code == 200
    res1 = r1.get_json()
    assert res1["status"] == "success"
    assert res1["purged_count"] == 1
    assert old_pkg_id in res1["purged_package_ids"]

    # Verify record was purged
    with app_instance.app_context():
        assert db.session.get(TravelPackage, old_pkg_id) is None

    # Idempotent retry: running cleanup again succeeds with 0 extra purged
    r2 = client.post("/api/cron/cleanup?retention_days=90", headers=headers)
    assert r2.status_code == 200
    res2 = r2.get_json()
    assert res2["status"] == "success"
    assert res2["purged_count"] == 0

    # Verify audit event was logged
    with app_instance.app_context():
        events = AuditEvent.query.filter_by(action="package_cleanup_job").all()
        assert len(events) >= 2


# ==============================================================================
# 7. Protected Booking Records (Never Hard Deleted)
# ==============================================================================

def test_protected_booking_records_never_hard_deleted(client, setup_users_and_operators, app_instance):
    comp_a_id = setup_users_and_operators["company_a_id"]
    traveler_id = setup_users_and_operators["traveler_id"]
    old_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=120)

    with app_instance.app_context():
        pkg = TravelPackage(
            operator_id=comp_a_id,
            title="Heritage Haveli Tour",
            destination="Shekhawati",
            price=9000,
            status="expired",
            is_active=False,
            deleted_at=old_date,
            created_at=old_date,
            updated_at=old_date,
        )
        db.session.add(pkg)
        db.session.flush()

        # Attach confirmed booking (financial & accounting history)
        booking = Booking(
            package_id=pkg.id,
            company_id=comp_a_id,
            traveler_id=traveler_id,
            booking_reference="VY-PROT01",
            status="confirmed",
            total_cost=9000,
        )
        db.session.add(booking)
        db.session.commit()
        pkg_id = pkg.id

    # Run cleanup past retention threshold
    headers = {"X-Cron-Secret": "test-cron-secret-xyz123"}
    res = client.post("/api/cron/cleanup?retention_days=90", headers=headers).get_json()

    assert res["status"] == "success"
    assert res["purged_count"] == 0
    assert res["retained_protected_count"] >= 1

    # Guarantee package still exists in database
    with app_instance.app_context():
        p_retained = db.session.get(TravelPackage, pkg_id)
        assert p_retained is not None
        assert p_retained.status == "expired"
        assert Booking.query.filter_by(package_id=pkg_id).count() == 1


# ==============================================================================
# 8. Safe Image Deletion and Orphan Cleanup
# ==============================================================================

def test_safe_image_deletion_and_orphan_cleanup(client, setup_users_and_operators, app_instance):
    comp_a_id = setup_users_and_operators["company_a_id"]

    shared_image_path = "packages/1/shared_hero.webp"
    orphan_image_path = "packages/1/unique_solo.webp"

    with app_instance.app_context():
        # Package 1 has shared image and unique image
        p1 = TravelPackage(
            operator_id=comp_a_id,
            title="Shared Image Tour 1",
            destination="Goa",
            cover_image=shared_image_path,
            images=[shared_image_path, orphan_image_path],
            is_active=False,
            status="expired",
        )
        # Package 2 also references shared image
        p2 = TravelPackage(
            operator_id=comp_a_id,
            title="Shared Image Tour 2",
            destination="Goa",
            cover_image=shared_image_path,
            images=[shared_image_path],
            is_active=True,
            status="active",
        )
        db.session.add_all([p1, p2])
        db.session.commit()
        p1_id = p1.id

        # Verify shared image detection
        assert is_image_referenced_elsewhere(shared_image_path, exclude_package_id=p1_id) is True
        assert is_image_referenced_elsewhere(orphan_image_path, exclude_package_id=p1_id) is False

        # Prune images for package 1: shared image preserved, orphan image processed
        p1_instance = db.session.get(TravelPackage, p1_id)
        deleted = safe_delete_package_images(p1_instance)
        # Shared image must NEVER be in deleted list
        assert shared_image_path not in deleted


# ==============================================================================
# 9. Database Migration and Rollback Files Validity
# ==============================================================================

def test_database_migration_and_rollback_sql():
    migration_path = os.path.join("migrations", "003_package_lifecycle_and_cleanup.sql")
    rollback_path = os.path.join("migrations", "003_package_lifecycle_and_cleanup_rollback.sql")

    assert os.path.isfile(migration_path), "Migration file 003 must exist"
    assert os.path.isfile(rollback_path), "Rollback file 003 must exist"

    with open(migration_path, "r", encoding="utf-8") as f:
        mig_sql = f.read()

    with open(rollback_path, "r", encoding="utf-8") as f:
        roll_sql = f.read()

    # Verify critical DDL components
    assert "package_images" in mig_sql
    assert "auth_user_id" in mig_sql
    assert "idx_travel_packages_valid_until" in mig_sql
    assert "ROW LEVEL SECURITY" in mig_sql

    assert "DROP TABLE IF EXISTS package_images" in roll_sql
    assert "DROP INDEX IF EXISTS idx_travel_packages_valid_until" in roll_sql
