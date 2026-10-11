"""VYBE matching engine — explainable, rule-based, testable.

Spec weights (configurable in MATCH_WEIGHTS, one place):
  budget fit: 25%
  destination / landscape: 25%
  activities / interests: 20%
  mood + travel pace: 15%
  accommodation / comfort: 10%
  group suitability: 5%

Hard constraints are enforced by filter_packages() (caller should filter
before ranking). Scoring never fabricates availability, ratings, reviews
or verification — availability_status comes from real seats_remaining only.

Missing preferences: neutral 0.5 (not 0, not 1.0) so incomplete profiles
do not get perfect matches nor zero. Documented per component below.

Backward compatible: accepts legacy keys (interests, preferred_regions,
scenery, preferred_climate, budget_max, duration_days, current_mood)
plus Phase-2 keys (travel_moods, travel_pace, destination_prefs,
activity_prefs, budget_per_person, accommodation_prefs, etc.).
"""

MATCH_WEIGHTS = {
    "budget": 0.25,
    "destination": 0.25,
    "activities": 0.20,
    "mood_pace": 0.15,
    "accommodation": 0.10,
    "group": 0.05,
}

DEFAULT_WEIGHTS = MATCH_WEIGHTS  # alias for legacy imports


def _as_list(v):
    if not v:
        return []
    if isinstance(v, (list, tuple, set)):
        return [str(x) for x in v if x]
    return [str(v)]


def _overlap(a, b) -> float:
    if not a or not b:
        return 0.0
    sa = {str(x).strip().lower() for x in a if str(x).strip()}
    sb = {str(x).strip().lower() for x in b if str(x).strip()}
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa | sb), 1)


def _substr_overlap(prefs_list, pkg_text_or_list) -> float:
    """Fallback for accommodation: substring match when tags differ in wording."""
    prefs = [str(x).lower() for x in (prefs_list or []) if str(x).strip()]
    if not prefs:
        return 0.0
    if isinstance(pkg_text_or_list, str):
        hay = pkg_text_or_list.lower()
        hits = sum(1 for p in prefs if p and p in hay)
        return hits / max(len(prefs), 1)
    return _overlap(prefs_list, pkg_text_or_list)


def _effective_budget(prefs: dict):
    for k in ("budget_per_person", "budget_max", "budget"):
        v = prefs.get(k)
        if isinstance(v, (int, float)) and v and v > 0:
            return int(v)
    return None


def _effective_moods(prefs: dict):
    moods = _as_list(prefs.get("travel_moods")) + _as_list(prefs.get("current_mood"))
    # de-dup preserving order, lowercase
    seen, out = set(), []
    for m in moods:
        ml = m.strip().lower()
        if ml and ml not in seen:
            seen.add(ml)
            out.append(ml)
    return out


def filter_packages(packages, prefs: dict):
    """Hard-constraint filtering. Returns (kept, excluded_with_reason).

    - is_active must be True
    - budget: exclude if price > budget*(1+flex/100); flex defaults 20%
    - capacity: exclude if num_travellers > max_group_size / capacity / seats_remaining
    - avoid: exclude if destination in avoid_destinations/avoid (exact, case-insensitive)
    - dates: only enforced when BOTH traveller date and package departure list exist
      and traveller is inflexible; otherwise kept (never fabricate availability).
    """
    kept, excluded = [], []
    budget = _effective_budget(prefs)
    flex = prefs.get("budget_flex_pct", 20)
    try:
        flex = int(flex) if flex is not None else 20
    except (TypeError, ValueError):
        flex = 20
    flex = max(0, min(flex, 200))
    num = prefs.get("num_travellers")
    try:
        num = int(num) if num else None
    except (TypeError, ValueError):
        num = None
    avoid = {str(x).strip().lower() for x in (
        _as_list(prefs.get("avoid_destinations")) + _as_list(prefs.get("avoid"))
    ) if str(x).strip()}
    travel_date = (prefs.get("travel_start_date") or "").strip() if isinstance(prefs.get("travel_start_date"), str) else None
    date_flex = prefs.get("date_flexible", True)
    if date_flex is None:
        date_flex = True

    for pkg in packages:
        if not getattr(pkg, "is_active", True):
            excluded.append((pkg, "hidden package"))
            continue
        if getattr(pkg, "is_deleted", False):
            excluded.append((pkg, "deleted package"))
            continue
        price = getattr(pkg, "price", 0) or 0
        if budget and price > budget * (1 + flex / 100.0):
            excluded.append((pkg, f"over budget (+{flex}% flex)"))
            continue
        if price < 0:
            excluded.append((pkg, "invalid price"))
            continue
        dest = str(getattr(pkg, "destination", "") or "").strip().lower()
        if dest and dest in avoid:
            excluded.append((pkg, "in your avoid list"))
            continue
        if num and num > 0:
            maxg = getattr(pkg, "max_group_size", None)
            cap = getattr(pkg, "capacity", None)
            seats = getattr(pkg, "seats_remaining", None)
            if isinstance(maxg, int) and maxg and num > maxg:
                excluded.append((pkg, "exceeds max group size"))
                continue
            if isinstance(cap, int) and cap and num > cap:
                excluded.append((pkg, "exceeds capacity"))
                continue
            if isinstance(seats, int) and seats is not None and num > seats:
                excluded.append((pkg, "not enough seats"))
                continue
        if travel_date and not date_flex:
            dep = getattr(pkg, "departure_dates_list", None) or []
            avail = getattr(pkg, "available_dates", "") or ""
            if dep and travel_date not in [str(d) for d in dep] and travel_date not in str(avail):
                excluded.append((pkg, "unavailable for your dates"))
                continue
        kept.append(pkg)
    return kept, excluded


