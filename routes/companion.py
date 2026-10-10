"""Roamly companion: My Trips itinerary, packing checklist, AI guide chat."""

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from models import CompanionMessage, PackItem, Stop, StopActivity, db
from services.sg_companion import answer, ask_and_store, dataset, ensure_companion

companion_bp = Blueprint("companion", __name__)

VALID_CATEGORIES = {"documents", "essentials", "clothing", "electronics", "health", "activities"}


def _user_stop(stop_id: int) -> Stop:
    from models import TripDay, TripPlan
    stop = (
        Stop.query.join(TripDay, Stop.day_id == TripDay.id)
        .join(TripPlan, TripDay.trip_id == TripPlan.id)
        .filter(Stop.id == stop_id, TripPlan.user_id == current_user.id)
        .first()
    )
    if stop is None:
        abort(404)
    return stop


@companion_bp.get("/trips")
@login_required
def trips_page():
    trip = ensure_companion(current_user.id)
    try:
        day_n = int(request.args.get("day", 1))
    except (TypeError, ValueError):
        day_n = 1
    days = trip.days
    day = next((d for d in days if d.day_number == day_n), days[0] if days else None)
    return render_template("trips.html", trip=trip, days=days, day=day,
                           departure_items=dataset()["departure_items"])


@companion_bp.get("/api/trips/current")
@login_required
def api_trip():
    return jsonify({"trip": ensure_companion(current_user.id).to_dict(include_days=True)})


@companion_bp.post("/api/trips/stops/<int:stop_id>/visit")
@login_required
def api_visit(stop_id: int):
    data = request.get_json(force=True, silent=True) or {}
    stop = _user_stop(stop_id)
    stop.visited = bool(data.get("visited", True))
    db.session.commit()
    return jsonify({"stop": stop.to_dict()})


@companion_bp.post("/api/trips/activities/<int:act_id>/toggle")
@login_required
def api_activity(act_id: int):
    from models import TripDay, TripPlan
    act = (
        StopActivity.query.join(Stop, StopActivity.stop_id == Stop.id)
        .join(TripDay, Stop.day_id == TripDay.id)
        .join(TripPlan, TripDay.trip_id == TripPlan.id)
        .filter(StopActivity.id == act_id, TripPlan.user_id == current_user.id)
        .first()
    )
    if act is None:
        abort(404)
    act.done = not act.done
    db.session.commit()
    return jsonify({"activity": act.to_dict()})


@companion_bp.post("/api/trips/stops/<int:stop_id>/departure")
@login_required
def api_departure(stop_id: int):
    """Non-destructive departure check: ack + mark visited, never clears anything."""
    stop = _user_stop(stop_id)
    stop.departure_ack = True
    stop.visited = True
    db.session.commit()
    return jsonify({"stop": stop.to_dict()})


@companion_bp.get("/packing")
@login_required
def packing_page():
    ensure_companion(current_user.id)
    items = PackItem.query.filter_by(user_id=current_user.id).order_by(PackItem.id).all()
    d = dataset()
    total = len(items)
    packed = sum(1 for i in items if i.packed)
    return render_template(
        "packing.html", items=items, total=total, packed=packed,
        pct=int(100 * packed / total) if total else 0,
        guides=d["document_guides"], emergency=d["emergency"],
        departure_items=d["departure_items"],
    )


@companion_bp.get("/api/packing")
@login_required
def api_packing():
    ensure_companion(current_user.id)
    items = PackItem.query.filter_by(user_id=current_user.id).order_by(PackItem.id).all()
    d = dataset()
    total = len(items)
    packed = sum(1 for i in items if i.packed)
    return jsonify({
        "items": [i.to_dict() for i in items],
        "total": total, "packed": packed,
        "pct": int(100 * packed / total) if total else 0,
        "guides": d["document_guides"], "emergency": d["emergency"],
        "departure_items": d["departure_items"],
    })


@companion_bp.post("/api/packing")
@login_required
def api_pack_add():
    data = request.get_json(force=True, silent=True) or {}
    title = (data.get("title") or "").strip()[:255]
    category = (data.get("category") or "essentials").lower()
    if not title:
        return jsonify({"error": "title required"}), 400
    if category not in VALID_CATEGORIES:
        return jsonify({"error": "unknown category"}), 400
    ensure_companion(current_user.id)  # packing implies a provisioned checklist
    item = PackItem(user_id=current_user.id, title=title, category=category, custom=True)
    db.session.add(item)
    db.session.commit()
    return jsonify({"item": item.to_dict()}), 201


@companion_bp.delete("/api/packing/<int:item_id>")
@login_required
def api_pack_delete(item_id: int):
    item = PackItem.query.filter_by(id=item_id, user_id=current_user.id).first()
    if item is None:
        abort(404)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"ok": True})


@companion_bp.post("/api/packing/<int:item_id>/toggle")
@login_required
def api_pack_toggle(item_id: int):
    item = PackItem.query.filter_by(id=item_id, user_id=current_user.id).first()
    if item is None:
        abort(404)
    item.packed = not item.packed
    db.session.commit()
    return jsonify({"item": item.to_dict()})


STARTER_CHIPS = [
    "What should I explore near Marina Bay?",
    "What can I do with three hours free?",
    "What should I pack for Singapore?",
    "What precautions should I know?",
]


@companion_bp.get("/companion")
@login_required
def companion_page():
    ensure_companion(current_user.id)
    history = (
        CompanionMessage.query.filter_by(user_id=current_user.id)
        .order_by(CompanionMessage.id.desc()).limit(50).all()[::-1]
    )
    return render_template("companion.html", history=history, chips=STARTER_CHIPS)


@companion_bp.get("/api/companion/messages")
@login_required
def api_messages():
    msgs = (
        CompanionMessage.query.filter_by(user_id=current_user.id)
        .order_by(CompanionMessage.id.desc()).limit(50).all()[::-1]
    )
    return jsonify({"messages": [m.to_dict() for m in msgs]})


@companion_bp.post("/api/companion/ask")
@login_required
def api_ask():
    data = request.get_json(force=True, silent=True) or {}
    ensure_companion(current_user.id)
    ai = ask_and_store(current_user.id, data.get("message", ""))
    if ai is None:
        return jsonify({"error": "message required"}), 400
    return jsonify({"message": ai, "chips": ai["chips"]}), 201
