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

    # --- Phase 2: 5-step onboarding (all nullable, additive, backward compatible) ---
    # Step 1: mood
    travel_moods = db.Column(db.JSON, default=list)  # 11 moods multi-select
    travel_pace = db.Column(db.String(20), nullable=True)  # slow|balanced|packed
    trip_desires = db.Column(db.JSON, default=list)  # relaxation|excitement|romance|...
    # Step 2: destination + activities
    destination_prefs = db.Column(db.JSON, default=list)
    activity_prefs = db.Column(db.JSON, default=list)
    preferred_destinations = db.Column(db.JSON, default=list)
    avoid_destinations = db.Column(db.JSON, default=list)
    preferred_region_text = db.Column(db.String(200), nullable=True)
    # Step 3: budget + requirements
    start_city = db.Column(db.String(120), nullable=True)
    destination_text = db.Column(db.String(200), nullable=True)
    budget_per_person = db.Column(db.Integer, nullable=True)
    budget_flex_pct = db.Column(db.Integer, nullable=True, default=20)
    travel_start_date = db.Column(db.String(20), nullable=True)
    travel_end_date = db.Column(db.String(20), nullable=True)
    date_flexible = db.Column(db.Boolean, nullable=True, default=True)
    num_travellers = db.Column(db.Integer, nullable=True, default=2)
    accommodation_prefs = db.Column(db.JSON, default=list)
    transport_prefs = db.Column(db.JSON, default=list)
    trip_mode = db.Column(db.String(20), nullable=True)  # private|group
    # Step 4: style
    travel_style = db.Column(db.String(20), nullable=True)  # budget|comfort|premium|luxury
    group_size_pref = db.Column(db.String(30), nullable=True)
    itinerary_pref = db.Column(db.String(20), nullable=True)  # planned|flexible
    priority = db.Column(db.String(20), nullable=True)  # price|comfort|uniqueness
    disliked_activities = db.Column(db.JSON, default=list)
    accessibility_notes = db.Column(db.Text, nullable=True)
    dietary_notes = db.Column(db.Text, nullable=True)
    other_notes = db.Column(db.Text, nullable=True)
    ideal_trip_text = db.Column(db.Text, nullable=True)
    onboarding_completed = db.Column(db.Boolean, default=False)
    onboarding_step = db.Column(db.Integer, default=1)

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
            # Phase 2 extras
            "travel_moods": self.travel_moods or [],
            "travel_pace": self.travel_pace,
            "trip_desires": self.trip_desires or [],
            "destination_prefs": self.destination_prefs or [],
            "activity_prefs": self.activity_prefs or [],
            "preferred_destinations": self.preferred_destinations or [],
            "avoid_destinations": self.avoid_destinations or [],
            "preferred_region_text": self.preferred_region_text,
            "start_city": self.start_city,
            "destination_text": self.destination_text,
            "budget_per_person": self.budget_per_person,
            "budget_flex_pct": self.budget_flex_pct if self.budget_flex_pct is not None else 20,
            "travel_start_date": self.travel_start_date,
            "travel_end_date": self.travel_end_date,
            "date_flexible": self.date_flexible if self.date_flexible is not None else True,
            "num_travellers": self.num_travellers,
            "accommodation_prefs": self.accommodation_prefs or [],
            "transport_prefs": self.transport_prefs or [],
            "trip_mode": self.trip_mode,
            "travel_style": self.travel_style,
            "group_size_pref": self.group_size_pref,
            "itinerary_pref": self.itinerary_pref,
            "priority": self.priority,
            "disliked_activities": self.disliked_activities or [],
            "accessibility_notes": self.accessibility_notes,
            "dietary_notes": self.dietary_notes,
            "other_notes": self.other_notes,
            "ideal_trip_text": self.ideal_trip_text,
            "onboarding_completed": bool(self.onboarding_completed),
            "onboarding_step": self.onboarding_step or 1,
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
