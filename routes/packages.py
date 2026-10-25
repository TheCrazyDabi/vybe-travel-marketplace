from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from models import Interest, TravelPackage, db
from models.booking import Enquiry
from services.recommendation import score_package

packages_bp = Blueprint("packages", __name__)

PACKAGE_FIELDS = (
    "title", "destination", "cover_image", "short_desc", "itinerary",
    "price", "currency", "duration_days", "group_size", "accommodation",
    "transportation", "included", "excluded", "activities", "region_tags",
    "climate_tags", "scenery_tags", "interest_tags", "mood_tags",
    "lat", "lng", "is_active", "available_dates", "cancellation_terms",
    # Phase 2 extras
    "nights", "min_group_size", "max_group_size", "suitable_travel_styles",
    "suitable_groups", "capacity", "seats_remaining", "customization_options",
    "images", "departure_dates_list", "price_breakdown", "price_kind",
)


@packages_bp.get("/packages")
def list_page():
    pkgs = (
        TravelPackage.query.filter_by(is_active=True, is_deleted=False)
        .order_by(TravelPackage.price.asc())
        .all()
    )
    return render_template("packages.html", packages=pkgs)


@packages_bp.get("/packages/<int:pkg_id>")
def detail_page(pkg_id: int):
    pkg = TravelPackage.query.get_or_404(pkg_id)
    score, reasons, explanation = None, [], ""
    if current_user.is_authenticated and current_user.profile:
        score, reasons, explanation = score_package(pkg, current_user.profile.to_dict())
    # traveller's enquiry for this package (if any)
    my_enquiry = None
    quotations = []
    my_offers = []
    if current_user.is_authenticated:
        my_enquiry = Enquiry.query.filter_by(
            traveler_id=current_user.id, package_id=pkg.id
        ).order_by(Enquiry.updated_at.desc()).first()
        if my_enquiry:
            quotations = sorted(my_enquiry.quotations, key=lambda q: q.id or 0)
    from models.custom_offer import CustomOffer
    if current_user.is_authenticated:
        my_offers = CustomOffer.query.filter_by(
            traveler_id=current_user.id, package_id=pkg.id
        ).order_by(CustomOffer.version.desc()).all()
    from models.review import Review
    reviews = Review.query.filter_by(package_id=pkg.id, status="visible").order_by(
        Review.created_at.desc()).limit(20).all()
    return render_template(
        "package_detail.html", pkg=pkg, score=score, reasons=reasons, explanation=explanation,
        my_enquiry=my_enquiry, quotations=quotations, my_offers=my_offers, reviews=reviews,
    )


def _check_and_expire_packages():
    """Auto-expire packages whose deadlines or trip dates have passed."""
    from datetime import datetime as _dt
    now = _dt.utcnow()
    query = TravelPackage.query.filter(
        TravelPackage.is_active == True,
        TravelPackage.is_deleted == False,
        (
            ((TravelPackage.valid_until != None) & (TravelPackage.valid_until < now)) |
            ((TravelPackage.booking_deadline != None) & (TravelPackage.booking_deadline < now)) |
            ((TravelPackage.trip_start_date != None) & (TravelPackage.trip_start_date < now))
        )
    )
    count = 0
    for p in query.all():
        p.status = "expired"
        p.is_active = False
        count += 1
    if count > 0:
        db.session.commit()
    return count


# ---- JSON API ----
@packages_bp.get("/api/packages")
def api_list():
    _check_and_expire_packages()
    
    q = TravelPackage.query.filter_by(is_deleted=False)
    
    # Status filter: default to active public packages
    status = request.args.get("status", "active").lower()
    if status == "all" and current_user.is_authenticated and current_user.role in ("operator", "admin"):
        pass
    elif status:
        q = q.filter(TravelPackage.status == status, TravelPackage.is_active == True)
    else:
        q = q.filter_by(is_active=True)

    dest = (request.args.get("destination") or "").strip()
    if dest:
        q = q.filter(TravelPackage.destination.ilike(f"%{dest}%"))

    # Sorting (only when explicitly requested, preserving default ordering)
    sort_by = (request.args.get("sort") or "").lower()
    if sort_by == "price_asc":
        q = q.order_by(TravelPackage.price.asc())
    elif sort_by == "price_desc":
        q = q.order_by(TravelPackage.price.desc())
    elif sort_by == "duration":
        q = q.order_by(TravelPackage.duration_days.asc())
    elif sort_by == "newest":
        q = q.order_by(TravelPackage.created_at.desc())

    # Pagination
    if "page" in request.args or "per_page" in request.args:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(100, max(1, int(request.args.get("per_page", 20))))
        total = q.count()
        pkgs = q.offset((page - 1) * per_page).limit(per_page).all()
        return jsonify({
            "packages": [p.to_dict() for p in pkgs],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        })

    pkgs = q.all()
    return jsonify({"packages": [p.to_dict() for p in pkgs]})


