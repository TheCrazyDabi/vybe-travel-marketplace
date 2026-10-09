from flask import Blueprint, jsonify, render_template, request
from flask_login import current_user, login_required

from models import Interest, TravelPackage, db
from services.recommendation import rank_packages
from services.vybe_ai import extract_preferences, onboarding_reply

traveler_bp = Blueprint("traveler", __name__)


def _prefs_dict():
    if current_user.is_authenticated and current_user.profile:
        return current_user.profile.to_dict()
    return {}


@traveler_bp.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    profile = current_user.profile
    if request.method == "POST":
        data = request.form or {}
        profile.budget_max = int(data.get("budget_max") or profile.budget_max or 15000)
        profile.duration_days = int(data.get("duration_days") or profile.duration_days or 3)
        profile.preferred_regions = request.form.getlist("regions") or profile.preferred_regions
        profile.preferred_climate = request.form.getlist("climate") or profile.preferred_climate
        profile.interests = request.form.getlist("interests") or profile.interests
        profile.current_mood = data.get("current_mood") or profile.current_mood
        profile.group_type = data.get("group_type") or profile.group_type
        # free-text assistant box -> deterministic extraction
        free = data.get("free_text") or ""
        if free:
            merged = extract_preferences(free, profile.to_dict())
            profile.preferred_regions = merged.get("preferred_regions", profile.preferred_regions)
            profile.interests = merged.get("interests", profile.interests)
            profile.current_mood = merged.get("current_mood", profile.current_mood)
            if merged.get("budget_max"):
                profile.budget_max = merged["budget_max"]
            if merged.get("duration_days"):
                profile.duration_days = merged["duration_days"]
        db.session.commit()
        return render_template(
            "onboarding.html",
            profile=profile,
            message=onboarding_reply(dict(data)),
            saved=True,
        )
    return render_template("onboarding.html", profile=profile, message=None, saved=False)


@traveler_bp.get("/discover")
@login_required
def discover():
    return render_template("discover.html")


@traveler_bp.get("/saved")
@login_required
def saved():
    interests = (
        Interest.query.filter_by(traveler_id=current_user.id)
        .order_by(Interest.created_at.desc())
        .all()
    )
    return render_template("saved.html", interests=interests)


@traveler_bp.get("/map")
@login_required
def map_view():
    pkgs = TravelPackage.query.filter_by(is_active=True).all()
    return render_template("map.html", packages=pkgs)


# ---- JSON API ----
@traveler_bp.get("/api/profile")
@login_required
def api_get_profile():
    return jsonify(
        {"user": current_user.to_dict(), "profile": current_user.profile.to_dict() if current_user.profile else {}}
    )


@traveler_bp.put("/api/profile")
@login_required
def api_put_profile():
    data = request.get_json(force=True, silent=True) or {}
    p = current_user.profile
    for field in ("budget_max", "duration_days", "preferred_regions", "preferred_climate",
                  "scenery", "interests", "group_type", "current_mood", "avoid"):
        if field in data:
            setattr(p, field, data[field])
    db.session.commit()
    return jsonify({"profile": p.to_dict()})


@traveler_bp.post("/api/preferences")
@login_required
def api_preferences():
    data = request.get_json(force=True, silent=True) or {}
    p = current_user.profile
    # Accept either structured fields or free text
    if "free_text" in data:
        merged = extract_preferences(data["free_text"], p.to_dict())
        for k, v in merged.items():
            if hasattr(p, k):
                setattr(p, k, v)
    else:
        for field in ("budget_max", "duration_days", "preferred_regions", "preferred_climate",
                      "scenery", "interests", "group_type", "current_mood", "avoid"):
            if field in data:
                setattr(p, field, data[field])
    db.session.commit()
    return jsonify({"profile": p.to_dict(), "message": onboarding_reply(data)})


@traveler_bp.get("/api/packages/recommended")
@login_required
def api_recommended():
    pkgs = TravelPackage.query.filter_by(is_active=True).all()
    prefs = _prefs_dict()
    weights = current_user.preference.weights if current_user.preference else None
    ranked = rank_packages(pkgs, prefs, weights)
    # exclude already swiped (like/pass) but keep saves visible
    swiped_ids = {
        i.package_id for i in Interest.query.filter_by(traveler_id=current_user.id)
        .filter(Interest.action.in_(["like", "pass"])).all()
    }
    out = []
    for r in ranked:
        if r["package"].id in swiped_ids:
            continue
        d = r["package"].to_dict()
        d["match_score"] = r["score"]
        d["match_reasons"] = r["reasons"]
        d["match_explanation"] = r["explanation"]
        out.append(d)
    return jsonify({"packages": out, "prefs": prefs})
