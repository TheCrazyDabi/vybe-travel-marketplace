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
    "images", "departure_dates_list",
)


@packages_bp.get("/packages")
def list_page():
    pkgs = TravelPackage.query.filter_by(is_active=True).order_by(TravelPackage.price).all()
    return render_template("packages.html", packages=pkgs)


@packages_bp.get("/packages/<int:pkg_id>")
def detail_page(pkg_id: int):
    pkg = TravelPackage.query.get_or_404(pkg_id)
    score, reasons, explanation = None, [], ""
    if current_user.is_authenticated and current_user.profile:
        score, reasons, explanation = score_package(pkg, current_user.profile.to_dict())
    # traveller's enquiry for this package (if any)
    my_enquiry = None
    if current_user.is_authenticated:
        my_enquiry = Enquiry.query.filter_by(
            traveler_id=current_user.id, package_id=pkg.id
        ).order_by(Enquiry.updated_at.desc()).first()
    return render_template(
        "package_detail.html", pkg=pkg, score=score, reasons=reasons, explanation=explanation,
        my_enquiry=my_enquiry,
    )


# ---- JSON API ----
@packages_bp.get("/api/packages")
def api_list():
    pkgs = TravelPackage.query.filter_by(is_active=True).all()
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
    )
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
            setattr(pkg, field, data[field])
    db.session.commit()
    return jsonify({"package": pkg.to_dict()})


@packages_bp.post("/api/packages/<int:pkg_id>/swipe")
@login_required
def api_swipe(pkg_id: int):
    """Favourite (like) / hide (pass) — independent toggles.

    - like = heart favourite, persisted, does NOT create an enquiry/booking.
    - pass = hide, persisted, does NOT delete favourites or enquiries.
    Use POST /api/enquiries for genuine interest (creates enquiry).
    """
    pkg = TravelPackage.query.get_or_404(pkg_id)
    data = request.get_json(force=True, silent=True) or {}
    action = (data.get("action") or "").lower()
    if action not in ("like", "pass"):
        return jsonify({"error": "action must be like|pass"}), 400
    reason = data.get("reason")
    if reason is not None and len(str(reason)) > 50:
        return jsonify({"error": "reason too long (max 50)"}), 400
    existing = Interest.query.filter_by(
        traveler_id=current_user.id, package_id=pkg.id, action=action
    ).first()
    if not existing:
        # independent: never delete the other action (pass must not remove favourites)
        db.session.add(Interest(traveler_id=current_user.id, package_id=pkg.id, action=action, reason=reason))
        # gentle adaptive note (no overreaction to single swipe)
        if current_user.preference and action == "pass" and reason:
            pref = current_user.preference
            lt = dict(pref.long_term or {})
            lt[f"avoid:{reason}"] = lt.get(f"avoid:{reason}", 0) + 1
            pref.long_term = lt
        db.session.commit()
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