@packages_bp.get("/api/packages/<int:pkg_id>")
def api_detail(pkg_id: int):
    pkg = TravelPackage.query.get_or_404(pkg_id)
    return jsonify({"package": pkg.to_dict()})


def _require_operator_company():
    if not current_user.is_authenticated or current_user.role not in ("operator", "admin"):
        abort(403)
    from models import TravelCompany

    company = TravelCompany.query.filter_by(user_id=current_user.id).first()
    if not company and current_user.role != "admin":
        abort(403, description="operator company profile required")
    # Only approved operators may publish (admins bypass for demo management).
    if (company and company.status != "approved"
            and current_user.role != "admin"):
        abort(403, description="company verification required before publishing")
    return company


def _validate_package_payload(data: dict):
    if not (data.get("title") or "").strip() or not (data.get("destination") or "").strip():
        return "title, destination required"
    if data.get("price") is None:
        return "title, destination, price required"
    try:
        price = int(data.get("price", 0))
    except (TypeError, ValueError):
        return "price must be an integer"
    if price < 0:
        return "price must be >= 0"
    try:
        days = int(data.get("duration_days", 1))
    except (TypeError, ValueError):
        return "duration_days must be an integer"
    if days < 1 or days > 365:
        return "duration_days must be 1..365"
    for f in ("min_group_size", "max_group_size", "capacity", "seats_remaining", "nights"):
        if data.get(f) not in (None, ""):
            try:
                v = int(data[f])
            except (TypeError, ValueError):
                return f"{f} must be an integer"
            if v < 0:
                return f"{f} must be >= 0"
    ming = data.get("min_group_size")
    maxg = data.get("max_group_size")
    try:
        if ming not in (None, "") and maxg not in (None, "") and int(ming) > int(maxg):
            return "min_group_size cannot exceed max_group_size"
    except (TypeError, ValueError):
        pass
    return None


@packages_bp.post("/api/packages")
@login_required
def api_create():
    company = _require_operator_company()
    data = request.get_json(force=True, silent=True) or {}
    err = _validate_package_payload(data)
    if err:
        return jsonify({"error": err}), 400
    pkg = TravelPackage(
        operator_id=company.id if company else None,
        title=data["title"].strip(),
        destination=data["destination"].strip(),
        cover_image=data.get("cover_image"),
        short_desc=data.get("short_desc"),
        itinerary=data.get("itinerary"),
        price=int(data.get("price", 0)),
        currency=data.get("currency", "INR"),
        duration_days=int(data.get("duration_days", 1)),
        group_size=data.get("group_size"),
        accommodation=data.get("accommodation"),
        transportation=data.get("transportation"),
        included=data.get("included", []),
        excluded=data.get("excluded", []),
        activities=data.get("activities", []),
        region_tags=data.get("region_tags", []),
        climate_tags=data.get("climate_tags", []),
        scenery_tags=data.get("scenery_tags", []),
        interest_tags=data.get("interest_tags", []),
        mood_tags=data.get("mood_tags", []),
        lat=data.get("lat"),
        lng=data.get("lng"),
        available_dates=data.get("available_dates"),
        cancellation_terms=data.get("cancellation_terms"),
        nights=data.get("nights"),
        min_group_size=data.get("min_group_size"),
        max_group_size=data.get("max_group_size"),
        suitable_travel_styles=data.get("suitable_travel_styles", []),
        suitable_groups=data.get("suitable_groups", []),
        capacity=data.get("capacity"),
        seats_remaining=data.get("seats_remaining", data.get("capacity")),
        customization_options=data.get("customization_options"),
        images=data.get("images", []),
        departure_dates_list=data.get("departure_dates_list", []),
        price_breakdown=data.get("price_breakdown"),
        price_kind=(data.get("price_kind") if current_user.role == "admin"
                    and data.get("price_kind") in ("demo_estimate", "operator_quote", "confirmed")
                    else "operator_quote"),
    )
    from datetime import datetime as _dt
    pkg.price_confirmed_at = _dt.utcnow()
    # admin without company: attach to first approved company for demo
    if pkg.operator_id is None:
        from models import TravelCompany

        fallback = TravelCompany.query.filter_by(status="approved").first()
        if not fallback:
            return jsonify({"error": "no operator company available"}), 400
        pkg.operator_id = fallback.id
    # default nights from days
    if pkg.nights is None and pkg.duration_days:
        pkg.nights = max(0, pkg.duration_days - 1)
    db.session.add(pkg)
    db.session.commit()
    return jsonify({"package": pkg.to_dict()}), 201


