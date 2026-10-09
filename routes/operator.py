import os

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from config import Config
from models import Conversation, Interest, TravelCompany, TravelPackage, VerificationRecord, db

operator_bp = Blueprint("operator", __name__)


def _own_company() -> TravelCompany | None:
    if not current_user.is_authenticated:
        return None
    return TravelCompany.query.filter_by(user_id=current_user.id).first()


@operator_bp.route("/operator", methods=["GET"])
@login_required
def dashboard():
    if current_user.role not in ("operator", "admin"):
        abort(403)
    company = _own_company()
    packages, interests, conversations = [], [], []
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
    return render_template(
        "operator_dashboard.html",
        company=company,
        packages=packages,
        interests=interests,
        conversations=conversations,
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
        company.contact_details = data.get("contact_details")
        company.description = data.get("description")
        company.licence_info = data.get("licence_info")
        company.service_regions = data.getlist("service_regions") or company.service_regions
        # optional doc upload
        f = request.files.get("document")
        if f and f.filename:
            ext = f.filename.rsplit(".", 1)[-1].lower()
            if ext in Config.ALLOWED_EXTENSIONS:
                os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
                path = os.path.join(Config.UPLOAD_FOLDER, secure_filename(f.filename))
                f.save(path)
                company.document_path = path
        db.session.commit()
        # ensure a verification record exists
        if not VerificationRecord.query.filter_by(company_id=company.id, status="pending").first():
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
    pkg = TravelPackage.query.get_or_404(pkg_id) if pkg_id else None
    if request.method == "POST":
        data = request.form
        target = pkg or TravelPackage(operator_id=company.id if company else None)
        if target.operator_id is None:  # admin fallback
            fallback = TravelCompany.query.filter_by(status="approved").first()
            target.operator_id = fallback.id if fallback else None
        target.title = data.get("title", target.title)
        target.destination = data.get("destination", target.destination)
        target.short_desc = data.get("short_desc", target.short_desc)
        target.itinerary = data.get("itinerary", target.itinerary)
        target.price = int(data.get("price") or target.price or 0)
        target.duration_days = int(data.get("duration_days") or target.duration_days or 1)
        target.cover_image = data.get("cover_image", target.cover_image)
        target.group_size = data.get("group_size", target.group_size)
        target.accommodation = data.get("accommodation", target.accommodation)
        target.transportation = data.get("transportation", target.transportation)
        target.is_active = bool(data.get("is_active", target.is_active if pkg else True))
        for field in ("region_tags", "interest_tags", "mood_tags", "climate_tags"):
            vals = data.get(field, "")
            if vals:
                setattr(target, field, [v.strip() for v in vals.split(",") if v.strip()])
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
        company = TravelCompany(
            user_id=current_user.id,
            company_name=data.get("company_name", ""),
            business_email=data.get("business_email", current_user.email),
            contact_details=data.get("contact_details"),
            description=data.get("description"),
            licence_info=data.get("licence_info"),
            service_regions=data.get("service_regions", []),
            status="pending",
        )
        db.session.add(company)
        db.session.flush()
    company.status = "pending"
    company.is_verified = False
    db.session.add(VerificationRecord(company_id=company.id, submitted_by=current_user.id))
    db.session.commit()
    return jsonify({"company": company.to_dict()}), 201
