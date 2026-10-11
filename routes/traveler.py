from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from models import Interest, TravelerProfile, TravelPackage, UserPreference, db
from models.booking import Booking, Enquiry
from services.recommendation import (
    apply_match_intelligence, apply_swipe_boost, closest_matches,
    detect_contradictions, rank_packages,
)
from services.vybe_ai import extract_preferences, onboarding_reply

traveler_bp = Blueprint("traveler", __name__)

PROFILE_SIMPLE_FIELDS = (
    "budget_max", "budget_per_person", "budget_flex_pct", "duration_days",
    "current_mood", "group_type", "travel_pace", "preferred_region_text",
    "start_city", "destination_text", "travel_start_date", "travel_end_date",
    "date_flexible", "num_travellers", "trip_mode", "travel_style",
    "group_size_pref", "itinerary_pref", "priority",
    "accessibility_notes", "dietary_notes", "other_notes", "ideal_trip_text",
    "onboarding_step", "onboarding_completed",
)

PROFILE_LIST_FIELDS = (
    "preferred_regions", "preferred_climate", "scenery", "interests", "avoid",
    "travel_moods", "trip_desires", "destination_prefs", "activity_prefs",
    "preferred_destinations", "avoid_destinations",
    "accommodation_prefs", "transport_prefs", "disliked_activities",
)

ALL_PROFILE_FIELDS = PROFILE_SIMPLE_FIELDS + PROFILE_LIST_FIELDS


def _get_or_create_profile():
    """Ensure the current user has a traveler profile (auto-create for travelers)."""
    p = current_user.profile
    if p is None:
        p = TravelerProfile(user_id=current_user.id)
        db.session.add(p)
        if not current_user.preference:
            db.session.add(UserPreference(user_id=current_user.id))
        db.session.commit()
    return p


def _prefs_dict():
    if current_user.is_authenticated and current_user.profile:
        return current_user.profile.to_dict()
    return {}


def _missing_required_prefs(profile) -> list:
    """Genuinely required fields for personalized recommendations."""
    d = profile.to_dict()
    missing = []
    if not (d.get("current_mood") or (d.get("travel_moods") or [])):
        missing.append("travel mood")
    if not (d.get("budget_per_person") or d.get("budget_max")):
        missing.append("budget per person")
    if not d.get("duration_days"):
        missing.append("trip duration")
    dest = (
        (d.get("preferred_destinations") or []) + (d.get("destination_prefs") or [])
        + (d.get("preferred_regions") or []) + ([d.get("destination_text")] if d.get("destination_text") else [])
    )
    if not [x for x in dest if x]:
        missing.append("destinations or regions")
    return missing


def _parse_list(form, *keys):
    """Collect multi-select values from checkboxes (getlist) or comma text."""
    vals = []
    for k in keys:
        vals.extend(form.getlist(k))
        single = (form.get(k) or "").strip() if isinstance(form.get(k), str) else ""
        # avoid double-count when getlist already captured; only split if single contains comma
        if single and "," in single and single not in vals:
            vals.extend([v.strip() for v in single.split(",") if v.strip()])
        elif single and len(keys) == 1 and not form.getlist(k):
            # single text field like preferred_destinations_text
            if "," in single:
                vals.extend([v.strip() for v in single.split(",") if v.strip()])
            elif single and single not in vals:
                vals.append(single)
    # de-dup preserving order
    seen, out = set(), []
    for v in vals:
        vl = str(v).strip()
        if vl and vl.lower() not in seen:
            seen.add(vl.lower())
            out.append(vl)
    return out


def _to_int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _to_bool(v, default=True):
    if v is None or v == "":
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on", "flexible"):
        return True
    if s in ("0", "false", "no", "off", "fixed"):
        return False
    return default


@traveler_bp.route("/onboarding", methods=["GET", "POST"])
@login_required
def onboarding():
    profile = _get_or_create_profile()
    if request.method == "POST":
        data = request.form or {}
        # legacy simple fields (backward compat)
        if data.get("budget_max"):
            profile.budget_max = _to_int(data.get("budget_max"), profile.budget_max or 15000)
        if data.get("duration_days"):
            profile.duration_days = _to_int(data.get("duration_days"), profile.duration_days or 3)
        legacy_regions = request.form.getlist("regions")
        if legacy_regions:
            profile.preferred_regions = legacy_regions
        legacy_climate = request.form.getlist("climate")
        if legacy_climate:
            profile.preferred_climate = legacy_climate
        legacy_interests = request.form.getlist("interests")
        if legacy_interests:
            profile.interests = legacy_interests
        if data.get("current_mood"):
            profile.current_mood = data.get("current_mood")
        if data.get("group_type"):
            profile.group_type = data.get("group_type")

        # Step 1: mood (11 options + pace + desires)
        moods = _parse_list(request.form, "travel_moods", "moods")
        if moods:
            profile.travel_moods = moods
            # keep current_mood synced for legacy scoring
            if not profile.current_mood:
                profile.current_mood = moods[0].lower()
        if data.get("travel_pace"):
            profile.travel_pace = data.get("travel_pace")
        desires = _parse_list(request.form, "trip_desires", "desires")
        if desires:
            profile.trip_desires = desires

        # Step 2: destinations + activities
        dest_prefs = _parse_list(request.form, "destination_prefs", "destinations")
        if dest_prefs:
            profile.destination_prefs = dest_prefs
        act_prefs = _parse_list(request.form, "activity_prefs", "activities_new")
        if act_prefs:
            profile.activity_prefs = act_prefs
        pref_dest = _parse_list(request.form, "preferred_destinations", "preferred_destinations_text")
        if pref_dest or "preferred_destinations" in data:
            profile.preferred_destinations = pref_dest
        avoid_dest = _parse_list(request.form, "avoid_destinations", "avoid_destinations_text")
        if avoid_dest or "avoid_destinations" in data:
            profile.avoid_destinations = avoid_dest
        if data.get("preferred_region_text"):
            profile.preferred_region_text = data.get("preferred_region_text").strip()

        # Step 3: budget + requirements
        if data.get("start_city"):
            profile.start_city = data.get("start_city").strip()
        if data.get("destination_text"):
            profile.destination_text = data.get("destination_text").strip()
        if data.get("budget_per_person"):
            profile.budget_per_person = _to_int(data.get("budget_per_person"), profile.budget_per_person)
            # sync legacy budget_max for old scoring/clients
            profile.budget_max = profile.budget_per_person
        if data.get("budget_flex_pct") not in (None, ""):
            profile.budget_flex_pct = max(0, min(200, _to_int(data.get("budget_flex_pct"), 20) or 0))
        if data.get("travel_start_date"):
            profile.travel_start_date = data.get("travel_start_date").strip()
        if data.get("travel_end_date"):
            profile.travel_end_date = data.get("travel_end_date").strip()
        if "date_flexible" in data or "date_type" in data:
            profile.date_flexible = _to_bool(data.get("date_flexible", data.get("date_type")), True)
        if data.get("num_travellers") or data.get("num_travelers"):
            profile.num_travellers = max(1, min(100, _to_int(data.get("num_travellers") or data.get("num_travelers"), 2) or 2))
        acc = _parse_list(request.form, "accommodation_prefs", "accommodation")
        if acc:
            profile.accommodation_prefs = acc
        trans = _parse_list(request.form, "transport_prefs", "transport")
        if trans:
            profile.transport_prefs = trans
        if data.get("trip_mode"):
            profile.trip_mode = data.get("trip_mode")

        # Step 4: style
        if data.get("travel_style"):
            profile.travel_style = data.get("travel_style")
        if data.get("group_size_pref"):
            profile.group_size_pref = data.get("group_size_pref")
        if data.get("itinerary_pref"):
            profile.itinerary_pref = data.get("itinerary_pref")
        if data.get("priority"):
            profile.priority = data.get("priority")
        disliked = _parse_list(request.form, "disliked_activities")
        if disliked or "disliked_activities" in data:
            profile.disliked_activities = disliked
        for f in ("accessibility_notes", "dietary_notes", "other_notes", "ideal_trip_text"):
            if data.get(f) is not None and data.get(f) != "":
                setattr(profile, f, data.get(f).strip())

        # free-text assistant box -> deterministic extraction
        free = data.get("free_text") or data.get("ideal_trip_text") or ""
        if free:
            merged = extract_preferences(free, profile.to_dict())
            profile.preferred_regions = merged.get("preferred_regions", profile.preferred_regions)
            profile.interests = merged.get("interests", profile.interests)
            profile.current_mood = merged.get("current_mood", profile.current_mood)
            if merged.get("budget_max"):
                profile.budget_max = merged["budget_max"]
                if not profile.budget_per_person:
                    profile.budget_per_person = merged["budget_max"]
            if merged.get("duration_days"):
                profile.duration_days = merged["duration_days"]

        # progress
        step = _to_int(data.get("onboarding_step"), profile.onboarding_step or 1) or 1
        profile.onboarding_step = max(1, min(5, step))
        wants_complete = bool(
            data.get("onboarding_completed") or data.get("complete") or step >= 5
        )
        error = None
        if wants_complete:
            missing = _missing_required_prefs(profile)
            if missing:
                # never mark complete on failed validation; let them retry
                error = "Almost there — please add: " + ", ".join(missing) + "."
            else:
                profile.onboarding_completed = True
                profile.onboarding_step = 5
        db.session.commit()
        if wants_complete and not error:
            flash("Preferences saved — here are trips picked for you.", "success")
            return redirect(url_for("traveler.discover"))
        return render_template(
            "onboarding.html",
            profile=profile,
            message=None if error else onboarding_reply(dict(data)),
            saved=not error,
            error=error,
        )
    return render_template("onboarding.html", profile=profile, message=None, saved=False)


