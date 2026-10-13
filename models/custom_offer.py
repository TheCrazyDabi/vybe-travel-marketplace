"""Custom-offer workflow: traveller requests a tailored trip, operator revises.

States: pending -> offer_submitted -> revision_requested -> offer_submitted ...
  -> accepted | rejected | expired
Revisions form a chain via parent_id (original quotation history preserved).
Acceptance never implies payment/inventory — booking workflow decides that.
"""

from datetime import datetime

from . import db

OFFER_STATUSES = {
    "pending",
    "offer_submitted",
    "revision_requested",
    "accepted",
    "rejected",
    "expired",
}


class CustomOffer(db.Model):
    __tablename__ = "custom_offers"

    id = db.Column(db.Integer, primary_key=True)
    traveler_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    package_id = db.Column(db.Integer, db.ForeignKey("travel_packages.id"), nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey("travel_companies.id"), nullable=False, index=True)
    enquiry_id = db.Column(db.Integer, db.ForeignKey("enquiries.id"), nullable=True, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("custom_offers.id"), nullable=True, index=True)
    version = db.Column(db.Integer, nullable=False, default=1)
    status = db.Column(db.String(30), nullable=False, default="pending", index=True)
    # traveller requirements
    travel_dates = db.Column(db.String(120), nullable=True)
    num_travellers = db.Column(db.Integer, nullable=True, default=2)
    desired_budget = db.Column(db.Integer, nullable=True)
    accommodation_pref = db.Column(db.String(255), nullable=True)
    itinerary_changes = db.Column(db.Text, nullable=True)
    transport_reqs = db.Column(db.String(255), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    # operator revision
    revised_price = db.Column(db.Integer, nullable=True)
    revised_itinerary = db.Column(db.Text, nullable=True)
    inclusions = db.Column(db.JSON, default=list)
    exclusions = db.Column(db.JSON, default=list)
    additional_charges = db.Column(db.JSON, default=list)
    valid_until = db.Column(db.String(30), nullable=True)
    operator_note = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    package = db.relationship("TravelPackage")
    revisions = db.relationship(
        "CustomOffer", backref=db.backref("parent", remote_side="CustomOffer.id"),
        cascade="all, delete-orphan",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "traveler_id": self.traveler_id,
            "package_id": self.package_id,
            "company_id": self.company_id,
            "enquiry_id": self.enquiry_id,
            "parent_id": self.parent_id,
            "version": self.version,
            "status": self.status,
            "travel_dates": self.travel_dates,
            "num_travellers": self.num_travellers,
            "desired_budget": self.desired_budget,
            "accommodation_pref": self.accommodation_pref,
            "itinerary_changes": self.itinerary_changes,
            "transport_reqs": self.transport_reqs,
            "notes": self.notes,
            "revised_price": self.revised_price,
            "revised_itinerary": self.revised_itinerary,
            "inclusions": self.inclusions or [],
            "exclusions": self.exclusions or [],
            "additional_charges": self.additional_charges or [],
            "valid_until": self.valid_until,
            "operator_note": self.operator_note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "package": self.package.to_dict() if self.package else None,
        }
