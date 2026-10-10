"""Roamly companion logic ported to VYBE: trip provision + offline AI guide.

Reference: Roamly (Kotlin, offline-first deterministic assistant) —
same 9 answer branches + fallback, same packing defaults, same
non-destructive departure rule. Skinned in VYBE branding; no AI key needed.
"""

import json
import os

from models import (
    CompanionMessage, PackItem, Stop, StopActivity, TripDay, TripPlan, db,
)

DATA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "singapore.json")
_data = None


def _load():
    global _data
    if _data is None:
        with open(DATA_FILE, encoding="utf-8") as f:
            _data = json.load(f)
    return _data


def dataset():
    return _load()


def ensure_companion(user_id: int) -> TripPlan:
    """Lazily provision the demo Singapore trip + packing list for a user."""
    trip = TripPlan.query.filter_by(user_id=user_id).first()
    if trip is None:
        d = _load()["trip"]
        trip = TripPlan(
            user_id=user_id, title=d["title"], destination=d["destination"],
            country=d.get("country"), dates=d.get("dates"),
            duration_days=d.get("duration_days", 5),
            traveler_count=d.get("traveler_count", 1),
            status=d.get("status", "upcoming"), summary=d.get("summary"),
            meeting_point=d.get("meeting_point"),
            announcements=d.get("announcements", []),
        )
        db.session.add(trip)
        db.session.flush()
        for day in _load()["days"]:
            td = TripDay(trip_id=trip.id, day_number=day["day_number"],
                         title=day["title"], date=day.get("date"))
            db.session.add(td)
            db.session.flush()
            for s in day["stops"]:
                stop = Stop(
                    day_id=td.id, key=s.get("key"), name=s["name"],
                    category=s.get("category"), time_slot=s.get("time_slot"),
                    duration=s.get("duration"), short_desc=s.get("short"),
                    full_desc=s.get("full"), tips=s.get("tips", []),
                    precautions=s.get("precautions", []),
                )
                db.session.add(stop)
                db.session.flush()
                for a in s.get("activities", []):
                    db.session.add(StopActivity(
                        stop_id=stop.id, key=a.get("key"),
                        title=a["title"], done=bool(a.get("done", False)),
                    ))
    if not PackItem.query.filter_by(user_id=user_id).first():
        for p in _load()["packing"]:
            db.session.add(PackItem(
                user_id=user_id, key=p.get("key"), title=p["title"],
                category=p.get("category", "essentials"),
                packed=bool(p.get("packed", False)),
                belonging=bool(p.get("belonging", False)),
            ))
    db.session.commit()
    return trip


# ---- Offline AI guide (RoamlyAiCompanion port) ----

