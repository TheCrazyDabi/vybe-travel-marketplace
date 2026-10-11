from datetime import datetime

from . import db

# Traveller rejection feedback vocabulary (Feature A). Stored as keys in
# Interest.reason (<=50 chars); labels live here + template/JS.
REJECTION_REASONS = (
    ("too_expensive", "Too expensive"),
    ("destination", "Destination does not interest me"),
    ("dates_duration", "Dates or duration do not suit me"),
    ("activities", "Activities do not interest me"),
    ("insufficient_details", "Insufficient package details"),
    ("transport_stay", "Transport or accommodation concerns"),
    ("other", "Other"),
)

REJECTION_REASON_KEYS = {k for k, _ in REJECTION_REASONS}
REJECTION_REASON_LABELS = dict(REJECTION_REASONS)


class Interest(db.Model):
    """Swipe / save record. action: like | pass | save."""

    __tablename__ = "interests"

    id = db.Column(db.Integer, primary_key=True)
    traveler_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    package_id = db.Column(
        db.Integer, db.ForeignKey("travel_packages.id"), nullable=False, index=True
    )
    action = db.Column(db.String(10), nullable=False, default="like")
    reason = db.Column(db.String(50), nullable=True)  # why passed (optional)
    # Feature A: optional free-text comment + feedback timestamp.
    comment = db.Column(db.Text, nullable=True)
    feedback_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("traveler_id", "package_id", "action", name="uq_interest"),
    )

    package = db.relationship("TravelPackage", backref="interests")

    def to_dict(self):
        return {
            "id": self.id,
            "package_id": self.package_id,
            "action": self.action,
            "reason": self.reason,
            "comment": self.comment,
            "feedback_at": self.feedback_at.isoformat() if self.feedback_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "package": self.package.to_dict() if self.package else None,
        }
