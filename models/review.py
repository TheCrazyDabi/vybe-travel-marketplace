"""Verified-trip reviews. Eligibility: a confirmed booking by the same
traveller for the same package. One review per booking (unique booking_id).
No fabricated reviews: demo packages ship with zero reviews.
"""

from datetime import datetime

from . import db

REVIEW_STATUSES = {"visible", "flagged", "removed"}


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("bookings.id"), unique=True, nullable=False)
    traveler_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    package_id = db.Column(db.Integer, db.ForeignKey("travel_packages.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("travel_companies.id"), nullable=False, index=True)
    rating = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="visible", index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "booking_id": self.booking_id,
            "traveler_id": self.traveler_id,
            "package_id": self.package_id,
            "company_id": self.company_id,
            "rating": self.rating,
            "text": self.text,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
