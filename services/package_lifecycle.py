"""Package Lifecycle, Validity Expiry, and Non-Destructive Cleanup Service for VYBE.

Enforces:
1. Exact timestamp boundary validity and booking deadline distinction.
2. Real-time request-level expiration check without relying solely on cron.
3. Retention rules preserving financial, audit, dispute, and booking records.
4. Safe image deletion preventing deletion of shared image assets.
5. Idempotent background cleanup suitable for pg_cron, Vercel Cron, or admin endpoints.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app
from models import AuditEvent, Interest, TravelPackage, db
from models.booking import Booking, Enquiry
from models.custom_offer import CustomOffer
from models.moderation import Report
from models.package import PackageImage
from models.review import Review
from services.storage import storage_service

logger = logging.getLogger(__name__)


def get_utc_now() -> datetime:
    """Return naive UTC datetime for standard database column comparisons."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Convert an aware or naive datetime to naive UTC."""
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def check_and_expire_packages() -> int:
    """Evaluate and transition expired packages in real-time.

    Transitions packages to 'expired' and is_active=False if:
    - valid_until < now
    - booking_deadline < now
    - trip_start_date < now
    Idempotent: packages already expired or inactive are skipped.
    """
    now = get_utc_now()
    active_pkgs = TravelPackage.query.filter(
        TravelPackage.is_active == True,
        TravelPackage.is_deleted == False,
    ).all()

    expired_count = 0
    for pkg in active_pkgs:
        vu = to_naive_utc(pkg.valid_until)
        bd = to_naive_utc(pkg.booking_deadline)
        ts = to_naive_utc(pkg.trip_start_date)

        is_expired = False
        if vu and vu <= now:
            is_expired = True
        elif bd and bd <= now:
            is_expired = True
        elif ts and ts <= now:
            is_expired = True

        if is_expired:
            pkg.status = "expired"
            pkg.is_active = False
            expired_count += 1

    if expired_count > 0:
        db.session.commit()
        logger.info("check_and_expire_packages: transitioned %d packages to expired.", expired_count)

    return expired_count


def is_booking_allowed(package: Optional[TravelPackage], num_travellers: int = 1) -> Tuple[bool, str]:
    """Validate whether a package can accept new bookings or enquiries.

    Distinguishes:
    - Booking deadline passed vs Validity expiry passed vs Trip departed.
    - Capacity and seat constraints.
    - Operator approval and suspension status.
    """
    if not package:
        return False, "Package not found"

    if bool(getattr(package, "is_deleted", False)):
        return False, "Package is no longer available"

    now = get_utc_now()

    # Listing validity check
    vu = to_naive_utc(package.valid_until)
    if vu and vu <= now:
        return False, "Package listing has expired"

    # Booking deadline check (distinguished from validity expiry)
    bd = to_naive_utc(package.booking_deadline)
    if bd and bd <= now:
        return False, "Booking deadline for this trip has passed"

    # Trip departure check
    ts = to_naive_utc(package.trip_start_date)
    if ts and ts <= now:
        return False, "Trip has already departed"

    # Status check
    status = (package.status or "active").lower()
    if status != "active" or not package.is_active:
        return False, f"Package is unavailable for booking (status: {status})"

    # Capacity & Seats check
    if isinstance(package.seats_remaining, int) and package.seats_remaining is not None:
        if package.seats_remaining <= 0:
            return False, "Not enough seats remaining. Only 0 available."
        if package.seats_remaining < num_travellers:
            return False, f"Not enough seats remaining. Only {package.seats_remaining} available"

    if isinstance(package.max_group_size, int) and package.max_group_size:
        if num_travellers > package.max_group_size:
            return False, f"Number of travellers exceeds maximum group size of {package.max_group_size}"

    # Operator status check
    if package.operator:
        if package.operator.status != "approved":
            return False, "Operator company is not verified to accept bookings"
        if package.operator.owner and package.operator.owner.status != "active":
            return False, "Operator account is suspended or inactive"

    return True, "OK"


def is_package_protected(package_id: int) -> Tuple[bool, List[str]]:
    """Determine whether a package is protected by accounting, legal or dispute references.

    A package is protected and CANNOT be hard deleted if it has:
    - Confirmed or past bookings
    - Traveler enquiries
    - Custom offers / quotations
    - Traveler reviews
    - Open moderation reports
    """
    reasons: List[str] = []

    if Booking.query.filter_by(package_id=package_id).count() > 0:
        reasons.append("has_booking_history")

    if Enquiry.query.filter_by(package_id=package_id).count() > 0:
        reasons.append("has_enquiries")

    if CustomOffer.query.filter_by(package_id=package_id).count() > 0:
        reasons.append("has_custom_offers")

    if Review.query.filter_by(package_id=package_id).count() > 0:
        reasons.append("has_reviews")

    if Report.query.filter_by(target_type="package", target_id=package_id, status="open").count() > 0:
        reasons.append("has_open_dispute_reports")

    return (len(reasons) > 0, reasons)


