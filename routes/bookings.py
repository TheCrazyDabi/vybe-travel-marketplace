"""Enquiry / Quotation / Booking workflow (persistent, role-checked)."""

from datetime import datetime
import uuid

import logging
from flask import Blueprint, abort, current_app, jsonify, request
from flask_login import current_user, login_required

from models import Conversation, Interest, Message, TravelCompany, TravelPackage, User, db
from models.booking import Booking, Enquiry, Quotation
from services.package_lifecycle import is_booking_allowed
from services.payment import payment_service
from services.push import push_service

logger = logging.getLogger(__name__)

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
    if hasattr(pkg, "check_and_update_expiry"):
        pkg.check_and_update_expiry()
    try:
        num = int(data.get("num_travellers") or 1)
    except (TypeError, ValueError):
        return jsonify({"error": "num_travellers must be a positive integer"}), 400
    if num < 1 or num > 100:
        return jsonify({"error": "num_travellers must be 1..100"}), 400

    allowed, reason = is_booking_allowed(pkg, num)
    if not allowed:
        return jsonify({"error": reason}), 400
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
    try:
        push_service.send_notification(
            user_id=enq.traveler_id,
            title="New Quotation Received",
            body=f"Quotation received: ₹{total:,} for your trip enquiry.",
            notif_type="quote_received",
            data={"enquiry_id": enq.id, "package_id": enq.package_id},
        )
    except Exception:
        pass
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



