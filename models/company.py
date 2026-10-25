from datetime import datetime
import os

from . import db


class TravelCompany(db.Model):
    __tablename__ = "travel_companies"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    company_name = db.Column(db.String(160), nullable=False)
    business_email = db.Column(db.String(255), nullable=False)
    contact_details = db.Column(db.String(255), nullable=True)
    description = db.Column(db.Text, nullable=True)
    licence_info = db.Column(db.String(255), nullable=True)
    document_path = db.Column(db.String(512), nullable=True)
    service_regions = db.Column(db.JSON, default=list)
    logo = db.Column(db.String(512), nullable=True)
    # pending | approved | rejected
    status = db.Column(db.String(20), default="pending", index=True)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Phase 2: operator onboarding extras (additive)
    contact_person = db.Column(db.String(120), nullable=True)
    business_type = db.Column(db.String(80), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    operating_regions = db.Column(db.JSON, default=list)
    # Trust layer: marks seeded sample operators (displayed as demo, never as verified)
    is_demo = db.Column(db.Boolean, default=False)

    packages = db.relationship(
        "TravelPackage", backref="operator", cascade="all, delete-orphan"
    )
    verifications = db.relationship(
        "VerificationRecord", backref="company", cascade="all, delete-orphan"
    )

    @property
    def document_filename(self) -> str | None:
        """Return a clean, sanitized display name without internal UUIDs or filesystem paths."""
        if not self.document_path:
            return None
        name = os.path.basename(self.document_path.replace("\\", "/"))
        if len(name) > 33 and name[32] == "_":
            return name[33:]
        return name

    def to_dict(self):
        return {
            "id": self.id,
            "company_name": self.company_name,
            "business_email": self.business_email,
            "contact_details": self.contact_details,
            "description": self.description,
            "service_regions": self.service_regions or [],
            "logo": self.logo,
            "status": self.status,
            "is_verified": self.is_verified,
            "contact_person": self.contact_person,
            "business_type": self.business_type,
            "phone": self.phone,
            "operating_regions": self.operating_regions or self.service_regions or [],
            "is_demo": bool(self.is_demo),
            "has_document": bool(self.document_path),
            "document_filename": self.document_filename,
        }


class VerificationRecord(db.Model):
    __tablename__ = "verification_records"

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("travel_companies.id"), nullable=False)
    submitted_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.String(20), default="pending")  # pending|approved|rejected
    reviewer_note = db.Column(db.Text, nullable=True)
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime, nullable=True)
