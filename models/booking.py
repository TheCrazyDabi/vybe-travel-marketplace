"""Enquiry / Quotation / Booking models for VYBE persistent workflow.

Statuses (exact, documented):
Enquiry: interested -> enquiry_sent -> awaiting_operator -> quote_received
  -> awaiting_traveller -> confirmed | rejected | cancelled
  - interested: swipe-right recorded, no details yet
  - enquiry_sent / awaiting_operator: traveller sent details, waiting operator
  - quote_received / awaiting_traveller: operator quoted, waiting traveller
  - confirmed: traveller accepted + details collected, booking created
  - rejected: operator declined or traveller declined quote
  - cancelled: traveller cancelled
Quotation: sent | accepted | declined | superseded
Booking: pending | confirmed | cancelled (demo, no real payment)
"""

from datetime import datetime

from . import db

ENQUIRY_STATUSES = {
    "interested",
    "enquiry_sent",
    "awaiting_operator",
    "quote_received",
    "awaiting_traveller",
    "confirmed",
    "rejected",
    "cancelled",
}

ALLOWED_TRANSITIONS = {
    "interested": {"enquiry_sent", "awaiting_operator", "cancelled"},
    "enquiry_sent": {"awaiting_operator", "quote_received", "rejected", "cancelled"},
    "awaiting_operator": {"quote_received", "rejected", "cancelled"},
    "quote_received": {"awaiting_traveller", "confirmed", "rejected", "cancelled", "awaiting_operator"},
    "awaiting_traveller": {"confirmed", "rejected", "cancelled", "awaiting_operator"},
    "confirmed": set(),
    "rejected": set(),
    "cancelled": set(),
}

TERMINAL_STATUSES = {"confirmed", "rejected", "cancelled"}


class Enquiry(db.Model):
    __tablename__ = "enquiries"

    id = db.Column(db.Integer, primary_key=True)
    traveler_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    package_id = db.Column(db.Integer, db.ForeignKey("travel_packages.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("travel_companies.id"), nullable=False, index=True)
    status = db.Column(db.String(30), nullable=False, default="interested", index=True)
    num_travellers = db.Column(db.Integer, nullable=True, default=1)
    travel_date = db.Column(db.String(30), nullable=True)
    message = db.Column(db.Text, nullable=True)
    total_cost = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    quotations = db.relationship(
        "Quotation", backref="enquiry", cascade="all, delete-orphan",
        order_by="Quotation.created_at",
    )
    booking = db.relationship("Booking", backref="enquiry", uselist=False, cascade="all, delete-orphan")
    package = db.relationship("TravelPackage")

    def can_transition(self, new_status: str) -> bool:
        return new_status in ALLOWED_TRANSITIONS.get(self.status or "interested", set())

    def to_dict(self, include_related=False):
        data = {
            "id": self.id,
            "traveler_id": self.traveler_id,
            "package_id": self.package_id,
            "company_id": self.company_id,
            "status": self.status,
            "num_travellers": self.num_travellers,
            "travel_date": self.travel_date,
            "message": self.message,
            "total_cost": self.total_cost,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "package": self.package.to_dict() if self.package else None,
        }
        if include_related:
            data["quotations"] = [q.to_dict() for q in self.quotations]
            data["booking"] = self.booking.to_dict() if self.booking else None
        return data


class Quotation(db.Model):
    __tablename__ = "quotations"

    id = db.Column(db.Integer, primary_key=True)
    enquiry_id = db.Column(db.Integer, db.ForeignKey("enquiries.id"), nullable=False, index=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    price_per_person = db.Column(db.Integer, nullable=False, default=0)
    total_price = db.Column(db.Integer, nullable=True)
    availability_note = db.Column(db.Text, nullable=True)
    valid_until = db.Column(db.String(30), nullable=True)
    message = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="sent")  # sent|accepted|declined|superseded
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "enquiry_id": self.enquiry_id,
            "operator_id": self.operator_id,
            "price_per_person": self.price_per_person,
            "total_price": self.total_price,
            "availability_note": self.availability_note,
            "valid_until": self.valid_until,
            "message": self.message,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Booking(db.Model):
    __tablename__ = "bookings"

    id = db.Column(db.Integer, primary_key=True)
    enquiry_id = db.Column(db.Integer, db.ForeignKey("enquiries.id"), unique=True, nullable=False)
    traveler_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    package_id = db.Column(db.Integer, db.ForeignKey("travel_packages.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("travel_companies.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default="confirmed")  # pending|confirmed|cancelled
    traveller_details = db.Column(db.JSON, default=dict)
    total_cost = db.Column(db.Integer, nullable=True)
    itinerary_snapshot = db.Column(db.Text, nullable=True)
    terms = db.Column(db.Text, nullable=True)
    payment_status = db.Column(db.String(30), nullable=False, default="simulated_pending")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    confirmed_at = db.Column(db.DateTime, nullable=True)

    # Razorpay payment fields (Phase 2)
    razorpay_order_id = db.Column(db.String(100), nullable=True, index=True)
    razorpay_payment_id = db.Column(db.String(100), nullable=True)
    razorpay_signature = db.Column(db.String(255), nullable=True)
    currency = db.Column(db.String(10), default="INR")
    amount_paid = db.Column(db.Integer, nullable=True)
    payment_method = db.Column(db.String(50), nullable=True)

    package = db.relationship("TravelPackage")

    def to_dict(self):
        return {
            "id": self.id,
            "enquiry_id": self.enquiry_id,
            "traveler_id": self.traveler_id,
            "package_id": self.package_id,
            "company_id": self.company_id,
            "status": self.status,
            "traveller_details": self.traveller_details or {},
            "total_cost": self.total_cost,
            "itinerary_snapshot": self.itinerary_snapshot,
            "terms": self.terms,
            "payment_status": self.payment_status,
            "razorpay_order_id": self.razorpay_order_id,
            "razorpay_payment_id": self.razorpay_payment_id,
            "currency": self.currency or "INR",
            "amount_paid": self.amount_paid,
            "payment_method": self.payment_method,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "confirmed_at": self.confirmed_at.isoformat() if self.confirmed_at else None,
            "package": self.package.to_dict() if self.package else None,
        }
