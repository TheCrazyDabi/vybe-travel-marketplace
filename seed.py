"""Seed VYBE with demo users, companies and packages (clearly labeled sample data).

Safe + repeatable:
- `seed_if_empty()` runs once on first launch (no users yet).
- `seed_demo()` can run repeatedly: upserts sample rows by natural keys
  (email / company_name / title+destination), never duplicates, never touches
  passwords of existing users, never deletes user data.
- Sample rows carry is_demo=True / "(demo)" names so UI labels them.
- Prints created/updated counts.

Usage:
    py seed.py            # safe: only fills gaps
    py seed.py --demo     # force refresh of sample catalogue
"""

import json
import os
import sys
from datetime import datetime

from models import (
    Interest, Report, TravelCompany, TravelerProfile, TravelPackage,
    User, UserPreference, VerificationRecord, db,
)

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "sample_packages.json")
MORE_FILE = os.path.join(os.path.dirname(__file__), "data", "more_packages.json")


def _build_package(p, company_id):
    return TravelPackage(
        operator_id=company_id,
        title=p["title"], destination=p["destination"],
        lat=p.get("lat"), lng=p.get("lng"),
        cover_image=p.get("cover_image"), short_desc=p.get("short_desc"),
        itinerary=p.get("itinerary"), price=p.get("price", 0),
        currency=p.get("currency", "INR"),
        duration_days=p.get("duration_days", 3),
        available_dates=p.get("available_dates"),
        group_size=p.get("group_size"),
        included=p.get("included", []), excluded=p.get("excluded", []),
        accommodation=p.get("accommodation"), transportation=p.get("transportation"),
        activities=p.get("activities", []),
        region_tags=p.get("region_tags", []), climate_tags=p.get("climate_tags", []),
        scenery_tags=p.get("scenery_tags", []), interest_tags=p.get("interest_tags", []),
        mood_tags=p.get("mood_tags", []),
        cancellation_terms=p.get("cancellation_terms"),
        is_active=True,
    )


def seed_demo_packages():
    """Idempotently add demo expansion packages. Safe to run on every boot.

    - Matches existing rows by title: never duplicates, never overwrites
      user-edited packages or touches interests/chats/bookings.
    - Attaches new packages to approved demo companies only.
    - Returns the number of packages added.
    """
    try:
        with open(MORE_FILE, encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, ValueError) as e:
        print(f"Demo expansion pack unavailable ({e}); skipping.")
        return 0
    companies = TravelCompany.query.filter_by(status="approved").all()
    if not companies:
        print("No approved companies; skipping demo expansion pack.")
        return 0
    existing = {t for (t,) in db.session.query(TravelPackage.title).all()}
    added = 0
    try:
        for i, p in enumerate(payload.get("packages", [])):
            if not p.get("title") or p["title"] in existing:
                continue
            company = companies[i % len(companies)]
            db.session.add(_build_package(p, company.id))
            existing.add(p["title"])
            added += 1
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Demo expansion pack partially applied ({e}); rolled back batch.")
        return 0
    if added:
        print(f"Seeded {added} demo expansion packages.")
    return added


def _demo_breakdown(price: int) -> dict:
    """Deterministic illustrative split that always sums to price (demo only)."""
    price = int(price or 0)
    accom = round(price * 0.22)
    transport = round(price * 0.14)
    meals = round(price * 0.10)
    activities = round(price * 0.08)
    taxes = round(price * 0.06)
    base = price - (accom + transport + meals + activities + taxes)
    return {
        "base": base,
        "accommodation": accom,
        "transport": transport,
        "meals": meals,
        "activities": activities,
        "taxes": taxes,
        "extras": [],
        "note": "Illustrative demo split — ask the operator for a confirmed quote.",
    }

def _get_or_create_user(email, name, role, password):
    u = User.query.filter_by(email=email).first()
    if u:
        if not u.check_password(password):
            u.set_password(password)
            db.session.flush()
        return u, False
    u = User(name=name, email=email, role=role, is_email_verified=True)
    u.set_password(password)
    db.session.add(u)
    db.session.flush()
    return u, True