def answer(query: str, trip: TripPlan | None = None):
    """Return (text, chips) for a traveler question. Deterministic, offline."""
    q = (query or "").lower().strip()

    if "marina bay" in q or "near marina" in q:
        return ("""
**Exploring Near Marina Bay:**
Here is a curated itinerary around the Bay:

• **Gardens by the Bay & Cloud Forest:** Just a 7-minute stroll across the Lions Bridge from Marina Bay Sands. Walk inside the 35m misty waterfall mountain and the Flower Dome.
• **Helix Bridge:** Beautiful DNA-inspired pedestrian link leading directly toward the ArtScience Museum.
• **Lau Pa Sat & Satay Street:** 12 minutes walk into the Financial District. Open-air charcoal grilled satay skewers start at 7:00 PM nightly.
• **Merlion Park:** Direct view across the water basin — best visited at twilight when the evening breeze picks up.

*Practical Tip:* The free Garden Rhapsody light show at the Supertree Grove runs daily at 7:45 PM and 8:45 PM.
""".strip(),
            ["What are the precautions for Marina Bay?", "What can I do with three hours free?"])

    if "three hours" in q or "3 hours" in q or "free time" in q:
        return ("""
**Curated 3-Hour Singapore Experiences:**
Depending on where you are:

1. **River & Culture (Civic District):**
   • Start at National Gallery Singapore (1 hr).
   • Stroll through historic Anderson Bridge to Clarke Quay (30 mins).
   • Take a 40-minute Singapore River Bumboat cruise at sunset.

2. **Green Serenity (Botanic Gardens):**
   • Explore the National Orchid Garden VIP pavilions (1 hr).
   • Enjoy iced lemongrass tea at The Halia café (45 mins).
   • Relax around Swan Lake and the ancient heritage trees.

3. **Architectural Wonder (Jewel Changi):**
   • Walk the lush Shiseido Forest Valley.
   • Catch the 40m Rain Vortex cascade from Level 2.
   • Sample warm pandan chiffon cake and kaya toast.
""".strip(),
            ["What should I explore near Marina Bay?", "What should I pack for Singapore?"])

    if "history" in q or "historical" in q or "simple language" in q:
        return ("""
**The Story of Singapore in Simple Words:**

• **From Fishing Settlement to Lion City:** Originally called *Temasek* ('Sea Town'), legend says Prince Sang Nila Utama spotted what he thought was a lion and named the island *Singapura* ('Lion City').
• **Trading Port (1819):** Sir Stamford Raffles established Singapore as a free trade port due to its strategic position at the crossroads of the Malacca Strait.
• **Melting Pot of Cultures:** Chinese, Malay, Indian, and Eurasian merchants settled in distinct quarters — today's Chinatown, Kampong Glam, and Little India.
• **Modern Transformation:** Since independence in 1965 under Lee Kuan Yew, Singapore developed into a global green financial hub, consciously designing itself as a "City in Nature."
""".strip(),
            ["What should I explore near Marina Bay?", "What should I pack for Singapore?"])

    if "planned for today" in q or "today's plan" in q or "itinerary today" in q:
        day = (trip.days[0] if trip and trip.days else None)
        if day is not None:
            dests = "\n".join(
                f"• **{s.name}** ({s.time_slot}) — {s.short_desc}" for s in day.stops)
            done = sum(1 for s in day.stops if s.visited)
            text = f"**Today's Itinerary — Day {day.day_number}: {day.title}**\n\n{dests}\n\n*Status:* You have {done} of {len(day.stops)} destinations completed."
        else:
            text = "You currently have 5 days planned for Singapore, starting with Marina Bay Sands and Gardens by the Bay!"
        return (text,
                ["What precautions should I know?", "What should I pack for my trip?"])

    if "pack" in q or "what to bring" in q:
        return ("""
**Packing Advice for Singapore's Tropical Climate:**

• **Clothing:** Lightweight breathable linen or cotton. Daily temperatures hover between 28°C–32°C with high humidity.
• **Layering:** Malls, MRT trains, and attractions like Cloud Forest are heavily air-conditioned (~22°C); bring a light cardigan or wrap.
• **Rain Gear:** Short, heavy afternoon rain showers are common; carry a compact umbrella.
• **Footwear:** Cushioned walking sneakers — Singapore is exceptionally walkable.
• **Power & Plugs:** Type-G UK 3-pin plug (230V, 50Hz).
• **Etiquette:** Modest attire covering shoulders and knees for temple visits.
""".strip(),
            ["Check my packing list progress", "What are the rules and precautions?"])

    if "precaution" in q or "rule" in q or "law" in q or "fine" in q:
        return ("""
**Key Precautions & Local Guidelines in Singapore:**

• **MRT & Public Transit:** Eating, drinking (even plain water), and chewing gum are strictly prohibited inside train stations and cabins.
• **Temple Visits:** Remove footwear before entering Hindu and Buddhist shrines, and dress modestly (shoulders & knees covered).
• **Smoking:** Strictly restricted to designated yellow smoking boxes; prohibited in all public parks and indoor venues.
• **Tipping Culture:** Tipping is generally not expected as restaurants automatically add a 10% service charge and GST.
• **Littering:** Heavy fines apply for littering or jaywalking.
""".strip(),
            ["What should I pack for Singapore?", "What can I do with three hours free?"])

    if "reorganise" in q or "reorganize" in q or "change plan" in q or "rain" in q:
        return ("""
**Smart Itinerary Adjustment Suggestions:**

• If it rains in the afternoon: Swap outdoor walks (Supertree Grove / Haji Lane) for indoor marvels like **Cloud Forest & Flower Dome**, **National Gallery**, or **Jewel Changi**.
• If you finish early: Add a relaxing twilight stroll along **Marina Barrage** or visit **Clarke Quay** for dinner by the river.
• All destinations in your itinerary can be visited in any order. Tap any stop to mark it complete!
""".strip(),
            ["What activities are planned for today?", "What should I explore near Marina Bay?"])

    if "chinatown" in q or "food" in q or "hawker" in q:
        return ("""
**Food & Hawker Culture Guide:**

• **Lau Pa Sat:** Famous for evening Satay Street (Stalls 7 & 8) with peanut sauce and cucumber.
• **Chinatown Complex:** Home to iconic Liao Fan Hawker Chan chicken rice and traditional dessert stalls.
• **Maxwell Food Centre:** Try Tian Tian Hainanese Chicken Rice or Zhen Zhen Porridge.
• **Local Culture:** Look for packet tissues on tables ('Choping') — this is how locals reserve spots while ordering!
""".strip(),
            ["What should I explore near Marina Bay?", "What precautions should I know?"])

    return (f"""
I have noted your question regarding "{query.strip()}".

As your Singapore travel companion, I can help you with:
• Itinerary recommendations for Marina Bay, Chinatown, Sentosa, and Botanic Gardens.
• 3-hour free time schedules.
• Packing tips for Singapore's tropical climate.
• Local customs, temple dress codes, and transit etiquette.
• Reminders for essential belongings before you leave any stop.

Feel free to tap one of the suggested questions below!
""".strip(),
        ["What should I explore near Marina Bay?",
         "What can I do with three hours free?",
         "What should I pack for Singapore?",
         "What precautions should I know about this activity?"])


def ask_and_store(user_id: int, message: str):
    """Persist user message + AI reply (with chips). Returns the AI message dict."""
    from models import CompanionMessage  # local import, mirrors codebase style
    text_in = (message or "").strip()[:1000]
    if not text_in:
        return None
    db.session.add(CompanionMessage(user_id=user_id, sender="user", body=text_in))
    trip = TripPlan.query.filter_by(user_id=user_id).first()
    body, chips = answer(text_in, trip)
    ai = CompanionMessage(user_id=user_id, sender="ai", body=body, chips=chips)
    db.session.add(ai)
    db.session.commit()
    return ai.to_dict()
