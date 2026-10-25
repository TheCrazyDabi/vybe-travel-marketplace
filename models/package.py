from datetime import datetime

from . import db


class TravelPackage(db.Model):
    __tablename__ = "travel_packages"

    id = db.Column(db.Integer, primary_key=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("travel_companies.id"), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    destination = db.Column(db.String(120), nullable=False, index=True)
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    cover_image = db.Column(db.String(1024), nullable=True)
    short_desc = db.Column(db.String(500), nullable=True)
    itinerary = db.Column(db.Text, nullable=True)
    price = db.Column(db.Integer, nullable=False, default=0)
    currency = db.Column(db.String(10), default="INR")
    duration_days = db.Column(db.Integer, nullable=False, default=1)
    available_dates = db.Column(db.String(255), nullable=True)
    group_size = db.Column(db.String(64), nullable=True)
    included = db.Column(db.JSON, default=list)
    excluded = db.Column(db.JSON, default=list)
    accommodation = db.Column(db.String(255), nullable=True)
    transportation = db.Column(db.String(255), nullable=True)
    activities = db.Column(db.JSON, default=list)

    region_tags = db.Column(db.JSON, default=list)
    climate_tags = db.Column(db.JSON, default=list)
    scenery_tags = db.Column(db.JSON, default=list)
    interest_tags = db.Column(db.JSON, default=list)
    mood_tags = db.Column(db.JSON, default=list)

    cancellation_terms = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    # Soft-delete / archival (Feature B): never hard-delete packages with
    # history. Deleted packages are hidden from discovery but rows stay.
    is_deleted = db.Column(db.Boolean, default=False, index=True)
    deleted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Phase 2: package management extras (additive, all nullable)
    nights = db.Column(db.Integer, nullable=True)
    min_group_size = db.Column(db.Integer, nullable=True)
    max_group_size = db.Column(db.Integer, nullable=True)
    suitable_travel_styles = db.Column(db.JSON, default=list)
    suitable_groups = db.Column(db.JSON, default=list)
    capacity = db.Column(db.Integer, nullable=True)
    seats_remaining = db.Column(db.Integer, nullable=True)
    customization_options = db.Column(db.Text, nullable=True)
    images = db.Column(db.JSON, default=list)
    departure_dates_list = db.Column(db.JSON, default=list)

    # TruePrice + demo trust layer (additive, nullable)
    price_breakdown = db.Column(db.JSON, nullable=True)
    price_kind = db.Column(db.String(20), nullable=True)  # demo_estimate|operator_quote|confirmed
    price_confirmed_at = db.Column(db.DateTime, nullable=True)
    is_demo = db.Column(db.Boolean, default=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Lifecycle & Expiry (Phase 2 / Prompt 4)
    status = db.Column(db.String(30), default="active", index=True)  # draft|active|inactive|expired|archived
    trip_start_date = db.Column(db.DateTime, nullable=True)
    trip_end_date = db.Column(db.DateTime, nullable=True)
    booking_deadline = db.Column(db.DateTime, nullable=True)
    valid_until = db.Column(db.DateTime, nullable=True)

    @property
    def is_bookable(self) -> bool:
        if not self.is_active or bool(self.is_deleted):
            return False
        if (self.status or "active") not in ("active",):
            return False
        from datetime import timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if self.booking_deadline:
            bd = self.booking_deadline.replace(tzinfo=None) if getattr(self.booking_deadline, "tzinfo", None) else self.booking_deadline
            if bd < now:
                return False
        if self.valid_until:
            vu = self.valid_until.replace(tzinfo=None) if getattr(self.valid_until, "tzinfo", None) else self.valid_until
            if vu < now:
                return False
        if self.trip_start_date:
            ts = self.trip_start_date.replace(tzinfo=None) if getattr(self.trip_start_date, "tzinfo", None) else self.trip_start_date
            if ts < now:
                return False
        if isinstance(self.seats_remaining, int) and self.seats_remaining <= 0:
            return False
        return True

    def check_and_update_expiry(self) -> bool:
        """Evaluate if package has expired and update status in-place if needed."""
        from datetime import timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expired = False
        vu = self.valid_until.replace(tzinfo=None) if (self.valid_until and getattr(self.valid_until, "tzinfo", None)) else self.valid_until
        bd = self.booking_deadline.replace(tzinfo=None) if (self.booking_deadline and getattr(self.booking_deadline, "tzinfo", None)) else self.booking_deadline
        ts = self.trip_start_date.replace(tzinfo=None) if (self.trip_start_date and getattr(self.trip_start_date, "tzinfo", None)) else self.trip_start_date

        if vu and vu < now:
            expired = True
        elif bd and bd < now:
            expired = True
        elif ts and ts < now:
            expired = True

        if expired and (self.status or "active") == "active":
            self.status = "expired"
            self.is_active = False
            return True
        return False

    def to_dict(self, include_operator=True):
        data = {
            "id": self.id,
            "title": self.title,
            "destination": self.destination,
            "lat": self.lat,
            "lng": self.lng,
            "cover_image": self.cover_image,
            "short_desc": self.short_desc,
            "itinerary": self.itinerary,
            "price": self.price,
            "currency": self.currency,
            "duration_days": self.duration_days,
            "available_dates": self.available_dates,
            "group_size": self.group_size,
            "included": self.included or [],
            "excluded": self.excluded or [],
            "accommodation": self.accommodation,
            "transportation": self.transportation,
            "activities": self.activities or [],
            "region_tags": self.region_tags or [],
            "climate_tags": self.climate_tags or [],
            "scenery_tags": self.scenery_tags or [],
            "interest_tags": self.interest_tags or [],
            "mood_tags": self.mood_tags or [],
            "cancellation_terms": self.cancellation_terms,
            "is_active": self.is_active,
            "is_deleted": bool(getattr(self, "is_deleted", False)),
            "deleted_at": self.deleted_at.isoformat() if getattr(self, "deleted_at", None) else None,
            # Phase 2 extras
            "nights": self.nights,
            "min_group_size": self.min_group_size,
            "max_group_size": self.max_group_size,
            "suitable_travel_styles": self.suitable_travel_styles or [],
            "suitable_groups": self.suitable_groups or [],
            "capacity": self.capacity,
            "seats_remaining": self.seats_remaining,
            "customization_options": self.customization_options,
            "images": self.images or [],
            "departure_dates_list": self.departure_dates_list or [],
            "price_breakdown": self.price_breakdown,
            "price_kind": self.price_kind,
            "price_confirmed_at": self.price_confirmed_at.isoformat() if self.price_confirmed_at else None,
            "is_demo": bool(self.is_demo),
            "status": self.status or ("active" if self.is_active else "inactive"),
            "trip_start_date": self.trip_start_date.isoformat() if self.trip_start_date else None,
            "trip_end_date": self.trip_end_date.isoformat() if self.trip_end_date else None,
            "booking_deadline": self.booking_deadline.isoformat() if self.booking_deadline else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "is_bookable": self.is_bookable,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            # availability derived from real data only (never fabricated)
            "availability_status": (
                "Available"
                if (self.seats_remaining is None or (self.seats_remaining or 0) > 0) and self.is_active
                else "Sold out / Hidden"
            ),
        }
        if include_operator and self.operator:
            data["operator"] = {
                "id": self.operator.id,
                "company_name": self.operator.company_name,
                "is_verified": self.operator.is_verified,
                "status": self.operator.status,
            }
        return data


class PackageImage(db.Model):
    __tablename__ = "package_images"

    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.Integer, db.ForeignKey("travel_packages.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_path = db.Column(db.String(1024), nullable=False, index=True)
    url = db.Column(db.String(1024), nullable=True)
    is_cover = db.Column(db.Boolean, default=False)
    file_size = db.Column(db.Integer, nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    package = db.relationship("TravelPackage", backref=db.backref("package_image_records", cascade="all, delete-orphan", lazy="dynamic"))

    def to_dict(self):
        return {
            "id": self.id,
            "package_id": self.package_id,
            "storage_path": self.storage_path,
            "url": self.url,
            "is_cover": bool(self.is_cover),
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
