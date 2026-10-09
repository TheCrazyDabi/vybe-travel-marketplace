"""VYBE AI onboarding helper with deterministic fallback.

Works WITHOUT any API key. If VYBE_AI_API_URL/KEY are configured,
teams can plug a free-tier model later (Phase 4). Until then,
`extract_preferences` uses keyword rules so the demo never breaks.
"""

import re

REGION_KEYS = {
    "mountains": ["mountain", "hill", "trek", "himalaya", "munnar", "ooty", "coorg"],
    "beaches": ["beach", "goa", "sea", "island", "coast"],
    "forests": ["forest", "jungle", "wildlife", "wayanad", "safari"],
    "cities": ["city", "urban", "jaipur", "heritage", "monument", "palace"],
    "desert": ["desert", "jaisalmer"],
}
INTEREST_KEYS = {
    "adventure": ["adventure", "trek", "hike", "raft", "paraglid", "scuba", "bike"],
    "relaxation": ["relax", "spa", "chill", "leisure", "slow"],
    "nature": ["nature", "tea", "garden", "lake", "waterfall"],
    "culture": ["culture", "heritage", "temple", "fort", "museum", "food", "cuisine"],
    "wildlife": ["wildlife", "safari", "elephant", "tiger"],
    "nightlife": ["nightlife", "party", "club"],
}
MOOD_KEYS = ["adventure", "relaxation", "romantic", "family", "party", "spiritual", "nature"]


def extract_preferences(text: str, current: dict | None = None) -> dict:
    prefs = dict(current or {})
    t = (text or "").lower()

    regions = set(prefs.get("preferred_regions", []))
    for region, keys in REGION_KEYS.items():
        if any(k in t for k in keys):
            regions.add(region)
    if regions:
        prefs["preferred_regions"] = sorted(regions)

    interests = set(prefs.get("interests", []))
    for interest, keys in INTEREST_KEYS.items():
        if any(k in t for k in keys):
            interests.add(interest)
    if interests:
        prefs["interests"] = sorted(interests)

    m = re.search(r"(?:budget|under|upto|up to|max)\D*?(\d[\d,]*)\s*(k|thousand)?", t)
    if m:
        val = int(m.group(1).replace(",", ""))
        if m.group(2):
            val *= 1000
        prefs["budget_max"] = val
    m2 = re.search(r"(\d+)\s*(?:day|night)", t)
    if m2:
        prefs["duration_days"] = int(m2.group(1))

    for mood in MOOD_KEYS:
        if mood in t:
            prefs["current_mood"] = mood
            break

    if "cool" in t or "cold" in t:
        prefs["preferred_climate"] = ["cool"]
    elif "warm" in t or "hot" in t or "sunny" in t:
        prefs["preferred_climate"] = ["warm"]

    return prefs


def onboarding_reply(answers: dict) -> str:
    prefs = {}
    for v in answers.values():
        prefs = extract_preferences(str(v), prefs)
    bits = []
    if prefs.get("preferred_regions"):
        bits.append("/".join(prefs["preferred_regions"]))
    if prefs.get("current_mood"):
        bits.append(f"{prefs['current_mood']} mood")
    if prefs.get("budget_max"):
        bits.append(f"under ₹{prefs['budget_max']:,}")
    summary = ", ".join(bits) if bits else "flexible tastes"
    return f"Got it — I'll look for {summary} trips. Head to Discover to swipe your VYBE!"