@traveler_bp.get("/discover")
@login_required
def discover():
    # Travelers must complete preferences first; deck needs them for ranking.
    # Completeness of the saved record decides (not the flag), so API-saved
    # prefs count and cleared prefs correctly bounce back to onboarding.
    if current_user.role == "traveler":
        profile = _get_or_create_profile()
        missing = _missing_required_prefs(profile)
        if missing:
            flash(
                "Tell us your preferences first — your answers personalize the trips you see.",
                "error",
            )
            return redirect(url_for("traveler.onboarding"))
    return render_template("discover.html")


@traveler_bp.get("/dashboard")
@login_required
def dashboard():
    interests = (
        Interest.query.filter_by(traveler_id=current_user.id)
        .order_by(Interest.created_at.desc())
        .limit(100)
        .all()
    )
    enquiries = (
        Enquiry.query.filter_by(traveler_id=current_user.id)
        .order_by(Enquiry.updated_at.desc())
        .limit(100)
        .all()
    )
    bookings = (
        Booking.query.filter_by(traveler_id=current_user.id)
        .order_by(Booking.created_at.desc())
        .limit(100)
        .all()
    )
    from models.custom_offer import CustomOffer
    offers = (
        CustomOffer.query.filter_by(traveler_id=current_user.id)
        .order_by(CustomOffer.updated_at.desc())
        .limit(100)
        .all()
    )
    return render_template(
        "traveler_dashboard.html", interests=interests, enquiries=enquiries, bookings=bookings,
        offers=offers, profile=current_user.profile,
    )


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
    # Map UI temporarily hidden (implementation + map.html kept for restore;
    # coordinates stay in the API for other features). Redirect into flow.
    return redirect("/discover")


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
    p = _get_or_create_profile()
    for field in ALL_PROFILE_FIELDS:
        if field in data:
            setattr(p, field, data[field])
    # display name lives on User (no migration needed); validated, persistent
    if "name" in data:
        name = (data.get("name") or "").strip()
        if not name or len(name) > 120:
            return jsonify({"error": "name must be 1-120 characters"}), 400
        current_user.name = name
    # sync budget aliases
    if "budget_per_person" in data and data["budget_per_person"] and not data.get("budget_max"):
        p.budget_max = data["budget_per_person"]
    if "budget_max" in data and data["budget_max"] and not data.get("budget_per_person"):
        p.budget_per_person = data["budget_max"]
    db.session.commit()
    return jsonify({"profile": p.to_dict(), "user": current_user.to_dict()})


@traveler_bp.get("/profile")
@login_required
def profile_page():
    """Dedicated Profile page (distinct from /onboarding preferences flow)."""
    profile = _get_or_create_profile()
    return render_template("profile.html", profile=profile.to_dict())


@traveler_bp.post("/api/preferences")
@login_required
def api_preferences():
    data = request.get_json(force=True, silent=True) or {}
    p = _get_or_create_profile()
    # Accept either structured fields or free text
    if "free_text" in data and len(data) == 1:
        merged = extract_preferences(data["free_text"], p.to_dict())
        for k, v in merged.items():
            if hasattr(p, k):
                setattr(p, k, v)
    else:
        for field in ALL_PROFILE_FIELDS:
            if field in data:
                setattr(p, field, data[field])
        if "free_text" in data and data["free_text"]:
            merged = extract_preferences(data["free_text"], p.to_dict())
            for k in ("preferred_regions", "interests", "current_mood", "budget_max", "duration_days"):
                if merged.get(k) is not None and k not in data:
                    setattr(p, k, merged[k])
        if "budget_per_person" in data and data["budget_per_person"]:
            p.budget_max = data["budget_per_person"]
    db.session.commit()
    return jsonify({"profile": p.to_dict(), "message": onboarding_reply(data)})


