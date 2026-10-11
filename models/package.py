from datetime import datetime

from . import db


class TravelPackage(db.Model):
    __tablename__ = "travel_packages"

    id = db.Column(db.Integer, primary_key=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("travel_companies.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    destination = db.Column(db.String(120), nullable=False, index=True)
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    cover_image = db.Column(db.String(1024), nullable=True)
    short_desc = db.Column(db.String(500), nullable=True)
    itinerary = db.Column(db.Text, nullable=True)
    price = db.Column(db.Integer, nullable=False, default=0)
    currency = db.Column(db.String(10), default="INR")
    duration_days = db.Column(db.Integer, nullable=False, default=1)
    available_dates = db.Column(db.String(255), nullable=True)
    group_size = db.Column(db.String(64), nullable=True)
    included = db.Column(db.JSON, default=list)
    excluded = db.Column(db.JSON, default=list)
    accommodation = db.Column(db.String(255), nullable=True)
    transportation = db.Column(db.String(255), nullable=True)
    activities = db.Column(db.JSON, default=list)

    region_tags = db.Column(db.JSON, default=list)
    climate_tags = db.Column(db.JSON, default=list)
    scenery_tags = db.Column(db.JSON, default=list)
    interest_tags = db.Column(db.JSON, default=list)
    mood_tags = db.Column(db.JSON, default=list)

    cancellation_terms = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    # Soft-delete / archival (Feature B): never hard-delete packages with
    # history. Deleted packages are hidden from discovery but rows stay.
    is_deleted = db.Column(db.Boolean, default=False, index=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Phase 2: package management extras (additive, all nullable)
    nights = db.Column(db.Integer, nullable=True)
    min_group_size = db.Column(db.Integer, nullable=True)
    max_group_size = db.Column(db.Integer, nullable=True)
    suitable_travel_styles = db.Column(db.JSON, default=list)
    suitable_groups = db.Column(db.JSON, default=list)
    capacity = db.Column(db.Integer, nullable=True)
    seats_remaining = db.Column(db.Integer, nullable=True)
    customization_options = db.Column(db.Text, nullable=True)
    images = db.Column(db.JSON, default=list)
    departure_dates_list = db.Column(db.JSON, default=list)

    # TruePrice + demo trust layer (additive, nullable)
    price_breakdown = db.Column(db.JSON, nullable=True)
    price_kind = db.Column(db.String(20), nullable=True)  # demo_estimate|operator_quote|confirmed
    price_confirmed_at = db.Column(db.DateTime, nullable=True)
    is_demo = db.Column(db.Boolean, default=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self, include_operator=True):
        data = {
            "id": self.id,
            "title": self.title,
            "destination": self.destination,
            "lat": self.lat,
            "lng": self.lng,
            "cover_image": self.cover_image,
            "short_desc": self.short_desc,
            "itinerary": self.itinerary,
            "price": self.price,
            "currency": self.currency,
            "duration_days": self.duration_days,
            "available_dates": self.available_dates,
            "group_size": self.group_size,
            "included": self.included or [],
            "excluded": self.excluded or [],
            "accommodation": self.accommodation,
            "transportation": self.transportation,
            "activities": self.activities or [],
            "region_tags": self.region_tags or [],
            "climate_tags": self.climate_tags or [],
            "scenery_tags": self.scenery_tags or [],
            "interest_tags": self.interest_tags or [],
            "mood_tags": self.mood_tags or [],
            "cancellation_terms": self.cancellation_terms,
            "is_active": self.is_active,
            "is_deleted": bool(getattr(self, "is_deleted", False)),
            "deleted_at": self.deleted_at.isoformat() if getattr(self, "deleted_at", None) else None,
            # Phase 2 extras
            "nights": self.nights,
            "min_group_size": self.min_group_size,
            "max_group_size": self.max_group_size,
            "suitable_travel_styles": self.suitable_travel_styles or [],
            "suitable_groups": self.suitable_groups or [],
            "capacity": self.capacity,
            "seats_remaining": self.seats_remaining,
            "customization_options": self.customization_options,
            "images": self.images or [],
            "departure_dates_list": self.departure_dates_list or [],
            "price_breakdown": self.price_breakdown,
            "price_kind": self.price_kind,
            "price_confirmed_at": self.price_confirmed_at.isoformat() if self.price_confirmed_at else None,
            "is_demo": bool(self.is_demo),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            # availability derived from real data only (never fabricated)
            "availability_status": (
                "Available"
                if (self.seats_remaining is None or (self.seats_remaining or 0) > 0) and self.is_active
                else "Sold out / Hidden"
            ),
        }
        if include_operator and self.operator:
            data["operator"] = {
                "id": self.operator.id,
                "company_name": self.operator.company_name,
                "is_verified": self.operator.is_verified,
                "status": self.operator.status,
            }
        return data
