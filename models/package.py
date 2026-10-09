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
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

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
        }
        if include_operator and self.operator:
            data["operator"] = {
                "id": self.operator.id,
                "company_name": self.operator.company_name,
                "is_verified": self.operator.is_verified,
                "status": self.operator.status,
            }
        return data