@bookings_bp.post("/api/bookings/request")
@login_required
def api_request_booking():
    """Traveller submits a booking request for an active, valid package."""
    data = request.get_json(force=True, silent=True) or {}

    # 1. Idempotency Check
    idempotency_key = (
        request.headers.get("X-Idempotency-Key")
        or data.get("idempotency_key")
    )
    if idempotency_key:
        existing = Booking.query.filter_by(idempotency_key=str(idempotency_key).strip()).first()
        if existing:
            if existing.traveler_id == current_user.id or current_user.role == "admin":
                return jsonify({"booking": existing.to_dict(), "idempotent_replay": True}), 200
            abort(403)

    package_id = data.get("package_id")
    if not package_id:
        return jsonify({"error": "package_id is required"}), 400

    try:
        num_travellers = int(data.get("num_travellers") or 1)
    except (TypeError, ValueError):
        return jsonify({"error": "num_travellers must be a positive integer"}), 400

    if num_travellers < 1 or num_travellers > 100:
        return jsonify({"error": "num_travellers must be between 1 and 100"}), 400

    # 2. Concurrency-safe atomic package lookup & locking
    try:
        pkg = TravelPackage.query.with_for_update().filter_by(id=package_id).first()
    except Exception:
        pkg = db.session.get(TravelPackage, package_id)

    if not pkg or getattr(pkg, "is_deleted", False):
        return jsonify({"error": "Package not found or no longer available"}), 404

    # 3. Expiry and bookable validation
    if hasattr(pkg, "check_and_update_expiry"):
        pkg.check_and_update_expiry()

    allowed, reason = is_booking_allowed(pkg, num_travellers)
    if not allowed:
        return jsonify({"error": reason}), 400

    if not pkg.is_active or (hasattr(pkg, "is_bookable") and not pkg.is_bookable):
        if isinstance(pkg.seats_remaining, int) and pkg.seats_remaining <= 0:
            return jsonify({
                "error": "Not enough seats remaining. Only 0 available.",
                "seats_remaining": 0
            }), 400
        return jsonify({"error": "Package has expired or is unavailable for booking"}), 400

    # 4. Operator status check (block if suspended or inactive)
    operator_company = TravelCompany.query.get(pkg.operator_id)
    if not operator_company:
        return jsonify({"error": "Operator profile not found"}), 400
    operator_user = User.query.get(operator_company.user_id)
    if not operator_user or operator_user.status != "active":
        return jsonify({"error": "Operator account is suspended or inactive"}), 400

    # 5. Capacity Check
    if isinstance(pkg.seats_remaining, int) and pkg.seats_remaining is not None:
        if num_travellers > pkg.seats_remaining:
            return jsonify({
                "error": f"Not enough seats remaining. Only {pkg.seats_remaining} available.",
                "seats_remaining": pkg.seats_remaining
            }), 400
    if isinstance(pkg.max_group_size, int) and pkg.max_group_size and num_travellers > pkg.max_group_size:
        return jsonify({"error": f"Exceeds max group size of {pkg.max_group_size}"}), 400

    # 6. Immutable Snapshots
    price_per_person = int(pkg.price or 0)
    total_cost = price_per_person * num_travellers
    price_breakdown = {
        "price_per_person": price_per_person,
        "num_travellers": num_travellers,
        "subtotal": total_cost,
        "currency": "INR",
        "captured_at": datetime.utcnow().isoformat(),
    }
    terms_snapshot = getattr(pkg, "cancellation_terms", None) or getattr(pkg, "terms", None) or f"Standard terms for {pkg.title}. Non-refundable within 48h of trip."
    itinerary_snapshot = str(getattr(pkg, "itinerary", "") or "")

    booking_ref = f"VY-{uuid.uuid4().hex[:8].upper()}"
    traveller_details = data.get("traveller_details") or {}
    if not isinstance(traveller_details, dict):
        traveller_details = {"raw": traveller_details}
    if "lead_name" not in traveller_details and hasattr(current_user, "name"):
        traveller_details["lead_name"] = current_user.name
    if "lead_email" not in traveller_details and hasattr(current_user, "email"):
        traveller_details["lead_email"] = current_user.email

    booking = Booking(
        booking_reference=booking_ref,
        idempotency_key=str(idempotency_key).strip() if idempotency_key else f"auto_{uuid.uuid4().hex}",
        traveler_id=current_user.id,
        package_id=pkg.id,
        company_id=operator_company.id,
        num_travellers=num_travellers,
        status="requested",
        agreed_price_snapshot=total_cost,
        price_breakdown_snapshot=price_breakdown,
        terms_snapshot=terms_snapshot,
        terms=terms_snapshot,
        itinerary_snapshot=itinerary_snapshot,
        capacity_reserved=False,
        traveller_details=traveller_details,
        total_cost=total_cost,
        payment_status="unpaid",
        created_at=datetime.utcnow(),
    )
    db.session.add(booking)
    db.session.commit()

    # 7. Audit log & Notification
    try:
        from models.audit import AuditEvent
        AuditEvent.log(
            event_type="booking_requested",
            user_id=current_user.id,
            details={"booking_id": booking.id, "booking_ref": booking_ref, "package_id": pkg.id, "total_cost": total_cost},
        )
    except Exception:
        pass

    try:
        push_service.send_notification(
            user_id=operator_user.id,
            title="New Booking Request",
            body=f"Traveller {getattr(current_user, 'name', 'Guest')} requested {num_travellers} seat(s) for '{pkg.title}'.",
            notif_type="booking_requested",
            data={"booking_id": booking.id, "booking_reference": booking_ref},
        )
    except Exception:
        pass

    return jsonify({"booking": booking.to_dict()}), 201


