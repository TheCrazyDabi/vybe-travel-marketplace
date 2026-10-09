from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from models import Interest, TravelPackage, db
from services.recommendation import score_package

packages_bp = Blueprint("packages", __name__)


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
    return render_template(
        "package_detail.html", pkg=pkg, score=score, reasons=reasons, explanation=explanation
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


@packages_bp.post("/api/packages")
@login_required
def api_create():
    company = _require_operator_company()
    data = request.get_json(force=True, silent=True) or {}
    if not data.get("title") or not data.get("destination") or data.get("price") is None:
        return jsonify({"error": "title, destination, price required"}), 400
    pkg = TravelPackage(
        operator_id=company.id if company else None,
        title=data["title"],
        destination=data["destination"],
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
    )
    # admin without company: attach to first approved company for demo
    if pkg.operator_id is None:
        from models import TravelCompany

        fallback = TravelCompany.query.filter_by(status="approved").first()
        if not fallback:
            return jsonify({"error": "no operator company available"}), 400
        pkg.operator_id = fallback.id
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
    for field in ("title", "destination", "cover_image", "short_desc", "itinerary",
                  "price", "currency", "duration_days", "group_size", "accommodation",
                  "transportation", "included", "excluded", "activities", "region_tags",
                  "climate_tags", "scenery_tags", "interest_tags", "mood_tags",
                  "lat", "lng", "is_active", "available_dates", "cancellation_terms"):
        if field in data:
            setattr(pkg, field, data[field])
    db.session.commit()
    return jsonify({"package": pkg.to_dict()})


@packages_bp.post("/api/packages/<int:pkg_id>/swipe")
@login_required
def api_swipe(pkg_id: int):
    pkg = TravelPackage.query.get_or_404(pkg_id)
    data = request.get_json(force=True, silent=True) or {}
    action = (data.get("action") or "").lower()
    if action not in ("like", "pass"):
        return jsonify({"error": "action must be like|pass"}), 400
    reason = data.get("reason")
    existing = Interest.query.filter_by(
        traveler_id=current_user.id, package_id=pkg.id, action=action
    ).first()
    if not existing:
        # remove opposite swipe so undo works naturally
        opposite = "pass" if action == "like" else "like"
        Interest.query.filter_by(
            traveler_id=current_user.id, package_id=pkg.id, action=opposite
        ).delete()
        db.session.add(Interest(traveler_id=current_user.id, package_id=pkg.id, action=action, reason=reason))
        # Phase 4 hook: gentle adaptive note (no overreaction to single swipe)
        if current_user.preference and action == "pass" and reason:
            pref = current_user.preference
            lt = dict(pref.long_term or {})
            lt[f"avoid:{reason}"] = lt.get(f"avoid:{reason}", 0) + 1
            pref.long_term = lt
        db.session.commit()
    return jsonify({"ok": True, "package_id": pkg.id, "action": action})


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


@packages_bp.get("/api/interests")
@login_required
def api_interests():
    interests = (
        Interest.query.filter_by(traveler_id=current_user.id)
        .order_by(Interest.created_at.desc())
        .all()
    )
    return jsonify({"interests": [i.to_dict() for i in interests]})