def seed_demo():
    """Upsert the sample catalogue. Returns dict of counts."""
    counts = {"users_created": 0, "companies_created": 0, "companies_updated": 0,
              "packages_created": 0, "packages_updated": 0}

    # Remove legacy PostgreSQL unique constraint on travel_companies(user_id) if present
    try:
        from sqlalchemy import text
        if db.engine.dialect.name == "postgresql":
            db.session.execute(text("ALTER TABLE travel_companies DROP CONSTRAINT IF EXISTS travel_companies_user_id_key"))
            db.session.commit()
    except Exception:
        db.session.rollback()

    with open(DATA_FILE, encoding="utf-8") as f:
        payload = json.load(f)

    demo_users = [
        ("traveler@vybe.demo", "Demo Traveler", "traveler", "traveler123"),
        ("operator@vybe.demo", "Demo Operator", "operator", "operator123"),
        ("admin@vybe.demo", "Demo Admin", "admin", "admin123"),
        ("pending@vybe.demo", "Pending Operator (demo)", "operator", "pending123"),
        ("rejected@vybe.demo", "Rejected Operator (demo)", "operator", "rejected123"),
    ]
    users = {}
    for email, name, role, pw in demo_users:
        u, created = _get_or_create_user(email, name, role, pw)
        users[email] = u
        counts["users_created"] += int(created)
    operator = users["operator@vybe.demo"]
    traveler = users["traveler@vybe.demo"]

    if not traveler.profile:
        db.session.add(TravelerProfile(
            user_id=traveler.id, budget_max=15000, duration_days=3,
            preferred_regions=["mountains", "beaches"], preferred_climate=["cool"],
            scenery=["mountains"], interests=["nature", "adventure"],
            group_type="friends", current_mood="relaxation",
        ))
    if not traveler.preference:
        db.session.add(UserPreference(user_id=traveler.id))

    companies = {}
    for c in payload.get("companies", []):
        name = c["company_name"]
        co = TravelCompany.query.filter_by(company_name=name).first()
        if co is None:
            co = TravelCompany(
                user_id=operator.id, company_name=name,
                business_email=c["business_email"],
                contact_details=c.get("contact_details"),
                description=c.get("description"),
                licence_info=c.get("licence_info"),
                service_regions=c.get("service_regions", []),
                operating_regions=c.get("service_regions", []),
                logo=c.get("logo"), status="approved", is_verified=True,
                is_demo=True,
            )
            db.session.add(co)
            counts["companies_created"] += 1
        else:
            co.is_demo = True
            if not co.service_regions:
                co.service_regions = c.get("service_regions", [])
            counts["companies_updated"] += 1
        db.session.flush()
        companies[name] = co

    all_cos = TravelCompany.query.filter_by(status="approved").all() or list(companies.values())
    by_name = {c.company_name: c for c in all_cos}
    sample_keys = {(p["title"], p["destination"]) for p in payload.get("packages", [])}
    for i, p in enumerate(payload.get("packages", [])):
        existing = TravelPackage.query.filter_by(
            title=p["title"], destination=p["destination"]).first()
        if existing is not None and not existing.is_demo and (existing.title, existing.destination) not in sample_keys:
            continue  # preserve real user-generated packages
        company = by_name.get(p.get("company") or "") or (all_cos[i % len(all_cos)] if all_cos else None)
        fields = dict(
            operator_id=company.id if company else 1,
            lat=p.get("lat"), lng=p.get("lng"),
            cover_image=p.get("cover_image"), short_desc=p.get("short_desc"),
            itinerary=p.get("itinerary"), price=p.get("price", 0),
            currency=p.get("currency", "INR"),
            duration_days=p.get("duration_days", 3),
            available_dates=p.get("available_dates"),
            group_size=p.get("group_size"),
            included=p.get("included", []), excluded=p.get("excluded", []),
            accommodation=p.get("accommodation"), transportation=p.get("transportation"),
            activities=p.get("activities", []),
            region_tags=p.get("region_tags", []), climate_tags=p.get("climate_tags", []),
            scenery_tags=p.get("scenery_tags", []), interest_tags=p.get("interest_tags", []),
            mood_tags=p.get("mood_tags", []),
            cancellation_terms=p.get("cancellation_terms"),
            nights=max(0, int(p.get("duration_days", 3)) - 1),
            min_group_size=2, max_group_size=12, capacity=20, seats_remaining=10,
            suitable_travel_styles=list({t.lower() for t in (p.get("interest_tags", []) + p.get("mood_tags", []))})[:4],
            suitable_groups=["friends", "family", "couple"],
            is_active=True, is_demo=True,
            price_breakdown=_demo_breakdown(p.get("price", 0)),
            price_kind="demo_estimate",
            price_confirmed_at=datetime.utcnow(),
        )
        if existing is None:
            db.session.add(TravelPackage(title=p["title"], destination=p["destination"], **fields))
            counts["packages_created"] += 1
        else:
            for k, v in fields.items():
                setattr(existing, k, v)
            counts["packages_updated"] += 1
    db.session.flush()

    # Demo verification states (idempotent by company).
    for email, cname, desc, lic, region, st in [
        ("pending@vybe.demo", "Hill Country Trails (demo, pending review)",
         "Demo pending company — shows the operator verification queue.",
         "DEMO-PENDING-0003 (sample data, not a real licence)", ["Kerala"], "pending"),
        ("rejected@vybe.demo", "Budget Beach Stays (demo, rejected)",
         "Demo rejected company — shows the rejection + resubmit flow.",
         "DEMO-REJECTED-0004 (sample data, not a real licence)", ["Goa"], "rejected"),
    ]:
        owner = users[email]
        co = TravelCompany.query.filter_by(company_name=cname).first()
        if co is None:
            co = TravelCompany(user_id=owner.id, company_name=cname,
                               business_email=email, contact_details="+91 90000 00000",
                               description=desc, licence_info=lic,
                               service_regions=region, operating_regions=region,
                               status=st, is_verified=False, is_demo=True)
            db.session.add(co)
            db.session.flush()
            db.session.add(VerificationRecord(company_id=co.id, submitted_by=owner.id,
                                              status=st if st == "pending" else "rejected"))
            counts["companies_created"] += 1
    db.session.commit()
    print(f"Demo seed: {counts['users_created']} users, "
          f"{counts['companies_created']} companies created/{counts['companies_updated']} updated, "
          f"{counts['packages_created']} packages created/{counts['packages_updated']} updated.")
    return counts


def seed_if_empty():
    if User.query.first():
        return
    print("Seeding VYBE demo data...")
    seed_demo()
    # Demo traveler activity (first run only).
    traveler = User.query.filter_by(email="traveler@vybe.demo").first()
    pkgs = TravelPackage.query.order_by(TravelPackage.id).all()
    admin = User.query.filter_by(email="admin@vybe.demo").first()
    if traveler and pkgs:
        if not Interest.query.filter_by(traveler_id=traveler.id).first():
            db.session.add(Interest(traveler_id=traveler.id, package_id=pkgs[0].id, action="like"))
            if len(pkgs) > 2:
                db.session.add(Interest(traveler_id=traveler.id, package_id=pkgs[2].id, action="save"))
        if admin and not Report.query.first():
            db.session.add(Report(
                reporter_id=traveler.id, target_type="package", target_id=pkgs[-1].id,
                reason="Suspicious pricing (demo report)",
                details="Demo report for the admin moderation queue — not a real complaint.",
            ))
        db.session.commit()
    print(f"Seeded {User.query.count()} users, {TravelCompany.query.count()} companies, {TravelPackage.query.count()} packages.")


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        if "--demo" in sys.argv:
            seed_demo()
        else:
            seed_if_empty()
        seed_demo_packages()
