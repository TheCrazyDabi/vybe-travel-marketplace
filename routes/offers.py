"""Custom offers + verified-trip reviews (role-checked, persistent)."""

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from models import TravelCompany, TravelPackage, db
from models.booking import Booking
from models.custom_offer import OFFER_STATUSES, CustomOffer
from models.review import Review

offers_bp = Blueprint("offers", __name__)


def _company_for(user):
    return TravelCompany.query.filter_by(user_id=user.id).first()


@offers_bp.post("/api/custom-offers")
@login_required
def api_create_offer():
    data = request.get_json(force=True, silent=True) or {}
    pkg = TravelPackage.query.get(data.get("package_id"))
    if not pkg or not pkg.is_active or getattr(pkg, "is_deleted", False):
        return jsonify({"error": "package unavailable"}), 404
    try:
        num = int(data.get("num_travellers") or 2)
    except (TypeError, ValueError):
        return jsonify({"error": "num_travellers must be an integer"}), 400
    if num < 1 or num > 100:
        return jsonify({"error": "num_travellers must be 1..100"}), 400
    budget = data.get("desired_budget")
    if budget not in (None, ""):
        try:
            budget = int(budget)
            if budget < 0:
                return jsonify({"error": "desired_budget must be >= 0"}), 400
        except (TypeError, ValueError):
            return jsonify({"error": "desired_budget must be an integer"}), 400
    else:
        budget = None
    offer = CustomOffer(
        traveler_id=current_user.id, package_id=pkg.id, company_id=pkg.operator_id,
        status="pending", travel_dates=(data.get("travel_dates") or "").strip() or None,
        num_travellers=num, desired_budget=budget,
        accommodation_pref=(data.get("accommodation_pref") or "").strip() or None,
        itinerary_changes=(data.get("itinerary_changes") or "").strip() or None,
        transport_reqs=(data.get("transport_reqs") or "").strip() or None,
        notes=(data.get("notes") or "").strip() or None,
    )
    db.session.add(offer)
    db.session.commit()
    return jsonify({"offer": offer.to_dict()}), 201


@offers_bp.get("/api/custom-offers")
@login_required
def api_list_offers():
    if current_user.role == "admin":
        q = CustomOffer.query
    elif current_user.role == "operator":
        comp = _company_for(current_user)
        if not comp:
            return jsonify({"offers": []})
        q = CustomOffer.query.filter_by(company_id=comp.id)
    else:
        q = CustomOffer.query.filter_by(traveler_id=current_user.id)
    status = (request.args.get("status") or "").strip()
    if status and status in OFFER_STATUSES:
        q = q.filter_by(status=status)
    offers = q.order_by(CustomOffer.updated_at.desc()).limit(200).all()
    return jsonify({"offers": [o.to_dict() for o in offers]})


@offers_bp.post("/api/custom-offers/<int:offer_id>/respond")
@login_required
def api_operator_respond(offer_id: int):
    offer = CustomOffer.query.get_or_404(offer_id)
    comp = _company_for(current_user)
    if not ((comp and offer.company_id == comp.id) or current_user.role == "admin"):
        abort(403)
    if offer.status in ("accepted", "rejected", "expired"):
        return jsonify({"error": f"cannot revise from {offer.status}"}), 400
    data = request.get_json(force=True, silent=True) or {}
    try:
        revised = int(data.get("revised_price", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "revised_price must be an integer"}), 400
    if revised < 0:
        return jsonify({"error": "revised_price must be >= 0"}), 400
    child = CustomOffer(
        traveler_id=offer.traveler_id, package_id=offer.package_id,
        company_id=offer.company_id, enquiry_id=offer.enquiry_id,
        parent_id=offer.id, version=(offer.version or 1) + 1,
        status="offer_submitted",
        travel_dates=offer.travel_dates, num_travellers=offer.num_travellers,
        desired_budget=offer.desired_budget, accommodation_pref=offer.accommodation_pref,
        itinerary_changes=offer.itinerary_changes, transport_reqs=offer.transport_reqs,
        notes=offer.notes, revised_price=revised,
        revised_itinerary=(data.get("revised_itinerary") or "").strip() or None,
        inclusions=data.get("inclusions", []), exclusions=data.get("exclusions", []),
        additional_charges=data.get("additional_charges", []),
        valid_until=(data.get("valid_until") or "").strip() or None,
        operator_note=(data.get("operator_note") or "").strip() or None,
    )
    db.session.add(child)
    offer.status = "offer_submitted"
    db.session.commit()
    return jsonify({"offer": child.to_dict()}), 201


@offers_bp.post("/api/custom-offers/<int:offer_id>/reply")
@login_required
def api_traveler_reply(offer_id: int):
    offer = CustomOffer.query.get_or_404(offer_id)
    if not (offer.traveler_id == current_user.id or current_user.role == "admin"):
        abort(403)
    data = request.get_json(force=True, silent=True) or {}
    action = (data.get("action") or "").lower()
    if action == "accept":
        if offer.status not in ("offer_submitted", "pending"):
            return jsonify({"error": f"cannot accept from {offer.status}"}), 400
        offer.status = "accepted"
    elif action == "reject":
        offer.status = "rejected"
    elif action == "revise":
        if offer.status not in ("offer_submitted", "pending"):
            return jsonify({"error": f"cannot request revision from {offer.status}"}), 400
        offer.status = "revision_requested"
        if data.get("notes"):
            offer.notes = (offer.notes or "") + f"\n[Revision asked] {data['notes']}"
    else:
        return jsonify({"error": "action must be accept|reject|revise"}), 400
    db.session.commit()
    return jsonify({"offer": offer.to_dict()})


@offers_bp.post("/api/reviews")
@login_required
def api_create_review():
    data = request.get_json(force=True, silent=True) or {}
    booking = Booking.query.get(data.get("booking_id"))
    if not booking:
        return jsonify({"error": "booking required"}), 400
    if booking.traveler_id != current_user.id and current_user.role != "admin":
        abort(403)
    if booking.status != "confirmed":
        return jsonify({"error": "reviews require a confirmed (completed) booking"}), 400
    if booking.traveler_id != current_user.id:
        return jsonify({"error": "only the booking traveller can review"}), 403
    try:
        rating = int(data.get("rating", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "rating must be 1..5"}), 400
    if rating < 1 or rating > 5:
        return jsonify({"error": "rating must be 1..5"}), 400
    if Review.query.filter_by(booking_id=booking.id).first():
        return jsonify({"error": "one review per trip already exists"}), 400
    text = (data.get("text") or "").strip()[:2000]
    review = Review(booking_id=booking.id, traveler_id=booking.traveler_id,
                    package_id=booking.package_id, company_id=booking.company_id,
                    rating=rating, text=text or None, status="visible")
    db.session.add(review)
    db.session.commit()
    return jsonify({"review": review.to_dict()}), 201


@offers_bp.get("/api/packages/<int:pkg_id>/reviews")
def api_list_reviews(pkg_id: int):
    TravelPackage.query.get_or_404(pkg_id)
    reviews = Review.query.filter_by(package_id=pkg_id, status="visible").order_by(
        Review.created_at.desc()).limit(50).all()
    return jsonify({"reviews": [r.to_dict() for r in reviews]})