def score_package(pkg, prefs: dict, weights: dict | None = None):
    """Return (score 0-100, reasons[<=3], explanation)."""
    w = {**MATCH_WEIGHTS, **(weights or {})}
    # legacy alias support
    if "interests" in (weights or {}) and "activities" not in (weights or {}):
        w["activities"] = weights["interests"]
    if "region_scenery" in (weights or {}) and "destination" not in (weights or {}):
        w["destination"] = weights["region_scenery"]
    if "duration" in (weights or {}) and "group" not in (weights or {}):
        pass  # duration folds into group component below
    if "climate" in (weights or {}) or "mood" in (weights or {}):
        pass
    reasons = []

    # 1) Budget 25%
    budget = _effective_budget(prefs)
    price = getattr(pkg, "price", 0) or 0
    if budget and budget > 0:
        if price <= 0:
            s_budget, budget_note = 0.5, None  # invalid price handled by filter; neutral here
        elif price <= budget:
            s_budget = 1.0
            budget_note = "Fits your budget"
        else:
            flex = prefs.get("budget_flex_pct", 20) or 20
            try:
                flex = max(0, int(flex))
            except (TypeError, ValueError):
                flex = 20
            over = (price - budget) / budget
            s_budget = max(0.0, 1.0 - over * (100.0 / max(flex, 1)) * 0.5 - over * 0.5)
            # linear-ish penalty: at flex limit score ~0.5, at 2x budget ~0
            s_budget = max(0.0, min(1.0, 1.0 - over))
            budget_note = None
            if s_budget >= 0.5:
                budget_note = "Slightly over budget but within flex"
        if budget_note and s_budget >= 0.7:
            reasons.append(budget_note)
        elif budget_note:
            reasons.append(budget_note)
    else:
        s_budget = 0.5  # missing budget -> neutral, NOT perfect

    # 2) Destination / landscape 25% (folds legacy regions+scenery+climate)
    pref_dest = (
        _as_list(prefs.get("destination_prefs"))
        + _as_list(prefs.get("preferred_regions"))
        + _as_list(prefs.get("scenery"))
        + _as_list(prefs.get("preferred_climate"))
        + _as_list(prefs.get("preferred_destinations"))
    )
    if prefs.get("destination_text"):
        pref_dest.append(str(prefs["destination_text"]))
    pkg_dest = (
        _as_list(getattr(pkg, "region_tags", None))
        + _as_list(getattr(pkg, "scenery_tags", None))
        + _as_list(getattr(pkg, "climate_tags", None))
    )
    if getattr(pkg, "destination", None):
        pkg_dest.append(str(pkg.destination))
    if pref_dest and pkg_dest:
        s_dest = _overlap(pref_dest, pkg_dest)
        if s_dest > 0:
            # find a concrete matching token for explanation
            inter = {a.lower() for a in pref_dest} & {b.lower() for b in pkg_dest}
            label = sorted(inter)[0] if inter else "your destination taste"
            reasons.append(f"Matches your {label} preference")
    else:
        s_dest = 0.5  # missing -> neutral

    # 3) Activities / interests 20%
    pref_act = _as_list(prefs.get("activity_prefs")) + _as_list(prefs.get("interests")) + _as_list(prefs.get("trip_desires"))
    pkg_act = _as_list(getattr(pkg, "activities", None)) + _as_list(getattr(pkg, "interest_tags", None))
    # legacy disliked filter: penalize packages heavy in disliked activities
    disliked = {str(x).lower() for x in _as_list(prefs.get("disliked_activities"))}
    if pref_act and pkg_act:
        s_act = _overlap(pref_act, pkg_act)
        if s_act > 0:
            inter = sorted({a.lower() for a in pref_act} & {b.lower() for b in pkg_act})[:3]
            reasons.append(f"Includes {', '.join(inter)} you enjoy")
        if disliked and ({str(x).lower() for x in pkg_act} & disliked):
            s_act = max(0.0, s_act - 0.3)
    else:
        s_act = 0.5

    # 4) Mood + pace 15%
    moods = _effective_moods(prefs)
    pkg_moods = [str(m).lower() for m in _as_list(getattr(pkg, "mood_tags", None))]
    pace = (prefs.get("travel_pace") or "").strip().lower() if isinstance(prefs.get("travel_pace"), str) else ""
    if moods and pkg_moods:
        s_mood = _overlap(moods, pkg_moods)
        if s_mood > 0:
            hit = sorted(set(moods) & set(pkg_moods))[0]
            reasons.append(f"Matches your {hit} mood")
    elif moods or pkg_moods:
        s_mood = 0.0 if (moods and pkg_moods) else 0.5
        if not moods:
            s_mood = 0.5
        else:
            s_mood = 0.0
    else:
        s_mood = 0.5
    # pace: packages carry no pace tags (no fabrication) -> neutral 0.5 when set
    if pace in ("slow", "balanced", "packed", "slow and relaxed", "activity-packed"):
        s_pace = 0.5
        # duration proximity as a transparent pace proxy
        wanted = prefs.get("duration_days")
        dur = getattr(pkg, "duration_days", None)
        if isinstance(wanted, int) and wanted > 0 and isinstance(dur, int):
            diff = abs(dur - wanted)
            s_pace = max(0.0, 1.0 - diff / max(wanted, 1))
            if diff == 0:
                reasons.append(f"Fits your {wanted}-day plan")
        s_mood_pace = 0.7 * s_mood + 0.3 * s_pace
    else:
        s_mood_pace = s_mood if (moods or pkg_moods) else 0.5

    # 5) Accommodation / comfort 10%
    acc_prefs = _as_list(prefs.get("accommodation_prefs"))
    style = (prefs.get("travel_style") or "").strip().lower() if isinstance(prefs.get("travel_style"), str) else ""
    if style:
        acc_prefs = acc_prefs + [style]
    pkg_acc_text = str(getattr(pkg, "accommodation", "") or "")
    pkg_styles = _as_list(getattr(pkg, "suitable_travel_styles", None))
    if acc_prefs and (pkg_acc_text or pkg_styles):
        s_acc = max(
            _substr_overlap(acc_prefs, pkg_acc_text) if pkg_acc_text else 0.0,
            _overlap(acc_prefs, pkg_styles) if pkg_styles else 0.0,
        )
        if s_acc > 0:
            reasons.append("Matches your comfort style")
    else:
        s_acc = 0.5

    # 6) Group suitability 5% (+ legacy duration fit)
    grp = (prefs.get("group_type") or "").strip().lower() if isinstance(prefs.get("group_type"), str) else ""
    suitable = [str(x).lower() for x in _as_list(getattr(pkg, "suitable_groups", None))]
    num = prefs.get("num_travellers")
    try:
        num = int(num) if num else None
    except (TypeError, ValueError):
        num = None
    parts = []
    if grp and suitable:
        parts.append(_overlap([grp], suitable))
    elif grp or suitable:
        parts.append(0.5 if not (grp and suitable) and (not grp or not suitable) else 0.0)
    else:
        parts.append(0.5)
    # capacity fit
    if num and num > 0:
        maxg = getattr(pkg, "max_group_size", None)
        ming = getattr(pkg, "min_group_size", None)
        if isinstance(maxg, int) and maxg and isinstance(ming, int) and ming:
            parts.append(1.0 if ming <= num <= maxg else 0.3)
        elif isinstance(maxg, int) and maxg:
            parts.append(1.0 if num <= maxg else 0.0)
        else:
            parts.append(0.7)
    # legacy duration fit folds here so old profiles still rank sensibly
    wanted = prefs.get("duration_days")
    dur = getattr(pkg, "duration_days", None)
    if isinstance(wanted, int) and wanted > 0 and isinstance(dur, int) and dur:
        diff = abs(dur - wanted)
        parts.append(max(0.0, 1.0 - diff / max(wanted, 1)))
    s_group = sum(parts) / max(len(parts), 1)
    if grp and suitable and _overlap([grp], suitable) > 0:
        reasons.append(f"Good for {grp} trips")

    total_w = max(sum(w["budget"] + w["destination"] + w["activities"] + w["mood_pace"] + w["accommodation"] + w["group"] for w in [w]), 1e-6)
    score = (
        s_budget * w["budget"]
        + s_dest * w["destination"]
        + s_act * w["activities"]
        + s_mood_pace * w["mood_pace"]
        + s_acc * w["accommodation"]
        + s_group * w["group"]
    ) / total_w * 100

    if not reasons:
        reasons = ["Popular trip worth exploring"]
    try:
        price_fmt = f"₹{int(price):,}"
    except (TypeError, ValueError):
        price_fmt = f"₹{price}"
    explanation = (
        f"Match {round(score)}: " + ", ".join(reasons[:3])
        + f" · {price_fmt} · {getattr(pkg, 'duration_days', '?')} days"
    )
    return round(float(score), 1), reasons[:3], explanation


