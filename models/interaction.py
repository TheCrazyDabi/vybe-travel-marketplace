from datetime import datetime

from . import db


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
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "package": self.package.to_dict() if self.package else None,
        }