def is_image_referenced_elsewhere(image_path_or_url: str, exclude_package_id: Optional[int] = None) -> bool:
    """Check if an image path or URL is referenced by another package or record.

    Prevents deleting shared images when one package is pruned.
    """
    if not image_path_or_url or not str(image_path_or_url).strip():
        return False

    clean_path = str(image_path_or_url).strip()

    # 1. Other package cover_image
    q_cover = TravelPackage.query.filter(TravelPackage.cover_image == clean_path)
    if exclude_package_id is not None:
        q_cover = q_cover.filter(TravelPackage.id != exclude_package_id)
    if q_cover.count() > 0:
        return True

    # 2. Other package images JSON array
    q_images = TravelPackage.query
    if exclude_package_id is not None:
        q_images = q_images.filter(TravelPackage.id != exclude_package_id)
    for p in q_images.all():
        if p.images and clean_path in p.images:
            return True

    # 3. Package images table
    q_pkg_img = PackageImage.query.filter(
        (PackageImage.storage_path == clean_path) | (PackageImage.url == clean_path)
    )
    if exclude_package_id is not None:
        q_pkg_img = q_pkg_img.filter(PackageImage.package_id != exclude_package_id)
    if q_pkg_img.count() > 0:
        return True

    return False


def safe_delete_package_images(package: TravelPackage) -> List[str]:
    """Safely delete package image files if they are not referenced by any other package.

    Returns the list of storage keys successfully deleted.
    """
    deleted_keys: List[str] = []
    candidates: set = set()

    if package.cover_image:
        candidates.add(package.cover_image)

    for img in (package.images or []):
        if img:
            candidates.add(img)

    for rec in package.package_image_records.all():
        if rec.storage_path:
            candidates.add(rec.storage_path)

    for image_ref in candidates:
        # Ignore external HTTP links or default static assets
        if image_ref.startswith("http://") or image_ref.startswith("https://") or image_ref.startswith("/static/"):
            continue

        if is_image_referenced_elsewhere(image_ref, exclude_package_id=package.id):
            logger.info("Image '%s' is referenced by another package; preserved.", image_ref)
            continue

        # Safe to delete orphan image
        try:
            if storage_service.delete_file(image_ref):
                deleted_keys.append(image_ref)
                logger.info("Safely deleted orphan package image '%s'.", image_ref)
        except Exception as e:
            logger.error("Failed to delete image '%s': %s", image_ref, e)

    return deleted_keys


def cleanup_expired_packages(
    retention_days: int = 90,
    dry_run: bool = False,
    current_user_id: Optional[int] = None,
    request=None,
) -> Dict[str, Any]:
    """Idempotently process package expiry and clean up unreferenced expired listings.

    Safety Guarantees:
    - Step 1: Transitions newly expired packages to status='expired' and is_active=False.
    - Step 2: Locates packages expired/archived older than retention_days.
    - Step 3: Evaluates protected references (bookings, enquiries, offers, reviews).
              Protected packages are NEVER deleted; their history is retained.
    - Step 4: For eligible unreferenced packages, safely deletes unshared images before
              removing the record.
    - Step 5: Records an AuditEvent documenting the outcome without logging personal data.
    """
    start_time = datetime.now()

    # 1. Update newly expired
    newly_expired_count = check_and_expire_packages()

    now = get_utc_now()
    retention_cutoff = now - timedelta(days=max(0, retention_days))

    # 2. Find candidates past retention threshold
    candidates = TravelPackage.query.filter(
        (TravelPackage.status.in_(["expired", "archived"])) | (TravelPackage.is_deleted == True)
    ).all()

    purged_count = 0
    retained_protected_count = 0
    images_purged_count = 0
    purged_package_ids: List[int] = []
    retained_reasons: Dict[int, List[str]] = {}

    for pkg in candidates:
        # Determine package age
        last_touch = to_naive_utc(pkg.deleted_at or pkg.updated_at or pkg.created_at) or now
        if last_touch > retention_cutoff:
            # Package has not yet reached the retention threshold
            continue

        protected, reasons = is_package_protected(pkg.id)
        if protected:
            retained_protected_count += 1
            retained_reasons[pkg.id] = reasons
            continue

        # Eligible for permanent removal
        if not dry_run:
            deleted_imgs = safe_delete_package_images(pkg)
            images_purged_count += len(deleted_imgs)

            # Clean dependent non-critical interactions (interests/swipes, package_images)
            Interest.query.filter_by(package_id=pkg.id).delete()
            PackageImage.query.filter_by(package_id=pkg.id).delete()

            db.session.delete(pkg)

        purged_count += 1
        purged_package_ids.append(pkg.id)

    if not dry_run:
        db.session.commit()

    duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)

    # 3. Log Audit Event
    audit_details = {
        "newly_expired_count": newly_expired_count,
        "purged_count": purged_count,
        "retained_protected_count": retained_protected_count,
        "images_purged_count": images_purged_count,
        "retention_days": retention_days,
        "dry_run": dry_run,
        "duration_ms": duration_ms,
    }

    AuditEvent.log(
        action="package_cleanup_job",
        user_id=current_user_id,
        target_type="travel_packages",
        target_id=str(purged_count),
        details=audit_details,
        request=request,
    )

    return {
        "status": "success",
        "newly_expired_count": newly_expired_count,
        "purged_count": purged_count,
        "retained_protected_count": retained_protected_count,
        "images_purged_count": images_purged_count,
        "purged_package_ids": purged_package_ids,
        "retention_days": retention_days,
        "dry_run": dry_run,
        "duration_ms": duration_ms,
    }