def rank_packages(packages, prefs: dict, weights: dict | None = None, apply_filter=True):
    """Rank packages. Applies hard-constraint filter first (unless apply_filter=False)."""
    if apply_filter:
        packages, _ = filter_packages(packages, prefs or {})
    ranked = []
    for pkg in packages:
        score, reasons, explanation = score_package(pkg, prefs or {}, weights)
        ranked.append({"package": pkg, "score": score, "reasons": reasons, "explanation": explanation})
    ranked.sort(key=lambda r: (-r["score"], getattr(r["package"], "price", 0) or 0,
                               getattr(r["package"], "id", 0) or 0))
    return ranked


def apply_swipe_boost(ranked, liked_packages, boost_max=8.0):
    """Transparent rule-based re-rank using swipe history.

    Only applies when >=3 likes exist (sufficient feedback). Boosts packages
    sharing interest/mood/region tags with liked ones. Returns new ranked list
    with extra reason 'Picked for you based on your likes' when boosted.
    No ML model claimed.
    """
    return apply_match_intelligence(
        ranked,
        {"liked": liked_packages or [], "saved": [], "passed": [], "enquired": []},
        boost_max=boost_max,
    )


def _tag_set(packages, attrs=("interest_tags", "mood_tags", "region_tags", "scenery_tags")):
    tags = set()
    for p in packages or []:
        for attr in attrs:
            for t in getattr(p, attr, None) or []:
                tags.add(str(t).lower())
    return tags


