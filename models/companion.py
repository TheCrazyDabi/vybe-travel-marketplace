"""Roamly companion models: trip itinerary, packing checklist, AI chat history.

Seeded per-user from data/singapore.json on first visit (lazy provision),
so each traveler gets their own checkable copy. Demo-labeled sample data.
"""

from datetime import datetime

from . import db


class TripPlan(db.Model):
    __tablename__ = "trip_plans"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    title = db.Column(db.String(160), nullable=False)
    destination = db.Column(db.String(120), nullable=False)
    country = db.Column(db.String(120), nullable=True)
    dates = db.Column(db.String(120), nullable=True)
    duration_days = db.Column(db.Integer, default=5)
    traveler_count = db.Column(db.Integer, default=1)
    status = db.Column(db.String(20), default="upcoming")
    summary = db.Column(db.Text, nullable=True)
    meeting_point = db.Column(db.String(255), nullable=True)
    announcements = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    days = db.relationship("TripDay", backref="trip", cascade="all, delete-orphan",
                           order_by="TripDay.day_number")

    def to_dict(self, include_days=False):
        d = {
            "id": self.id, "title": self.title, "destination": self.destination,
            "country": self.country, "dates": self.dates,
            "duration_days": self.duration_days, "traveler_count": self.traveler_count,
            "status": self.status, "summary": self.summary,
            "meeting_point": self.meeting_point,
            "announcements": self.announcements or [],
        }
        if include_days:
            d["days"] = [day.to_dict() for day in self.days]
        return d


class TripDay(db.Model):
    __tablename__ = "trip_days"

    id = db.Column(db.Integer, primary_key=True)
    trip_id = db.Column(db.Integer, db.ForeignKey("trip_plans.id"), nullable=False, index=True)
    day_number = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(160), nullable=False)
    date = db.Column(db.String(80), nullable=True)

    stops = db.relationship("Stop", backref="day", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id, "day_number": self.day_number,
            "title": self.title, "date": self.date,
            "stops": [s.to_dict() for s in self.stops],
        }


class Stop(db.Model):
    __tablename__ = "trip_stops"

    id = db.Column(db.Integer, primary_key=True)
    day_id = db.Column(db.Integer, db.ForeignKey("trip_days.id"), nullable=False, index=True)
    key = db.Column(db.String(60), nullable=True)
    name = db.Column(db.String(160), nullable=False)
    category = db.Column(db.String(80), nullable=True)
    time_slot = db.Column(db.String(40), nullable=True)
    duration = db.Column(db.String(40), nullable=True)
    short_desc = db.Column(db.Text, nullable=True)
    full_desc = db.Column(db.Text, nullable=True)
    tips = db.Column(db.JSON, default=list)
    precautions = db.Column(db.JSON, default=list)
    visited = db.Column(db.Boolean, default=False)
    departure_ack = db.Column(db.Boolean, default=False)

    activities = db.relationship("StopActivity", backref="stop", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id, "key": self.key, "name": self.name,
            "category": self.category, "time_slot": self.time_slot,
            "duration": self.duration, "short": self.short_desc,
            "full": self.full_desc, "tips": self.tips or [],
            "precautions": self.precautions or [],
            "visited": self.visited, "departure_ack": self.departure_ack,
            "activities": [a.to_dict() for a in self.activities],
        }


class StopActivity(db.Model):
    __tablename__ = "stop_activities"

    id = db.Column(db.Integer, primary_key=True)
    stop_id = db.Column(db.Integer, db.ForeignKey("trip_stops.id"), nullable=False, index=True)
    key = db.Column(db.String(60), nullable=True)
    title = db.Column(db.String(255), nullable=False)
    done = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {"id": self.id, "key": self.key, "title": self.title, "done": self.done}


class PackItem(db.Model):
    __tablename__ = "pack_items"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    key = db.Column(db.String(60), nullable=True)
    title = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(40), nullable=False, default="essentials")
    packed = db.Column(db.Boolean, default=False)
    belonging = db.Column(db.Boolean, default=False)
    custom = db.Column(db.Boolean, default=False)

    def to_dict(self):
        return {
            "id": self.id, "key": self.key, "title": self.title,
            "category": self.category, "packed": self.packed,
            "belonging": self.belonging, "custom": self.custom,
        }


class CompanionMessage(db.Model):
    __tablename__ = "companion_messages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    sender = db.Column(db.String(10), nullable=False, default="user")  # user|ai
    body = db.Column(db.Text, nullable=False)
    chips = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "sender": self.sender, "body": self.body,
            "chips": self.chips or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
