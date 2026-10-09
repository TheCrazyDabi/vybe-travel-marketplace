"""Shared SQLAlchemy instance + model re-exports to avoid circular imports."""

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Re-export models so `from models import User, TravelPackage, ...` works.
from .user import TravelerProfile, User, UserPreference  # noqa: E402,F401
from .company import TravelCompany, VerificationRecord  # noqa: E402,F401
from .package import TravelPackage  # noqa: E402,F401
from .interaction import Interest  # noqa: E402,F401
from .messaging import Conversation, Message  # noqa: E402,F401

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
]