@bookings_bp.post("/api/bookings/<int:booking_id>/accept")
@login_required
def api_accept_booking(booking_id: int):
    """Operator accepts a requested booking and atomically reserves capacity."""
    booking = Booking.query.get_or_404(booking_id)
    comp = _company_for(current_user)
    if current_user.role != "admin" and not (comp and booking.company_id == comp.id):
        abort(403)

    if booking.status != "requested":
        return jsonify({"error": f"Cannot accept booking in '{booking.status}' status (must be 'requested')"}), 400

    # Atomic lock on package to verify & reserve capacity
    try:
        pkg = TravelPackage.query.with_for_update().filter_by(id=booking.package_id).first()
    except Exception:
        pkg = db.session.get(TravelPackage, booking.package_id)

    num = booking.num_travellers or 1
    if pkg and isinstance(pkg.seats_remaining, int) and pkg.seats_remaining is not None:
        if pkg.seats_remaining < num:
            return jsonify({
                "error": "Insufficient capacity to accept this booking request",
                "seats_remaining": pkg.seats_remaining
            }), 400
        pkg.seats_remaining = max(0, pkg.seats_remaining - num)

    booking.capacity_reserved = True
    booking.status = "accepted"
    booking.accepted_at = datetime.utcnow()
    db.session.commit()

    try:
        from models.audit import AuditEvent
        AuditEvent.log(
            event_type="booking_accepted",
            user_id=current_user.id,
            details={"booking_id": booking.id, "package_id": booking.package_id},
        )
    except Exception:
        pass

    try:
        push_service.send_notification(
            user_id=booking.traveler_id,
            title="Booking Request Accepted!",
            body=f"Your booking request #{booking.booking_reference or booking.id} has been accepted by the operator.",
            notif_type="booking_accepted",
            data={"booking_id": booking.id},
        )
    except Exception:
        pass

    return jsonify({"booking": booking.to_dict()}), 200


@bookings_bp.post("/api/bookings/<int:booking_id>/reject")
@login_required
def api_reject_booking(booking_id: int):
    """Operator rejects a booking request and releases any reserved capacity."""
    booking = Booking.query.get_or_404(booking_id)
    comp = _company_for(current_user)
    if current_user.role != "admin" and not (comp and booking.company_id == comp.id):
        abort(403)

    if booking.status in ("rejected", "cancelled", "completed"):
        return jsonify({"error": f"Cannot reject booking in '{booking.status}' status"}), 400

    data = request.get_json(force=True, silent=True) or {}
    reason = (data.get("reason") or "Declined by operator").strip()

    # Release capacity if it had been reserved
    if booking.capacity_reserved and booking.package_id:
        try:
            pkg = TravelPackage.query.with_for_update().filter_by(id=booking.package_id).first()
        except Exception:
            pkg = db.session.get(TravelPackage, booking.package_id)
        if pkg and isinstance(pkg.seats_remaining, int) and pkg.seats_remaining is not None:
            pkg.seats_remaining += (booking.num_travellers or 1)
        booking.capacity_reserved = False

    booking.status = "rejected"
    booking.cancellation_reason = reason
    db.session.commit()

    try:
        push_service.send_notification(
            user_id=booking.traveler_id,
            title="Booking Request Declined",
            body=f"Your booking request #{booking.booking_reference or booking.id} could not be accepted. Reason: {reason}",
            notif_type="booking_rejected",
            data={"booking_id": booking.id},
        )
    except Exception:
        pass

    return jsonify({"booking": booking.to_dict()}), 200


@bookings_bp.post("/api/bookings/<int:booking_id>/confirm")
@login_required
def api_confirm_booking(booking_id: int):
    """Traveller or Admin confirms an accepted booking request."""
    booking = Booking.query.get_or_404(booking_id)
    if current_user.role != "admin" and booking.traveler_id != current_user.id:
        abort(403)

    if booking.status not in ("accepted", "requested"):
        return jsonify({"error": f"Cannot confirm booking in '{booking.status}' status"}), 400

    if not booking.capacity_reserved and booking.package_id:
        try:
            pkg = TravelPackage.query.with_for_update().filter_by(id=booking.package_id).first()
        except Exception:
            pkg = db.session.get(TravelPackage, booking.package_id)
        num = booking.num_travellers or 1
        if pkg and isinstance(pkg.seats_remaining, int) and pkg.seats_remaining is not None:
            if pkg.seats_remaining < num:
                return jsonify({"error": "Insufficient capacity"}), 400
            pkg.seats_remaining = max(0, pkg.seats_remaining - num)
        booking.capacity_reserved = True

    booking.status = "confirmed"
    booking.confirmed_at = datetime.utcnow()
    db.session.commit()

    try:
        push_service.send_notification(
            user_id=booking.traveler_id,
            title="Booking Confirmed!",
            body=f"Booking #{booking.booking_reference or booking.id} is confirmed.",
            notif_type="booking_confirmed",
            data={"booking_id": booking.id},
        )
        if booking.company and booking.company.user_id:
            push_service.send_notification(
                user_id=booking.company.user_id,
                title="Booking Confirmed",
                body=f"Booking #{booking.booking_reference or booking.id} was confirmed by traveller.",
                notif_type="booking_confirmed",
                data={"booking_id": booking.id},
            )
    except Exception:
        pass

    return jsonify({"booking": booking.to_dict()}), 200