@traveler_bp.get("/api/packages/recommended")
@login_required
def api_recommended():
    pkgs = TravelPackage.query.filter_by(is_active=True).all()
    pkgs = [p for p in pkgs if not getattr(p, "is_deleted", False)]
    # optional query filters (search + discovery filters, never breaking default)
    # Reuses matching service for ranking; filters only narrow the list.
    q = (request.args.get("q") or request.args.get("destination") or "").strip().lower()
    region = (request.args.get("region") or "").strip().lower()
    style = (request.args.get("style") or request.args.get("travel_style") or "").strip().lower()
    accom = (request.args.get("accommodation") or "").strip().lower()
    operator = (request.args.get("operator") or "").strip().lower()

    def _to_int(v):
        try:
            return int(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    min_price = _to_int(request.args.get("min_price"))
    max_price = _to_int(request.args.get("max_price"))
    min_duration = _to_int(request.args.get("min_duration"))
    max_duration = _to_int(request.args.get("max_duration"))
    min_score = None
    try:
        min_score = float(request.args.get("min_score")) if request.args.get("min_score") not in (None, "") else None
    except (TypeError, ValueError):
        min_score = None
    if q:
        pkgs = [p for p in pkgs if q in (p.title or "").lower() or q in (p.destination or "").lower()]
    if region:
        wants = [w.strip() for w in region.split(",") if w.strip()]
        def _matches(p):
            tags = [str(t).lower() for t in ((p.region_tags or []) + (p.scenery_tags or []))]
            dest = (p.destination or "").lower()
            return any(w in tags or w in dest for w in wants)
        pkgs = [p for p in pkgs if _matches(p)]
    if min_price is not None:
        pkgs = [p for p in pkgs if (p.price or 0) >= min_price]
    if max_price is not None:
        pkgs = [p for p in pkgs if (p.price or 0) <= max_price]
    if min_duration is not None:
        pkgs = [p for p in pkgs if (p.duration_days or 0) >= min_duration]
    if max_duration is not None:
        pkgs = [p for p in pkgs if (p.duration_days or 0) <= max_duration]
    if style:
        wants = [w.strip() for w in style.split(",") if w.strip()]
        pkgs = [p for p in pkgs if any(
            w in [str(t).lower() for t in (p.suitable_travel_styles or [])]
            or w in (p.accommodation or "").lower()
            or w in [str(t).lower() for t in ((p.interest_tags or []) + (p.mood_tags or []))]
            for w in wants)]
    if accom:
        pkgs = [p for p in pkgs if accom in (p.accommodation or "").lower()
                or accom in [str(t).lower() for t in (p.suitable_travel_styles or [])]]
    if operator:
        pkgs = [p for p in pkgs if p.operator and operator in (p.operator.company_name or "").lower()]
    prefs = _prefs_dict()
    weights = current_user.preference.weights if current_user.preference else None
    total_active = sum(1 for _ in TravelPackage.query.filter_by(is_active=True).all()
                       if not getattr(_, "is_deleted", False))
    if total_active == 0:
        return jsonify({"packages": [], "prefs": prefs,
                        "setup_notice": "No packages in the database yet (demo). Run: py seed.py --demo"})
    ranked = rank_packages(pkgs, prefs, weights)
    if min_score is not None:
        ranked = [r for r in ranked if r["score"] >= min_score]
    # VYBE Match Intelligence v1: likes + saves + enquiries up, passes damped down.
    # Onboarding prefs stay primary; history only re-ranks (never excludes).
    try:
        from models import TravelPackage as TP
        from models.booking import Enquiry as EnqM

        def _pkgs(ids):
            ids = list({i for i in ids if i})
            return TP.query.filter(TP.id.in_(ids)).all() if ids else []

        liked = _pkgs([i.package_id for i in Interest.query.filter_by(
            traveler_id=current_user.id, action="like").all()])
        saved = _pkgs([i.package_id for i in Interest.query.filter_by(
            traveler_id=current_user.id, action="save").all()])
        passed = _pkgs([i.package_id for i in Interest.query.filter_by(
            traveler_id=current_user.id, action="pass").all()])
        enq_ids = [e.package_id for e in EnqM.query.filter_by(traveler_id=current_user.id).all()]
        enquired = _pkgs(enq_ids)
        ranked = apply_match_intelligence(
            ranked, {"liked": liked, "saved": saved, "passed": passed, "enquired": enquired})
    except Exception:
        pass
    # exclude passed (hide) from deck; keep favourites/saves visible in panels
    # but exclude liked from deck to avoid repeats (revisit via header panel/prev)
    swiped_ids = {
        i.package_id for i in Interest.query.filter_by(traveler_id=current_user.id)
        .filter(Interest.action.in_(["like", "pass"])).all()
    }
    liked_ids = {
        i.package_id for i in Interest.query.filter_by(traveler_id=current_user.id, action="like").all()
    }
    saved_ids = {
        i.package_id for i in Interest.query.filter_by(traveler_id=current_user.id, action="save").all()
    }
    out = []
    for r in ranked:
        if r["package"].id in swiped_ids:
            continue
        d = r["package"].to_dict()
        d["match_score"] = r["score"]
        d["match_reasons"] = r["reasons"]
        d["match_explanation"] = r["explanation"]
        d["is_liked"] = r["package"].id in liked_ids
        d["is_saved"] = r["package"].id in saved_ids
        out.append(d)
    payload = {"packages": out, "prefs": prefs}
    # contradiction clarification (never silent guessing)
    contra = detect_contradictions(prefs)
    if contra:
        payload["clarification"] = contra
    # Refined swipe-deck queries (?deck=1 from Discover, or ?closest=1) always
    # return a usable deck: if exact filters leave the deck thin (<5), soft
    # preferences are relaxed automatically (hard budget ceiling kept) and the
    # top-up is honestly labelled. Bare API calls stay exact, and a truly
    # impossible query (e.g. budget below every price) returns an explained
    # empty deck. ?strict=1 always opts out.
    strict_mode = (request.args.get("strict") or "").lower() in ("1", "true", "yes")
    want_topup = not strict_mode and any(
        (request.args.get(k) or "").lower() in ("1", "true", "yes") for k in ("deck", "closest"))
    strict = {"region": region, "style": style, "accommodation": accom,
              "operator": operator, "min_score": request.args.get("min_score"),
              "min_price": request.args.get("min_price"),
              "min_duration": request.args.get("min_duration"), "q": q,
              "max_price": request.args.get("max_price"),
              "max_duration": request.args.get("max_duration")}

    def _relax():
        all_pkgs = [p for p in TravelPackage.query.filter_by(is_active=True).all()
                    if not getattr(p, "is_deleted", False)]
        return closest_matches(all_pkgs, prefs, strict, weights)

    def _explain_empty():
        payload["empty_reason"] = (
            "These filters are stricter than everything in the demo catalogue "
            "(even after relaxing soft preferences, the budget ceiling was kept). "
            "Try widening the budget or dates, or edit preferences.")
        payload["suggest_widen"] = True

    if want_topup and len(out) < 5:
        exact_n = len(out)
        seen = {d["id"] for d in out}
        relaxed_ranked, relaxed_fields, _note = _relax()
        target = 10 if exact_n == 0 else 5
        for r in relaxed_ranked:
            if len(out) >= target:
                break
            if r["package"].id in seen or r["package"].id in swiped_ids:
                continue
            seen.add(r["package"].id)
            out.append({**r["package"].to_dict(), "match_score": r["score"],
                        "match_reasons": r["reasons"], "match_explanation": r["explanation"],
                        "closest_match": True})
        payload["relaxed"] = relaxed_fields
        if not out:
            payload["note"] = ("No exact matches, and nothing fit even after relaxing soft "
                               "preferences (budget ceiling kept).")
            _explain_empty()
        elif exact_n == 0:
            payload["note"] = ("No exact matches for those filters — showing the "
                               "closest trips instead. Relaxed: "
                               + ", ".join(relaxed_fields) + ".")
        elif len(out) > exact_n:
            payload["note"] = (f"Only {exact_n} exact match(es) — topped up with closest "
                               "matches. Relaxed: " + ", ".join(relaxed_fields) + ".")
    elif not out:
        _explain_empty()
    return jsonify(payload)