@packages_bp.put("/api/packages/<int:pkg_id>")
@login_required
def api_update(pkg_id: int):
    pkg = TravelPackage.query.get_or_404(pkg_id)
    company = _require_operator_company()
    if company and pkg.operator_id != company.id and current_user.role != "admin":
        abort(403)
    data = request.get_json(force=True, silent=True) or {}
    if "price" in data:
        try:
            if int(data["price"]) < 0:
                return jsonify({"error": "price must be >= 0"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "price must be an integer"}), 400
    if "duration_days" in data:
        try:
            d = int(data["duration_days"])
            if d < 1 or d > 365:
                return jsonify({"error": "duration_days must be 1..365"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "duration_days must be an integer"}), 400
    if "min_group_size" in data and "max_group_size" in data:
        try:
            if data["min_group_size"] not in (None, "") and data["max_group_size"] not in (None, ""):
                if int(data["min_group_size"]) > int(data["max_group_size"]):
                    return jsonify({"error": "min_group_size cannot exceed max_group_size"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "group sizes must be integers"}), 400
    for field in PACKAGE_FIELDS:
        if field in data:
            if field == "price_kind" and current_user.role != "admin" and data[field] == "demo_estimate":
                continue  # only seed/admin may mark demo estimates
            setattr(pkg, field, data[field])
    from datetime import datetime as _dt2
    if any(k in data for k in ("price", "price_breakdown")):
        pkg.price_confirmed_at = _dt2.utcnow()
        if not pkg.price_kind:
            pkg.price_kind = "operator_quote"
    db.session.commit()
    return jsonify({"package": pkg.to_dict()})


@packages_bp.post("/api/packages/<int:pkg_id>/delete")
@login_required
def api_delete(pkg_id: int):
    """Operator soft-delete (archive). Never hard-deletes rows.

    Sets is_deleted=True + is_active=False; all dependent records
    (interests, enquiries, bookings, offers, messages, reviews) stay.
    Deleted packages are excluded from discovery and new enquiries.
    Idempotent: repeat calls return ok + already_deleted.
    """
    from datetime import datetime as _dt_del

    pkg = TravelPackage.query.get_or_404(pkg_id)
    company = _require_operator_company()
    if company and pkg.operator_id != company.id and current_user.role != "admin":
        abort(403)
    if getattr(pkg, "is_deleted", False):
        return jsonify({"ok": True, "package_id": pkg.id, "already_deleted": True})
    pkg.is_deleted = True
    pkg.is_active = False
    pkg.deleted_at = _dt_del.utcnow()
    db.session.commit()
    return jsonify({"ok": True, "package_id": pkg.id, "deleted": True})


