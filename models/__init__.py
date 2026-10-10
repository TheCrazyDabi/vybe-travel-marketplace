"""Shared SQLAlchemy instance + model re-exports to avoid circular imports."""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Re-export models so `from models import User, TravelPackage, ...` works.
from .user import TravelerProfile, User, UserPreference  # noqa: E402,F401
from .company import TravelCompany, VerificationRecord  # noqa: E402,F401
from .package import TravelPackage  # noqa: E402,F401
from .interaction import Interest  # noqa: E402,F401
from .messaging import Conversation, Message  # noqa: E402,F401
from .moderation import Report  # noqa: E402,F401
from .booking import Booking, Enquiry, Quotation  # noqa: E402,F401
from .companion import (  # noqa: E402,F401
    CompanionMessage, PackItem, Stop, StopActivity, TripDay, TripPlan,
)
from .custom_offer import CustomOffer  # noqa: E402,F401
from .review import Review  # noqa: E402,F401

__all__ = [
    "db",
    "User",
    "TravelerProfile",
    "UserPreference",
    "TravelCompany",
    "VerificationRecord",
    "TravelPackage",
    "Interest",
    "Conversation",
    "Message",
    "Report",
    "Enquiry",
    "Quotation",
    "Booking",
    "TripPlan",
    "TripDay",
    "Stop",
    "StopActivity",
    "PackItem",
    "CompanionMessage",
    "CustomOffer",
    "Review",
]
