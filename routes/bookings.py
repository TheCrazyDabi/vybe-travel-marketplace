"""Enquiry / Quotation / Booking workflow (persistent, role-checked)."""

from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from models import Conversation, Interest, Message, TravelCompany, TravelPackage, db
from models.booking import Booking, Enquiry, Quotation

bookings_bp = Blueprint("bookings", __name__)

ACTIVE_ENQUIRY = {"interested", "enquiry_sent", "awaiting_operator", "quote_received", "awaiting_traveller"}


def _company_for(user):
    return TravelCompany.query.filter_by(user_id=user.id).first()


def _can_view_enquiry(enq: Enquiry) -> bool:
    if not current_user.is_authenticated:
        return False
    if current_user.role == "admin":
        return True
    if enq.traveler_id == current_user.id:
        return True
    comp = _company_for(current_user)
    return comp is not None and enq.company_id == comp.id


def _ensure_conversation(enq: Enquiry):
    conv = Conversation.query.filter_by(
        traveler_id=enq.traveler_id, company_id=enq.company_id, package_id=enq.package_id
    ).first()
    if not conv:
        conv = Conversation(
            traveler_id=enq.traveler_id, company_id=enq.company_id,
            package_id=enq.package_id, status="New",
        )
        db.session.add(conv)
        db.session.flush()
    return conv


@bookings_bp.post("/api/enquiries")
@login_required
def api_create_enquiry():
    data = request.get_json(force=True, silent=True) or {}
    package_id = data.get("package_id")
    if not package_id:
        return jsonify({"error": "package_id required"}), 400
    pkg = db.session.get(TravelPackage, package_id)
    if not pkg or not pkg.is_active or getattr(pkg, "is_deleted", False):
        return jsonify({"error": "package unavailable"}), 404
    try:
        num = int(data.get("num_travellers") or 1)
    except (TypeError, ValueError):
        return jsonify({"error": "num_travellers must be a positive integer"}), 400
    if num < 1 or num > 100:
        return jsonify({"error": "num_travellers must be 1..100"}), 400
    # capacity hard check (real data only)
    if isinstance(pkg.max_group_size, int) and pkg.max_group_size and num > pkg.max_group_size:
        return jsonify({"error": f"exceeds max group size {pkg.max_group_size}"}), 400
    if isinstance(pkg.seats_remaining, int) and pkg.seats_remaining is not None and num > pkg.seats_remaining:
        return jsonify({"error": "not enough seats remaining"}), 400

    # reuse active enquiry for same traveler+package (prevent duplicates)
    existing = Enquiry.query.filter_by(traveler_id=current_user.id, package_id=pkg.id).filter(
        Enquiry.status.in_(list(ACTIVE_ENQUIRY))
    ).first()
    if existing:
        # update details, move to enquiry_sent/awaiting_operator
        existing.num_travellers = num
        existing.travel_date = (data.get("travel_date") or existing.travel_date or "").strip() or None
        existing.message = data.get("message") or existing.message
        if existing.status == "interested":
            existing.status = "enquiry_sent"
        db.session.commit()
        return jsonify({"enquiry": existing.to_dict(include_related=True)}), 200

    enq = Enquiry(
        traveler_id=current_user.id,
        package_id=pkg.id,
        company_id=pkg.operator_id,
        status="enquiry_sent",
        num_travellers=num,
        travel_date=(data.get("travel_date") or "").strip() or None,
        message=(data.get("message") or "").strip() or None,
        total_cost=(pkg.price or 0) * num if pkg.price else None,
    )
    db.session.add(enq)
    db.session.flush()
    # ensure swipe-like exists (right swipe = interested, no charge)
    if not Interest.query.filter_by(traveler_id=current_user.id, package_id=pkg.id, action="like").first():
        # remove pass if present (interest overrides pass)
        Interest.query.filter_by(traveler_id=current_user.id, package_id=pkg.id, action="pass").delete()
        db.session.add(Interest(traveler_id=current_user.id, package_id=pkg.id, action="like"))
    conv = _ensure_conversation(enq)
    if data.get("message"):
        db.session.add(Message(conversation_id=conv.id, sender_id=current_user.id, body=data["message"][:2000]))
        conv.status = "Contacted" if conv.status == "New" else conv.status
    db.session.commit()
    return jsonify({"enquiry": enq.to_dict(include_related=True), "conversation_id": conv.id}), 201