@bookings_bp.post("/api/bookings/<int:booking_id>/cancel")
@login_required
def api_cancel_booking(booking_id: int):
    """Cancel booking with capacity release and notification."""
    b = Booking.query.get_or_404(booking_id)
    comp = _company_for(current_user)
    is_owner = (b.traveler_id == current_user.id)
    is_operator = bool(comp and b.company_id == comp.id)
    is_admin = (current_user.role == "admin")

    if not (is_owner or is_operator or is_admin):
        abort(403)

    if b.status in ("cancelled", "completed"):
        return jsonify({"error": "already cancelled"}), 400

    data = request.get_json(force=True, silent=True) or {}
    reason = (data.get("reason") or "Cancelled by user").strip()

    # Capacity restoration if capacity was reserved
    if b.capacity_reserved and b.package_id:
        try:
            pkg = TravelPackage.query.with_for_update().filter_by(id=b.package_id).first()
        except Exception:
            pkg = db.session.get(TravelPackage, b.package_id)
        if pkg and isinstance(pkg.seats_remaining, int) and pkg.seats_remaining is not None:
            pkg.seats_remaining += (b.num_travellers or 1)
        b.capacity_reserved = False

    b.status = "cancelled"
    b.cancelled_by = current_user.id
    b.cancelled_at = datetime.utcnow()
    b.cancellation_reason = reason
    db.session.commit()

    try:
        if is_owner and b.company and b.company.user_id:
            push_service.send_notification(
                user_id=b.company.user_id,
                title="Booking Cancelled",
                body=f"Booking #{b.booking_reference or b.id} was cancelled by traveller.",
                notif_type="booking_cancelled",
                data={"booking_id": b.id},
            )
        elif (is_operator or is_admin) and b.traveler_id:
            push_service.send_notification(
                user_id=b.traveler_id,
                title="Booking Cancelled",
                body=f"Booking #{b.booking_reference or b.id} was cancelled. Reason: {reason}",
                notif_type="booking_cancelled",
                data={"booking_id": b.id},
            )
    except Exception:
        pass

    return jsonify({"booking": b.to_dict()})


@bookings_bp.post("/api/bookings/<int:booking_id>/pay")
@login_required
def api_create_booking_payment(booking_id: int):
    booking = Booking.query.get_or_404(booking_id)
    if current_user.role != "admin" and booking.traveler_id != current_user.id:
        abort(403)
    if booking.status == "cancelled":
        return jsonify({"error": "Cannot pay for cancelled booking"}), 400
    if booking.payment_status == "paid":
        return jsonify({"error": "Booking is already paid", "booking": booking.to_dict()}), 400

    amount = booking.total_cost or 0
    if amount <= 0:
        return jsonify({"error": "Invalid booking total amount"}), 400

    try:
        order = payment_service.create_order(
            amount_inr=amount,
            receipt=f"bkg_{booking.id}",
            notes={"booking_id": booking.id, "package_id": booking.package_id},
        )
        booking.razorpay_order_id = order["id"]
        booking.payment_status = "order_created"
        db.session.commit()

        key_id = current_app.config.get("RAZORPAY_KEY_ID") or "rzp_test_simulated"
        return jsonify({
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order.get("currency", "INR"),
            "key_id": key_id,
            "booking_id": booking.id,
            "simulated": order.get("simulated", False),
        })
    except Exception as e:
        return jsonify({"error": f"Failed to initialize payment: {e}"}), 500