@packages_bp.post("/api/packages/<int:pkg_id>/swipe")
@login_required
def api_swipe(pkg_id: int):
    """Favourite (like) / hide (pass) — independent toggles.

    - like = heart favourite, persisted, does NOT create an enquiry/booking.
    - pass = hide, persisted, does NOT delete favourites or enquiries.
    - pass accepts optional rejection feedback: reason (allow-list key) +
      comment (free text, <=500 chars). Feedback is optional; omit to skip.
    Use POST /api/enquiries for genuine interest (creates enquiry).
    """
    from datetime import datetime as _dt

    from models.interaction import REJECTION_REASON_KEYS

    pkg = TravelPackage.query.get_or_404(pkg_id)
    if getattr(pkg, "is_deleted", False):
        return jsonify({"error": "package unavailable"}), 404
    data = request.get_json(force=True, silent=True) or {}
    action = (data.get("action") or "").lower()
    if action not in ("like", "pass"):
        return jsonify({"error": "action must be like|pass"}), 400
    reason = data.get("reason")
    if reason in (None, ""):
        reason = None
    if reason is not None:
        reason = str(reason).strip()
        if not reason:
            reason = None
        elif len(reason) > 50:
            return jsonify({"error": "reason too long (max 50)"}), 400
        elif reason not in REJECTION_REASON_KEYS and reason != "hidden":
            return jsonify({"error": "unknown reason", "valid_reasons": sorted(REJECTION_REASON_KEYS)}), 400
    comment = data.get("comment")
    if comment in (None, ""):
        comment = None
    if comment is not None:
        comment = str(comment).strip()[:2000]
        if not comment:
            comment = None
        elif len(str(data.get("comment") or "")) > 500:
            return jsonify({"error": "comment too long (max 500)"}), 400
    if action == "like" and (reason or comment):
        return jsonify({"error": "feedback is for pass only"}), 400
    existing = Interest.query.filter_by(
        traveler_id=current_user.id, package_id=pkg.id, action=action
    ).first()
    if not existing:
        # independent: never delete the other action (pass must not remove favourites)
        db.session.add(Interest(traveler_id=current_user.id, package_id=pkg.id, action=action, reason=reason,
                                comment=comment, feedback_at=_dt.utcnow() if (reason or comment) else None))
        # gentle adaptive note (no overreaction to single swipe)
        if current_user.preference and action == "pass" and reason:
            pref = current_user.preference
            lt = dict(pref.long_term or {})
            lt[f"avoid:{reason}"] = lt.get(f"avoid:{reason}", 0) + 1
            pref.long_term = lt
        db.session.commit()
    else:
        # Idempotent retry / attach feedback to an existing pass.
        if action == "pass" and (reason or comment) and not (existing.reason or existing.comment):
            existing.reason = reason or existing.reason
            existing.comment = comment or existing.comment
            existing.feedback_at = _dt.utcnow()
            db.session.commit()
        elif action == "pass" and (reason or comment):
            # Feedback already recorded — treat retry as success (no duplicate).
            pass
    return jsonify({"ok": True, "package_id": pkg.id, "action": action})


@packages_bp.post("/api/packages/<int:pkg_id>/like")
@login_required
def api_like(pkg_id: int):
    """Heart favourite: idempotent add, no enquiry created."""
    TravelPackage.query.get_or_404(pkg_id)
    existing = Interest.query.filter_by(
        traveler_id=current_user.id, package_id=pkg_id, action="like"
    ).first()
    if not existing:
        db.session.add(Interest(traveler_id=current_user.id, package_id=pkg_id, action="like"))
        db.session.commit()
    return jsonify({"ok": True, "package_id": pkg_id, "liked": True})


@packages_bp.delete("/api/packages/<int:pkg_id>/like")
@login_required
def api_unlike(pkg_id: int):
    TravelPackage.query.get_or_404(pkg_id)
    n = Interest.query.filter_by(
        traveler_id=current_user.id, package_id=pkg_id, action="like"
    ).delete()
    db.session.commit()
    return jsonify({"ok": True, "package_id": pkg_id, "liked": False, "removed": n})


