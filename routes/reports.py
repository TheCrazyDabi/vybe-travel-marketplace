"""User safety reports: submit (any logged-in user) + admin review."""

from datetime import datetime

from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from models import Report, db

reports_bp = Blueprint("reports", __name__)


@reports_bp.post("/api/reports")
@login_required
def api_submit():
    data = request.get_json(force=True, silent=True) or {}
    target_type = (data.get("target_type") or "").lower()
    target_id = data.get("target_id")
    reason = (data.get("reason") or "").strip()
    if target_type not in ("user", "package", "company"):
        return jsonify({"error": "target_type must be user|package|company"}), 400
    if not isinstance(target_id, int) or not reason:
        return jsonify({"error": "target_id and reason required"}), 400
    rep = Report(
        reporter_id=current_user.id, target_type=target_type, target_id=target_id,
        reason=reason[:120], details=(data.get("details") or "").strip() or None,
    )
    db.session.add(rep)
    db.session.commit()
    return jsonify({"report": rep.to_dict()}), 201


@reports_bp.get("/api/admin/reports")
@login_required
def api_list():
    if not current_user.is_authenticated or current_user.role != "admin":
        abort(403)
    status = (request.args.get("status") or "").lower()
    query = Report.query
    if status in ("new", "review", "resolved", "dismissed"):
        query = query.filter_by(status=status)
    reps = query.order_by(Report.created_at.desc()).limit(200).all()
    return jsonify({"reports": [r.to_dict() for r in reps]})


@reports_bp.post("/api/admin/reports/<int:rep_id>/review")
@login_required
def api_review(rep_id: int):
    if not current_user.is_authenticated or current_user.role != "admin":
        abort(403)
    data = request.get_json(force=True, silent=True) or {}
    status = (data.get("status") or "").lower()
    if status not in ("review", "resolved", "dismissed"):
        return jsonify({"error": "status must be review|resolved|dismissed"}), 400
    rep = Report.query.get_or_404(rep_id)
    rep.status = status
    rep.action_taken = (data.get("action_taken") or "").strip() or None
    rep.handled_by = current_user.id
    rep.handled_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"report": rep.to_dict()})
