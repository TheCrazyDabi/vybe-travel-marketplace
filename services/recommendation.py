"""Deterministic recommendation scoring for VYBE (Phase 1/2 base).

Weights (defaults, configurable per user):
  interests 25%, region+scenery 20%, budget 20%,
  duration 15%, climate 10%, mood 10%.

Hard constraints (unavailable / impossible budget) are handled by the
caller filtering is_active packages; scoring never overrides them.
"""

DEFAULT_WEIGHTS = {
    "interests": 0.25,
    "region_scenery": 0.20,
    "budget": 0.20,
    "duration": 0.15,
    "climate": 0.10,
    "mood": 0.10,
}


def _overlap(a, b) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(x.lower() for x in a), set(x.lower() for x in b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa | sb), 1)


def score_package(pkg, prefs: dict, weights: dict | None = None):
    """Return (score 0-100, reasons list). prefs = TravelerProfile.to_dict()."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    reasons = []

    interests = prefs.get("interests") or []
    pkg_interests = (pkg.interest_tags or []) + (pkg.activities or [])
    s_interests = _overlap(interests, pkg_interests)
    if s_interests > 0:
        reasons.append(f"includes {', '.join(sorted(set(i.lower() for i in interests) & set(x.lower() for x in pkg_interests))[:3])}")

    regions = (prefs.get("preferred_regions") or []) + (prefs.get("scenery") or [])
    pkg_regions = (pkg.region_tags or []) + (pkg.scenery_tags or [])
    s_region = _overlap(regions, pkg_regions)
    if s_region > 0:
        reasons.append("matches your preferred scenery")

    budget = prefs.get("budget_max")
    if budget and budget > 0:
        if pkg.price <= budget:
            s_budget = 1.0
            reasons.append("within your budget")
        else:
            # linear penalty up to 2x budget
            over = (pkg.price - budget) / budget
            s_budget = max(0.0, 1.0 - over)
    else:
        s_budget = 0.5  # no budget set -> neutral

    wanted_days = prefs.get("duration_days")
    if wanted_days and wanted_days > 0:
        diff = abs(pkg.duration_days - wanted_days)
        s_duration = max(0.0, 1.0 - diff / max(wanted_days, 1))
        if diff == 0:
            reasons.append(f"fits your {wanted_days}-day plan")
    else:
        s_duration = 0.5

    s_climate = _overlap(prefs.get("preferred_climate") or [], pkg.climate_tags or [])
    if s_climate > 0:
        reasons.append("matches your climate preference")

    mood = (prefs.get("current_mood") or "").lower()
    pkg_moods = [m.lower() for m in (pkg.mood_tags or [])]
    s_mood = 1.0 if mood and mood in pkg_moods else 0.0
    if s_mood:
        reasons.append(f"great for '{prefs.get('current_mood')}' mood")

    score = (
        s_interests * w["interests"]
        + s_region * w["region_scenery"]
        + s_budget * w["budget"]
        + s_duration * w["duration"]
        + s_climate * w["climate"]
        + s_mood * w["mood"]
    ) / max(sum(w.values()), 1e-6) * 100

    if not reasons:
        reasons = ["popular trip worth exploring"]

    explanation = (
        f"Match {round(score)}: "
        + ", ".join(reasons[:3])
        + f" · ₹{pkg.price:,} · {pkg.duration_days} days"
    )
    return round(score, 1), reasons[:3], explanation


def rank_packages(packages, prefs: dict, weights: dict | None = None):
    ranked = []
    for pkg in packages:
        score, reasons, explanation = score_package(pkg, prefs, weights)
        ranked.append({"package": pkg, "score": score, "reasons": reasons, "explanation": explanation})
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked
