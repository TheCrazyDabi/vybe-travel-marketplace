"""Seed VYBE with demo users, companies and packages (clearly labeled sample data)."""

import json
import os

from models import TravelCompany, TravelerProfile, TravelPackage, User, UserPreference, db

DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "sample_packages.json")


def seed_if_empty():
    if User.query.first():
        return
    print("Seeding VYBE demo data...")

    traveler = User(name="Demo Traveler", email="traveler@vybe.demo", role="traveler")
    traveler.set_password("traveler123")
    operator = User(name="Demo Operator", email="operator@vybe.demo", role="operator")
    operator.set_password("operator123")
    admin = User(name="Demo Admin", email="admin@vybe.demo", role="admin")
    admin.set_password("admin123")
    db.session.add_all([traveler, operator, admin])
    db.session.flush()

    db.session.add(TravelerProfile(
        user_id=traveler.id, budget_max=15000, duration_days=3,
        preferred_regions=["mountains", "beaches"], preferred_climate=["cool"],
        scenery=["mountains"], interests=["nature", "adventure"],
        group_type="friends", current_mood="relaxation",
    ))
    db.session.add(UserPreference(user_id=traveler.id))

    with open(DATA_FILE, encoding="utf-8") as f:
        payload = json.load(f)

    for c in payload.get("companies", []):
        db.session.add(TravelCompany(
            user_id=operator.id,
            company_name=c["company_name"],
            business_email=c["business_email"],
            contact_details=c.get("contact_details"),
            description=c.get("description"),
            licence_info=c.get("licence_info"),
            service_regions=c.get("service_regions", []),
            logo=c.get("logo"),
            status="approved",
            is_verified=True,
        ))
    db.session.flush()

    companies = TravelCompany.query.all()
    for i, p in enumerate(payload.get("packages", [])):
        company = companies[i % len(companies)] if companies else None
        db.session.add(TravelPackage(
            operator_id=company.id if company else 1,
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
        ))
    db.session.commit()
    print(f"Seeded {User.query.count()} users, {TravelCompany.query.count()} companies, {TravelPackage.query.count()} packages.")


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        seed_if_empty()