@bookings_bp.get("/api/enquiries")
@login_required
def api_list_enquiries():
    status = (request.args.get("status") or "").strip()
    if current_user.role == "admin":
        q = Enquiry.query
    elif current_user.role == "operator":
        comp = _company_for(current_user)
        if not comp:
            return jsonify({"enquiries": []})
        q = Enquiry.query.filter_by(company_id=comp.id)
    else:
        q = Enquiry.query.filter_by(traveler_id=current_user.id)
    if status:
        q = q.filter_by(status=status)
    enqs = q.order_by(Enquiry.updated_at.desc()).limit(200).all()
    return jsonify({"enquiries": [e.to_dict(include_related=True) for e in enqs]})


@bookings_bp.get("/api/enquiries/<int:enq_id>")
@login_required
def api_get_enquiry(enq_id: int):
    enq = Enquiry.query.get_or_404(enq_id)
    if not _can_view_enquiry(enq):
        abort(403)
    return jsonify({"enquiry": enq.to_dict(include_related=True)})


@bookings_bp.post("/api/enquiries/<int:enq_id>/quote")
@login_required
def api_quote(enq_id: int):
    enq = Enquiry.query.get_or_404(enq_id)
    comp = _company_for(current_user)
    is_owner = comp is not None and enq.company_id == comp.id
    if not (is_owner or current_user.role == "admin"):
        abort(403)
    if enq.status in ("confirmed", "rejected", "cancelled"):
        return jsonify({"error": f"cannot quote in status {enq.status}"}), 400
    data = request.get_json(force=True, silent=True) or {}
    try:
        ppp = int(data.get("price_per_person", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "price_per_person must be a non-negative integer"}), 400
    if ppp < 0:
        return jsonify({"error": "price_per_person must be >= 0"}), 400
    try:
        total = data.get("total_price")
        total = int(total) if total is not None and total != "" else ppp * (enq.num_travellers or 1)
    except (TypeError, ValueError):
        return jsonify({"error": "total_price must be an integer"}), 400
    if total < 0:
        return jsonify({"error": "total_price must be >= 0"}), 400
    # supersede old sent quotes
    for q in enq.quotations:
        if q.status == "sent":
            q.status = "superseded"
    quote = Quotation(
        enquiry_id=enq.id,
        operator_id=current_user.id,
        price_per_person=ppp,
        total_price=total,
        availability_note=(data.get("availability_note") or "").strip() or None,
        valid_until=(data.get("valid_until") or "").strip() or None,
        message=(data.get("message") or "").strip() or None,
        status="sent",
    )
    db.session.add(quote)
    enq.status = "quote_received"
    enq.total_cost = total
    conv = _ensure_conversation(enq)
    conv.status = "Quotation Sent"
    note = f"Quotation: ₹{ppp:,}/person, total ₹{total:,}. {quote.message or ''}".strip()
    db.session.add(Message(conversation_id=conv.id, sender_id=current_user.id, body=note[:2000]))
    db.session.commit()
    return jsonify({"quotation": quote.to_dict(), "enquiry": enq.to_dict(include_related=True)}), 201


@bookings_bp.post("/api/enquiries/<int:enq_id>/confirm")
@login_required
def api_confirm(enq_id: int):
    enq = Enquiry.query.get_or_404(enq_id)
    if not (enq.traveler_id == current_user.id or current_user.role == "admin"):
        abort(403)
    if enq.status not in ("quote_received", "awaiting_traveller", "awaiting_operator", "enquiry_sent"):
        return jsonify({"error": f"cannot confirm from status {enq.status}; need a quote first"}), 400
    data = request.get_json(force=True, silent=True) or {}
    details = data.get("traveller_details") or data.get("traveler_details") or {}
    if not isinstance(details, dict):
        return jsonify({"error": "traveller_details must be an object"}), 400
    # accept latest sent quote if present
    latest = None
    for q in sorted(enq.quotations, key=lambda x: x.id or 0, reverse=True):
        if q.status == "sent":
            latest = q
            break
    if latest:
        latest.status = "accepted"
        for q in enq.quotations:
            if q is not latest and q.status == "sent":
                q.status = "superseded"
        total = latest.total_price
    else:
        # allow confirm without quote only if operator-less demo? require quote for safety
        # but permit when enquiry has total_cost from package
        total = enq.total_cost
    if enq.booking:
        return jsonify({"error": "booking already exists", "booking": enq.booking.to_dict()}), 400
    pkg = db.session.get(TravelPackage, enq.package_id)
    booking = Booking(
        enquiry_id=enq.id,
        traveler_id=enq.traveler_id,
        package_id=enq.package_id,
        company_id=enq.company_id,
        status="confirmed",
        traveller_details=details,
        total_cost=total,
        itinerary_snapshot=pkg.itinerary if pkg else None,
        terms=pkg.cancellation_terms if pkg else None,
        payment_status="simulated_pending",
        confirmed_at=datetime.utcnow(),
    )
    db.session.add(booking)
    enq.status = "confirmed"
    # decrement seats when real inventory exists (never below 0)
    if pkg and isinstance(pkg.seats_remaining, int) and pkg.seats_remaining is not None:
        pkg.seats_remaining = max(0, pkg.seats_remaining - (enq.num_travellers or 1))
    db.session.commit()
    return jsonify({"booking": booking.to_dict(), "enquiry": enq.to_dict(include_related=True)}), 201


