from datetime import datetime

from flask import Blueprint, abort, jsonify, render_template
from flask_login import current_user, login_required

from models import TravelCompany, VerificationRecord, db

admin_bp = Blueprint("admin", __name__)


def _require_admin():
    if not current_user.is_authenticated or current_user.role != "admin":
        abort(403)


@admin_bp.get("/admin/verifications")
@login_required
def verification_page():
    _require_admin()
    pending = VerificationRecord.query.filter_by(status="pending").all()
    companies = TravelCompany.query.order_by(TravelCompany.created_at.desc()).all()
    return render_template("admin_verification.html", pending=pending, companies=companies)


@admin_bp.get("/api/admin/verifications")
@login_required
def api_list():
    _require_admin()
    recs = VerificationRecord.query.order_by(VerificationRecord.created_at.desc()).all()
    return jsonify({
        "verifications": [
            {
                "id": r.id, "company_id": r.company_id,
                "company_name": r.company.company_name if r.company else None,
                "status": r.status, "reviewer_note": r.reviewer_note,
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