def apply_match_intelligence(ranked, history=None, boost_max=8.0):
    """VYBE Match Intelligence v1 — deterministic, explainable, rule-based.

    history = {liked:[], saved:[], passed:[], enquired:[]} lists of packages.
    Signals (per-tag overlap, never whole-destination bans):
      enquiry +6.0 (strong interest) · save +4.0 · like +3.0 ·
      pass -4.0 damped (reduces similar ranking, never deletes a destination).
    Reasons cite the actual signal ("Similar to packages you saved").
    Not an AI model — transparent weighted rules; onboarding prefs stay primary.
    """
    history = history or {}
    liked = history.get("liked") or []
    saved = history.get("saved") or []
    passed = history.get("passed") or []
    enquired = history.get("enquired") or []
    if not (liked or saved or passed or enquired):
        return ranked
    sig_tags = {
        "enquired": (_tag_set(enquired), 6.0, "Similar to packages you enquired about"),
        "saved": (_tag_set(saved), 4.0, "Similar to packages you saved"),
        "liked": (_tag_set(liked), 3.0, "Similar to packages you liked"),
        "passed": (_tag_set(passed), -4.0, None),
    }
    # pass feedback counts only with >=2 passes (avoid overreacting to one swipe)
    if len(passed) < 2:
        sig_tags["passed"] = (set(), 0.0, None)
    out = []
    for r in ranked:
        pkg = r["package"]
        tags = _tag_set([pkg])
        delta = 0.0
        best = None
        for name, (sig, weight, reason) in sig_tags.items():
            if not sig:
                continue
            overlap = len(tags & sig) / max(len(tags | sig), 1)
            if overlap < 0.2:
                continue
            if name == "passed":
                delta += overlap * weight * 0.5  # damped: never bans a destination
            else:
                delta += overlap * weight
                if best is None or weight > best[0]:
                    best = (weight, reason)
        nr = dict(r)
        if abs(delta) > 0.05:
            nr["score"] = round(max(0.0, min(100.0, r["score"] + min(delta, boost_max))), 1)
            if best and delta > 0:
                rs = list(r["reasons"] or [])
                if best[1] not in rs:
                    rs.append(best[1])
                nr["reasons"] = rs[:3]
        out.append(nr)
    # deterministic tie-break: score desc, price asc, id asc
    out.sort(key=lambda r: (-r["score"], getattr(r["package"], "price", 0) or 0,
                            getattr(r["package"], "id", 0) or 0))
    return out


