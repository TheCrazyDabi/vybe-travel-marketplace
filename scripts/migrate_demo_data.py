"""VYBE Demo Data Migration & Quarantine Utility.

Inspects the existing database to distinguish seed/demo packages from genuine
operator listings. Safely archives or flags demo packages without destroying
real accounts, active bookings, or traveler preferences.
"""

import argparse
import sys
from datetime import datetime, timezone

from app import create_app
from config import get_config
from models import AuditEvent, TravelCompany, TravelPackage, User, db
from models.booking import Booking, Enquiry


def inspect_production_data():
    """Report statistics on real vs demo records in the database."""
    total_users = User.query.count()
    demo_users = User.query.filter(User.email.ilike("%@vybe.test")).count()
    real_users = total_users - demo_users

    total_companies = TravelCompany.query.count()
    demo_companies = TravelCompany.query.filter_by(is_demo=True).count()
    real_companies = total_companies - demo_companies

    total_packages = TravelPackage.query.count()
    demo_packages = TravelPackage.query.filter_by(is_demo=True).count()
    real_packages = total_packages - demo_packages

    active_packages = TravelPackage.query.filter_by(is_active=True, is_deleted=False).count()
    expired_packages = TravelPackage.query.filter_by(status="expired").count()
    archived_packages = TravelPackage.query.filter_by(status="archived").count()

    total_bookings = Booking.query.count()
    total_enquiries = Enquiry.query.count()

    print("=" * 60)
    print("VYBE PRODUCTION DATA INSPECTION")
    print("=" * 60)
    print(f"Users: {total_users} total ({real_users} real, {demo_users} demo)")
    print(f"Companies: {total_companies} total ({real_companies} real, {demo_companies} demo)")
    print(f"Packages: {total_packages} total ({real_packages} real, {demo_packages} demo)")
    print(f"  - Active: {active_packages}")
    print(f"  - Expired: {expired_packages}")
    print(f"  - Archived: {archived_packages}")
    print(f"Bookings: {total_bookings}")
    print(f"Enquiries: {total_enquiries}")
    print("=" * 60)

    return {
        "real_users": real_users,
        "demo_users": demo_users,
        "real_packages": real_packages,
        "demo_packages": demo_packages,
        "total_bookings": total_bookings,
    }


def quarantine_demo_packages(dry_run=True):
    """Safely archive demo packages so they no longer appear in production feeds."""
    demo_pkgs = TravelPackage.query.filter_by(is_demo=True, is_active=True).all()
    count = len(demo_pkgs)

    print(f"Found {count} active demo packages to quarantine.")
    if dry_run:
        print("[DRY RUN] No changes were made. Pass --execute to apply.")
        return count

    for p in demo_pkgs:
        p.status = "archived"
        p.is_active = False
        p.is_deleted = True
        p.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)

    db.session.commit()

    AuditEvent.log(
        action="quarantine_demo_packages",
        details={"quarantined_count": count, "timestamp": datetime.now(timezone.utc).isoformat()},
    )

    print(f"Successfully quarantined {count} demo packages.")
    return count


def main():
    parser = argparse.ArgumentParser(description="VYBE Demo Data Migration Utility")
    parser.add_argument("--inspect", action="store_true", help="Report real vs demo data counts")
    parser.add_argument("--quarantine-demo", action="store_true", help="Archive demo packages from production discovery")
    parser.add_argument("--execute", action="store_true", help="Execute database updates (default is dry run)")

    args = parser.parse_args()

    app = create_app(get_config())
    with app.app_context():
        if args.inspect or not (args.quarantine_demo):
            inspect_production_data()

        if args.quarantine_demo:
            quarantine_demo_packages(dry_run=not args.execute)


if __name__ == "__main__":
    main()
