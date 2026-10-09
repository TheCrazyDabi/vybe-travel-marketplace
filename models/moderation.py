"""User reports + moderation actions (hackathon-minimal safety workflow)."""

from datetime import datetime

from . import db


class Report(db.Model):
    """A traveler/operator flags a user, package or company for admin review."""

    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    # user | package | company
    target_type = db.Column(db.String(20), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text, nullable=True)
    # new | review | resolved | dismissed
    status = db.Column(db.String(20), nullable=False, default="new", index=True)
    action_taken = db.Column(db.String(255), nullable=True)
    handled_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    handled_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reporter = db.relationship("User", foreign_keys=[reporter_id])
    handler = db.relationship("User", foreign_keys=[handled_by])

    def to_dict(self):
        return {
            "id": self.id,
            "reporter_id": self.reporter_id,
            "reporter_email": self.reporter.email if self.reporter else None,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "reason": self.reason,
            "details": self.details,
            "status": self.status,
            "action_taken": self.action_taken,
            "handled_by": self.handled_by,
            "handled_at": self.handled_at.isoformat() if self.handled_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