@bookings_bp.post("/api/enquiries/<int:enq_id>/decline")
@login_required
def api_decline(enq_id: int):
    enq = Enquiry.query.get_or_404(enq_id)
    if not (enq.traveler_id == current_user.id or current_user.role == "admin"):
        abort(403)
    data = request.get_json(force=True, silent=True) or {}
    for q in enq.quotations:
        if q.status == "sent":
            q.status = "declined"
    # back to awaiting_operator so operator can re-quote; or rejected if requested
    if (data.get("final") or False):
        enq.status = "rejected"
    else:
        enq.status = "awaiting_operator" if enq.status in ("quote_received", "awaiting_traveller") else enq.status
    db.session.commit()
    return jsonify({"enquiry": enq.to_dict(include_related=True)})


@bookings_bp.post("/api/enquiries/<int:enq_id>/reject")
@login_required
def api_reject(enq_id: int):
    enq = Enquiry.query.get_or_404(enq_id)
    comp = _company_for(current_user)
    if not ((comp and enq.company_id == comp.id) or current_user.role == "admin"):
        abort(403)
    if enq.status in ("confirmed", "rejected", "cancelled"):
        return jsonify({"error": f"cannot reject from {enq.status}"}), 400
    enq.status = "rejected"
    db.session.commit()
    return jsonify({"enquiry": enq.to_dict(include_related=True)})


@bookings_bp.post("/api/enquiries/<int:enq_id>/cancel")
@login_required
def api_cancel_enquiry(enq_id: int):
    enq = Enquiry.query.get_or_404(enq_id)
    if not (enq.traveler_id == current_user.id or current_user.role == "admin"):
        abort(403)
    if enq.status in ("confirmed",):
        return jsonify({"error": "confirmed enquiries cancel via booking cancel"}), 400
    if enq.status in ("rejected", "cancelled"):
        return jsonify({"error": f"already {enq.status}"}), 400
    enq.status = "cancelled"
    db.session.commit()
    return jsonify({"enquiry": enq.to_dict(include_related=True)})


@bookings_bp.get("/api/bookings")
@login_required
def api_list_bookings():
    if current_user.role == "admin":
        q = Booking.query
    elif current_user.role == "operator":
        comp = _company_for(current_user)
        if not comp:
            return jsonify({"bookings": []})
        q = Booking.query.filter_by(company_id=comp.id)
    else:
        q = Booking.query.filter_by(traveler_id=current_user.id)
    bookings = q.order_by(Booking.created_at.desc()).limit(200).all()
    return jsonify({"bookings": [b.to_dict() for b in bookings]})


@bookings_bp.get("/api/bookings/<int:booking_id>")
@login_required
def api_get_booking(booking_id: int):
    b = Booking.query.get_or_404(booking_id)
    if current_user.role != "admin" and b.traveler_id != current_user.id:
        comp = _company_for(current_user)
        if not (comp and b.company_id == comp.id):
            abort(403)
    return jsonify({"booking": b.to_dict()})


@bookings_bp.post("/api/bookings/<int:booking_id>/cancel")
@login_required
def api_cancel_booking(booking_id: int):
    b = Booking.query.get_or_404(booking_id)
    if current_user.role != "admin" and b.traveler_id != current_user.id:
        comp = _company_for(current_user)
        if not (comp and b.company_id == comp.id):
            abort(403)
    if b.status == "cancelled":
        return jsonify({"error": "already cancelled"}), 400
    b.status = "cancelled"
    if b.enquiry and b.enquiry.status == "confirmed":
        # keep enquiry confirmed history; booking cancelled separately
        pass
    db.session.commit()
    return jsonify({"booking": b.to_dict()})
