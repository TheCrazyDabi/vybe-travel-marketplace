import os

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from config import Config
from models import Conversation, Interest, TravelCompany, TravelPackage, VerificationRecord, db
from models.booking import Booking, Enquiry
from models.custom_offer import CustomOffer

operator_bp = Blueprint("operator", __name__)


def _own_company() -> TravelCompany | None:
    if not current_user.is_authenticated:
        return None
    return TravelCompany.query.filter_by(user_id=current_user.id).first()


def _to_int(v, default=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


@operator_bp.route("/operator", methods=["GET"])
@login_required
def dashboard():
    if current_user.role not in ("operator", "admin"):
        abort(403)
    company = _own_company()
    packages, interests, conversations, enquiries, bookings, offers = [], [], [], [], [], []
    latest_review = None
    if company:
        latest_review = (
            VerificationRecord.query.filter_by(company_id=company.id)
            .order_by(VerificationRecord.created_at.desc())
            .first()
        )
    if company:
        packages = TravelPackage.query.filter_by(operator_id=company.id).all()
        pkg_ids = [p.id for p in packages]
        if pkg_ids:
            interests = (
                Interest.query.filter(Interest.package_id.in_(pkg_ids), Interest.action == "like")
                .order_by(Interest.created_at.desc())
                .limit(50)
                .all()
            )
        conversations = (
            Conversation.query.filter_by(company_id=company.id)
            .order_by(Conversation.updated_at.desc())
            .limit(50)
            .all()
        )
        enquiries = (
            Enquiry.query.filter_by(company_id=company.id)
            .order_by(Enquiry.updated_at.desc())
            .limit(100)
            .all()
        )
        bookings = (
            Booking.query.filter_by(company_id=company.id)
            .order_by(Booking.created_at.desc())
            .limit(100)
            .all()
        )
        offers = (
            CustomOffer.query.filter_by(company_id=company.id)
            .order_by(CustomOffer.updated_at.desc())
            .limit(100)
            .all()
        )
    return render_template(
        "operator_dashboard.html",
        company=company,
        packages=packages,
        interests=interests,
        conversations=conversations,
        enquiries=enquiries,
        bookings=bookings,
        offers=offers,
        latest_review=latest_review,
    )


@operator_bp.route("/operator/company", methods=["GET", "POST"])
@login_required
def company_form():
    if current_user.role not in ("operator", "admin"):
        abort(403)
    company = _own_company()
    if request.method == "POST":
        data = request.form
        if not company:
            company = TravelCompany(user_id=current_user.id, status="pending")
            db.session.add(company)
        company.company_name = data.get("company_name") or company.company_name or ""
        company.business_email = data.get("business_email") or current_user.email
        company.contact_details = data.get("contact_details") or data.get("phone") or company.contact_details
        company.description = data.get("description") or data.get("business_description") or company.description
        company.licence_info = data.get("licence_info")
        regions = data.getlist("service_regions") or data.getlist("operating_regions")
        if regions:
            company.service_regions = regions
            company.operating_regions = regions
        # Phase 2 extras
        if data.get("contact_person") is not None:
            company.contact_person = data.get("contact_person").strip() or None
        if data.get("business_type") is not None:
            company.business_type = data.get("business_type").strip() or None
        if data.get("phone") is not None:
            company.phone = data.get("phone").strip() or None
        # optional doc upload
        f = request.files.get("document")
        if f and f.filename:
            ext = f.filename.rsplit(".", 1)[-1].lower()
            if ext in Config.ALLOWED_EXTENSIONS:
                os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
                path = os.path.join(Config.UPLOAD_FOLDER, secure_filename(f.filename))
                f.save(path)
                company.document_path = path
        # basic validation: company name required for new
        if not (company.company_name or "").strip():
            return render_template("verification.html", company=company, error="Company name is required."), 400
        db.session.commit()
        # ensure a verification record exists
        if not VerificationRecord.query.filter_by(company_id=company.id, status="pending").first():
            # only add pending record if company is pending
            if company.status == "pending":
                db.session.add(VerificationRecord(company_id=company.id, submitted_by=current_user.id))
                db.session.commit()
            elif company.status in ("approved", "rejected") and current_user.role == "operator":
                # resubmit resets to pending (real verification flow, no fake verified)
                company.status = "pending"
                company.is_verified = False
                db.session.add(VerificationRecord(company_id=company.id, submitted_by=current_user.id))
                db.session.commit()
        return redirect(url_for("operator.dashboard"))
    return render_template("verification.html", company=company)


@operator_bp.route("/operator/packages/new", methods=["GET", "POST"])
@operator_bp.route("/operator/packages/<int:pkg_id>/edit", methods=["GET", "POST"])
@login_required
def package_form(pkg_id: int | None = None):
    if current_user.role not in ("operator", "admin"):
        abort(403)
    company = _own_company()
    if not company and current_user.role != "admin":
        return redirect(url_for("operator.company_form"))
    if (company and company.status != "approved"
            and current_user.role != "admin"):
        flash("Publishing unlocks after your company is approved.", "error")
        return redirect(url_for("operator.dashboard"))
    pkg = TravelPackage.query.get_or_404(pkg_id) if pkg_id else None
    # ownership check on edit
    if pkg and company and pkg.operator_id != company.id and current_user.role != "admin":
        abort(403)
    if request.method == "POST":
        data = request.form
        target = pkg or TravelPackage(operator_id=company.id if company else None)
        if target.operator_id is None:  # admin fallback
            fallback = TravelCompany.query.filter_by(status="approved").first()
            target.operator_id = fallback.id if fallback else None
        title = (data.get("title") or (target.title or "")).strip()
        destination = (data.get("destination") or (target.destination or "")).strip()
        if not pkg and (not title or not destination):
            return render_template(
                "package_form.html", pkg=pkg, company=company,
                error="Title and destination are required.",
            ), 400
        try:
            price = int(data.get("price") if data.get("price") not in (None, "") else (target.price or 0))
            days = int(data.get("duration_days") if data.get("duration_days") not in (None, "") else (target.duration_days or 1))
        except (TypeError, ValueError):
            return render_template("package_form.html", pkg=pkg, company=company, error="Price and days must be numbers."), 400
        if price < 0:
            return render_template("package_form.html", pkg=pkg, company=company, error="Price must be >= 0."), 400
        if days < 1 or days > 365:
            return render_template("package_form.html", pkg=pkg, company=company, error="Days must be 1..365."), 400
        target.title = title or target.title
        target.destination = destination or target.destination
        target.short_desc = data.get("short_desc", target.short_desc)
        target.itinerary = data.get("itinerary", target.itinerary)
        target.price = price
        target.duration_days = days
        target.cover_image = data.get("cover_image", target.cover_image)
        target.group_size = data.get("group_size", target.group_size)
        target.accommodation = data.get("accommodation", target.accommodation)
        target.transportation = data.get("transportation", target.transportation)
        target.available_dates = data.get("available_dates", target.available_dates)
        target.cancellation_terms = data.get("cancellation_terms", target.cancellation_terms)
        target.customization_options = data.get("customization_options", target.customization_options)
        # Checkbox semantics: unchecked box omits the key -> False.
        target.is_active = "is_active" in data
        for field in ("region_tags", "interest_tags", "mood_tags", "climate_tags",
                      "suitable_travel_styles", "suitable_groups", "included", "excluded", "activities"):
            vals = data.get(field, "")
            if vals:
                if isinstance(vals, str):
                    setattr(target, field, [v.strip() for v in vals.split(",") if v.strip()])
        for f in ("nights", "min_group_size", "max_group_size", "capacity", "seats_remaining"):
            if data.get(f) not in (None, ""):
                setattr(target, f, _to_int(data.get(f), getattr(target, f)))
        if data.get("images"):
            target.images = [v.strip() for v in data.get("images").split(",") if v.strip()]
        if data.get("departure_dates_list"):
            target.departure_dates_list = [v.strip() for v in data.get("departure_dates_list").split(",") if v.strip()]
        if target.nights is None and target.duration_days:
            target.nights = max(0, target.duration_days - 1)
        if target.seats_remaining is None and target.capacity is not None:
            target.seats_remaining = target.capacity
        from datetime import datetime as _dt3
        target.price_kind = target.price_kind or "operator_quote"
        target.price_confirmed_at = _dt3.utcnow()
        ming, maxg = target.min_group_size, target.max_group_size
        if isinstance(ming, int) and isinstance(maxg, int) and ming is not None and maxg is not None and ming > maxg:
            return render_template("package_form.html", pkg=pkg, company=company, error="Min group cannot exceed max group."), 400
        if not pkg:
            db.session.add(target)
        db.session.commit()
        return redirect(url_for("operator.dashboard"))
    return render_template("package_form.html", pkg=pkg, company=company)


# ---- JSON ----
@operator_bp.post("/api/companies/verification")
@login_required
def api_submit_verification():
    data = request.get_json(force=True, silent=True) or {}
    company = _own_company()
    if not company:
        if current_user.role != "operator":
            return jsonify({"error": "operators only"}), 403
        if not (data.get("company_name") or "").strip():
            return jsonify({"error": "company_name required"}), 400
        company = TravelCompany(
            user_id=current_user.id,
            company_name=data.get("company_name", "").strip(),
            business_email=data.get("business_email", current_user.email),
            contact_details=data.get("contact_details") or data.get("phone"),
            description=data.get("description"),
            licence_info=data.get("licence_info"),
            service_regions=data.get("service_regions", data.get("operating_regions", [])),
            contact_person=data.get("contact_person"),
            business_type=data.get("business_type"),
            phone=data.get("phone"),
            operating_regions=data.get("operating_regions", data.get("service_regions", [])),
            status="pending",
        )
        db.session.add(company)
        db.session.flush()
    else:
        # update extras if provided
        for f in ("contact_person", "business_type", "phone"):
            if f in data:
                setattr(company, f, data[f])
        if "operating_regions" in data:
            company.operating_regions = data["operating_regions"]
            company.service_regions = data["operating_regions"]
        elif "service_regions" in data:
            company.service_regions = data["service_regions"]
            company.operating_regions = data["service_regions"]
    company.status = "pending"
    company.is_verified = False
    db.session.add(VerificationRecord(company_id=company.id, submitted_by=current_user.id))
    db.session.commit()
    return jsonify({"company": company.to_dict()}), 201