@packages_bp.post("/api/packages/<int:pkg_id>/hide")
@login_required
def api_hide(pkg_id: int):
    """Hide from future recommendations (same as pass, explicit)."""
    TravelPackage.query.get_or_404(pkg_id)
    if not Interest.query.filter_by(
        traveler_id=current_user.id, package_id=pkg_id, action="pass"
    ).first():
        db.session.add(Interest(traveler_id=current_user.id, package_id=pkg_id, action="pass", reason="hidden"))
        db.session.commit()
    return jsonify({"ok": True, "package_id": pkg_id, "hidden": True})


@packages_bp.post("/api/packages/<int:pkg_id>/undo")
@login_required
def api_undo(pkg_id: int):
    """Undo previous swipe (removes like/pass, keeps save)."""
    TravelPackage.query.get_or_404(pkg_id)
    n = Interest.query.filter_by(traveler_id=current_user.id, package_id=pkg_id).filter(
        Interest.action.in_(["like", "pass"])
    ).delete()
    db.session.commit()
    return jsonify({"ok": True, "package_id": pkg_id, "removed": n})


@packages_bp.post("/api/packages/<int:pkg_id>/save")
@login_required
def api_save(pkg_id: int):
    TravelPackage.query.get_or_404(pkg_id)
    existing = Interest.query.filter_by(
        traveler_id=current_user.id, package_id=pkg_id, action="save"
    ).first()
    if not existing:
        db.session.add(Interest(traveler_id=current_user.id, package_id=pkg_id, action="save"))
        db.session.commit()
    return jsonify({"ok": True, "package_id": pkg_id})


@packages_bp.delete("/api/packages/<int:pkg_id>/save")
@login_required
def api_unsave(pkg_id: int):
    TravelPackage.query.get_or_404(pkg_id)
    n = Interest.query.filter_by(
        traveler_id=current_user.id, package_id=pkg_id, action="save"
    ).delete()
    db.session.commit()
    return jsonify({"ok": True, "package_id": pkg_id, "removed": n})


@packages_bp.get("/api/interests")
@login_required
def api_interests():
    action = (request.args.get("action") or "").strip().lower()
    q = Interest.query.filter_by(traveler_id=current_user.id)
    if action in ("like", "pass", "save"):
        q = q.filter_by(action=action)
    interests = q.order_by(Interest.created_at.desc()).all()
    return jsonify({"interests": [i.to_dict() for i in interests]})


@packages_bp.get("/api/interests/counts")
@login_required
def api_interest_counts():
    from sqlalchemy import func

    rows = (
        db.session.query(Interest.action, func.count(Interest.id))
        .filter_by(traveler_id=current_user.id)
        .group_by(Interest.action)
        .all()
    )
    counts = {"like": 0, "save": 0, "pass": 0}
    for action, n in rows:
        if action in counts:
            counts[action] = int(n)
    return jsonify(counts)

@packages_bp.post("/api/packages/<int:pkg_id>/status")
@login_required
def api_update_status(pkg_id: int):
    """Explicit lifecycle transition: draft, active, inactive, archived."""
    from datetime import datetime as _dt
    pkg = TravelPackage.query.get_or_404(pkg_id)
    company = _require_operator_company()
    if company and pkg.operator_id != company.id and current_user.role != "admin":
        abort(403)

    data = request.get_json(force=True, silent=True) or {}
    new_status = (data.get("status") or "").lower()
    valid_statuses = {"draft", "active", "inactive", "archived"}
    if new_status not in valid_statuses:
        return jsonify({"error": f"status must be one of {valid_statuses}"}), 400

    if new_status == "active":
        if not pkg.title or not pkg.destination or pkg.price < 0:
            return jsonify({"error": "Package must have valid title, destination and price to be active"}), 400
        now = _dt.utcnow()
        if (pkg.valid_until and pkg.valid_until < now) or (pkg.booking_deadline and pkg.booking_deadline < now):
            return jsonify({"error": "Cannot activate an expired package"}), 400
        pkg.status = "active"
        pkg.is_active = True
        pkg.is_deleted = False
    elif new_status == "archived":
        pkg.status = "archived"
        pkg.is_active = False
        pkg.is_deleted = True
        pkg.deleted_at = _dt.utcnow()
    else:  # draft or inactive
        pkg.status = new_status
        pkg.is_active = False

    db.session.commit()
    return jsonify({"ok": True, "package": pkg.to_dict()})