@bookings_bp.post("/api/bookings/<int:booking_id>/verify-payment")
@login_required
def api_verify_booking_payment(booking_id: int):
    booking = Booking.query.get_or_404(booking_id)
    if current_user.role != "admin" and booking.traveler_id != current_user.id:
        abort(403)
    if booking.status == "cancelled":
        return jsonify({"error": "Cannot verify payment for cancelled booking"}), 400

    data = request.get_json(force=True, silent=True) or {}
    order_id = data.get("razorpay_order_id") or booking.razorpay_order_id
    payment_id = data.get("razorpay_payment_id")
    signature = data.get("razorpay_signature")
    method = data.get("payment_method") or "razorpay"

    if not order_id or not payment_id or not signature:
        return jsonify({"error": "razorpay_order_id, razorpay_payment_id, and razorpay_signature are required"}), 400

    if booking.razorpay_order_id and booking.razorpay_order_id != order_id:
        return jsonify({"error": "Order ID mismatch"}), 400

    is_valid = payment_service.verify_payment_signature(
        razorpay_order_id=order_id,
        razorpay_payment_id=payment_id,
        razorpay_signature=signature,
    )
    if not is_valid:
        return jsonify({"error": "Payment signature verification failed"}), 400

    booking.razorpay_order_id = order_id
    booking.razorpay_payment_id = payment_id
    booking.razorpay_signature = signature
    booking.payment_status = "paid"
    booking.amount_paid = booking.total_cost
    booking.payment_method = method
    booking.status = "confirmed"
    booking.confirmed_at = datetime.utcnow()
    db.session.commit()
    try:
        push_service.send_notification(
            user_id=booking.traveler_id,
            title="Booking Confirmed!",
            body=f"Your payment of ₹{(booking.amount_paid or 0):,} was successful.",
            notif_type="booking_confirmed",
            data={"booking_id": booking.id},
        )
        if booking.company and booking.company.user_id:
            push_service.send_notification(
                user_id=booking.company.user_id,
                title="Booking Paid & Confirmed",
                body=f"Booking #{booking.id} was paid: ₹{(booking.amount_paid or 0):,}.",
                notif_type="booking_paid",
                data={"booking_id": booking.id},
            )
    except Exception:
        pass

    return jsonify({"ok": True, "booking": booking.to_dict()})


@bookings_bp.post("/api/payments/razorpay/webhook")
def api_razorpay_webhook():
    signature = request.headers.get("X-Razorpay-Signature", "")
    body_bytes = request.get_data()

    if not signature:
        return jsonify({"error": "Missing X-Razorpay-Signature header"}), 400

    if not payment_service.verify_webhook_signature(body_bytes, signature):
        return jsonify({"error": "Invalid webhook signature"}), 400

    data = request.get_json(force=True, silent=True) or {}
    event = data.get("event")
    logger.info("Received Razorpay webhook event: %s", event)

    if event in ("order.paid", "payment.captured"):
        payload = data.get("payload", {})
        order_id = None
        payment_id = None
        amount_paid = None
        method = None

        if "payment" in payload and "entity" in payload["payment"]:
            entity = payload["payment"]["entity"]
            order_id = entity.get("order_id")
            payment_id = entity.get("id")
            amount_paid = entity.get("amount", 0) // 100
            method = entity.get("method")
        elif "order" in payload and "entity" in payload["order"]:
            entity = payload["order"]["entity"]
            order_id = entity.get("id")
            amount_paid = entity.get("amount_paid", 0) // 100

        if order_id:
            booking = Booking.query.filter_by(razorpay_order_id=order_id).first()
            if booking:
                # Idempotent: return 200 without duplicate action
                if booking.payment_status == "paid":
                    return jsonify({"status": "already_processed"}), 200

                booking.payment_status = "paid"
                if payment_id:
                    booking.razorpay_payment_id = payment_id
                if amount_paid:
                    booking.amount_paid = amount_paid
                if method:
                    booking.payment_method = method
                booking.status = "confirmed"
                booking.confirmed_at = datetime.utcnow()
                db.session.commit()
                return jsonify({"status": "processed", "booking_id": booking.id}), 200

    return jsonify({"status": "ignored"}), 200
