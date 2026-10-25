"""Security Audit Event Logging model for VYBE."""

from datetime import datetime
from . import db


class AuditEvent(db.Model):
    __tablename__ = "audit_events"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    action = db.Column(db.String(100), nullable=False, index=True)
    target_type = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.String(100), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    details = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    @classmethod
    def log(cls, action: str, user_id=None, target_type=None, target_id=None, details=None, request=None):
        """Helper to create and save an audit event safely."""
        ip = None
        ua = None
        if request:
            ip = request.headers.get("X-Forwarded-For", request.remote_addr)
            if ip and "," in ip:
                ip = ip.split(",")[0].strip()
            ua = (request.user_agent.string if request.user_agent else "")[:255]

        evt = cls(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            ip_address=ip,
            user_agent=ua,
            details=details or {},
        )
        try:
            db.session.add(evt)
            db.session.commit()
            return evt
        except Exception:
            db.session.rollback()
            return None

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "details": self.details or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