def _strongest_label(sig_tags, tags):
    best, best_w = None, 0
    for name, (sig, weight, _reason) in sig_tags.items():
        if weight <= 0 or not sig:
            continue
        overlap = len(tags & sig) / max(len(tags | sig), 1)
        if overlap >= 0.2 and weight > best_w:
            best, best_w = name, weight
    return best


def detect_contradictions(prefs: dict):
    """Return a clarification string when prefs conflict, else None."""
    budget = _effective_budget(prefs)
    style = str(prefs.get("travel_style") or "").lower()
    acc = [str(a).lower() for a in _as_list(prefs.get("accommodation_prefs"))]
    luxury = style in ("luxury", "premium") or any("luxury" in a or "resort" in a or "premium" in a for a in acc)
    if budget and budget <= 5000 and luxury:
        return (f"You selected a maximum budget of ₹{budget:,} with a premium/luxury stay. "
                "Would you prefer to increase your budget or keep the budget and explore homestays?")
    if budget and budget <= 3000 and luxury:
        return (f"You selected a maximum budget of ₹{budget:,} and a premium resort. "
                "Would you prefer to increase your budget or keep the budget and explore homestays?")
    return None


SOFT_FILTERS = ("region", "style", "accommodation", "operator", "min_score", "min_price", "min_duration", "q")


def closest_matches(all_packages, prefs: dict, strict_filters: dict, weights=None):
    """Demo fallback: relax ONLY soft filters, preserve hard constraints.

    Hard (preserved): is_active, max_price (budget ceiling), max_duration,
    avoid list, inflexible dates, capacity.
    Soft (relaxed): region/q/style/accommodation/operator/min_score/min_price/min_duration.
    Returns (ranked, relaxed_fields, note).
    """
    relaxed = []
    kept = list(all_packages)
    # apply hard constraints only
    def _num(v):
        try:
            return int(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None
    hard = {}
    for k in ("max_price", "max_duration"):
        hard[k] = _num(strict_filters.get(k))
    for k in ("region", "style", "accommodation", "operator", "min_score", "min_price", "min_duration", "q"):
        if strict_filters.get(k) not in (None, "", []):
            relaxed.append(k)
    if hard.get("max_price") is not None:
        kept = [p for p in kept if (p.price or 0) <= hard["max_price"]]
    if hard.get("max_duration") is not None:
        kept = [p for p in kept if (p.duration_days or 0) <= hard["max_duration"]]
    ranked = rank_packages(kept, prefs, weights, apply_filter=True)
    if relaxed:
        note = ("No exact matches — showing closest matches. Relaxed: "
                + ", ".join(relaxed) + ". Your selections were kept for editing.")
    else:
        note = "No exact matches — showing closest available packages."
    return ranked, relaxed, note
