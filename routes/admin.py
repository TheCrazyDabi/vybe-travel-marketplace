from datetime import datetime

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from models import Interest, Report, TravelCompany, TravelPackage, User, VerificationRecord, db

admin_bp = Blueprint("admin", __name__)


def _require_admin():
    if not current_user.is_authenticated or current_user.role != "admin":
        abort(403)


@admin_bp.get("/admin")
@login_required
def dashboard():
    _require_admin()
    return render_template("admin_dashboard.html", stats=_overview_stats())


def _overview_stats():
    return {
        "users_total": User.query.count(),
        "travelers": User.query.filter_by(role="traveler").count(),
        "operators": User.query.filter_by(role="operator").count(),
        "suspended": User.query.filter_by(status="suspended").count(),
        "pending_verifications": VerificationRecord.query.filter_by(status="pending").count(),
        "approved_operators": TravelCompany.query.filter_by(status="approved").count(),
        "rejected_operators": TravelCompany.query.filter_by(status="rejected").count(),
        "packages": TravelPackage.query.filter_by(is_active=True).count(),
        "interests": Interest.query.filter_by(action="like").count(),
        "open_reports": Report.query.filter(Report.status.in_(["new", "review"])).count(),
    }


@admin_bp.get("/api/admin/overview")
@login_required
def api_overview():
    _require_admin()
    return jsonify(_overview_stats())


@admin_bp.get("/api/admin/users")
@login_required
def api_users():
    _require_admin()
    q = (request.args.get("q") or "").strip().lower()
    role = (request.args.get("role") or "").strip().lower()
    status = (request.args.get("status") or "").strip().lower()
    query = User.query
    if role in ("traveler", "operator", "admin"):
        query = query.filter_by(role=role)
    if status in ("active", "suspended"):
        query = query.filter_by(status=status)
    users = query.order_by(User.created_at.desc()).limit(200).all()
    if q:
        users = [u for u in users if q in (u.email or "").lower() or q in (u.name or "").lower()]
    out = []
    for u in users:
        d = u.to_dict()
        company = TravelCompany.query.filter_by(user_id=u.id).first()
        d["company"] = (
            {"id": company.id, "company_name": company.company_name, "status": company.status}
            if company else None
        )
        out.append(d)
    return jsonify({"users": out})


@admin_bp.post("/api/admin/users/<int:user_id>/status")
@login_required
def api_user_status(user_id: int):
    _require_admin()
    data = request.get_json(force=True, silent=True) or {}
    status = (data.get("status") or "").lower()
    if status not in ("active", "suspended"):
        return jsonify({"error": "status must be active|suspended"}), 400
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        return jsonify({"error": "cannot change your own status"}), 400
    user.status = status
    user.status_reason = (data.get("reason") or "").strip() or None
    db.session.commit()
    return jsonify({"user": user.to_dict()})


@admin_bp.get("/admin/verifications")
@login_required
def verification_page():
    _require_admin()
    pending = VerificationRecord.query.filter_by(status="pending").all()
    companies = TravelCompany.query.order_by(TravelCompany.created_at.desc()).all()
    history = (
        VerificationRecord.query.filter(VerificationRecord.status != "pending")
        .order_by(VerificationRecord.reviewed_at.desc())
        .limit(50)
        .all()
    )
    reviewers = {u.id: u.name for u in User.query.all()}
    return render_template(
        "admin_verification.html", pending=pending, companies=companies,
        history=history, reviewers=reviewers,
    )


@admin_bp.get("/api/admin/verifications")
@login_required
def api_list():
    _require_admin()
    recs = VerificationRecord.query.order_by(VerificationRecord.created_at.desc()).all()
    reviewers = {u.id: u.name for u in User.query.all()}
    return jsonify({
        "verifications": [
            {
                "id": r.id, "company_id": r.company_id,
                "company_name": r.company.company_name if r.company else None,
                "status": r.status, "reviewer_note": r.reviewer_note,
                "reviewed_by": reviewers.get(r.reviewed_by),
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recs
        ]
    })


@admin_bp.post("/api/admin/verifications/<int:rec_id>/decision")
@login_required
def api_decide(rec_id: int):
    from flask import request

    _require_admin()
    rec = VerificationRecord.query.get_or_404(rec_id)
    data = request.get_json(force=True, silent=True) or {}
    decision = (data.get("decision") or "").lower()  # approve|reject
    if decision not in ("approve", "reject"):
        return jsonify({"error": "decision must be approve|reject"}), 400
    rec.status = "approved" if decision == "approve" else "rejected"
    rec.reviewer_note = data.get("note")
    rec.reviewed_by = current_user.id
    rec.reviewed_at = datetime.utcnow()
    if rec.company:
        rec.company.status = rec.status
        rec.company.is_verified = decision == "approve"
    db.session.commit()
    return jsonify({"ok": True, "status": rec.status})
