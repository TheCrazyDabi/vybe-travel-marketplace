from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    # traveler | operator | admin
    role = db.Column(db.String(20), nullable=False, default="traveler")
    # active | suspended (admin moderation)
    status = db.Column(db.String(20), nullable=False, default="active")
    status_reason = db.Column(db.String(255), nullable=True)
    age_range = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    profile = db.relationship(
        "TravelerProfile", backref="user", uselist=False, cascade="all, delete-orphan"
    )
    preference = db.relationship(
        "UserPreference", backref="user", uselist=False, cascade="all, delete-orphan"
    )
    companies = db.relationship(
        "TravelCompany", backref="owner", cascade="all, delete-orphan"
    )

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "status": self.status,
            "age_range": self.age_range,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TravelerProfile(db.Model):
    __tablename__ = "traveler_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    budget_max = db.Column(db.Integer, nullable=True)
    duration_days = db.Column(db.Integer, nullable=True)
    preferred_regions = db.Column(db.JSON, default=list)  # e.g. ["mountains","beaches"]
    preferred_climate = db.Column(db.JSON, default=list)  # ["cool","warm"]
    scenery = db.Column(db.JSON, default=list)
    interests = db.Column(db.JSON, default=list)
    group_type = db.Column(db.String(20), nullable=True)  # solo|friends|couple|family
    current_mood = db.Column(db.String(40), nullable=True)
    avoid = db.Column(db.JSON, default=list)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "budget_max": self.budget_max,
            "duration_days": self.duration_days,
            "preferred_regions": self.preferred_regions or [],
            "preferred_climate": self.preferred_climate or [],
            "scenery": self.scenery or [],
            "interests": self.interests or [],
            "group_type": self.group_type,
            "current_mood": self.current_mood,
            "avoid": self.avoid or [],
        }


class UserPreference(db.Model):
    """Adaptive weights: long-term interests vs current trip mood."""

    __tablename__ = "user_preferences"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    long_term = db.Column(db.JSON, default=dict)
    mood_weights = db.Column(db.JSON, default=dict)
    weights = db.Column(
        db.JSON,
        default=lambda: {
            "interests": 0.25,
            "region_scenery": 0.20,
            "budget": 0.20,
            "duration": 0.15,
            "climate": 0.10,
            "mood": 0.10,
        },
    )
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
