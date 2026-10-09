from datetime import datetime

from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from models import Conversation, Message, TravelCompany, db

messaging_bp = Blueprint("messaging", __name__)


def _can_access(conv: Conversation) -> bool:
    if not current_user.is_authenticated:
        return False
    if current_user.role == "admin":
        return True
    if conv.traveler_id == current_user.id:
        return True
    comp = TravelCompany.query.filter_by(user_id=current_user.id).first()
    return comp is not None and conv.company_id == comp.id


@messaging_bp.get("/chats")
@login_required
def chats_page():
    if current_user.role == "operator":
        comp = TravelCompany.query.filter_by(user_id=current_user.id).first()
        convs = Conversation.query.filter_by(company_id=comp.id).all() if comp else []
    elif current_user.role == "admin":
        convs = Conversation.query.order_by(Conversation.updated_at.desc()).limit(100).all()
    else:
        convs = Conversation.query.filter_by(traveler_id=current_user.id).all()
    return render_template("chat.html", conversations=convs, active=None)


@messaging_bp.get("/chats/<int:conv_id>")
@login_required
def chat_detail(conv_id: int):
    conv = Conversation.query.get_or_404(conv_id)
    if not _can_access(conv):
        abort(403)
    if current_user.role == "operator":
        comp = TravelCompany.query.filter_by(user_id=current_user.id).first()
        convs = Conversation.query.filter_by(company_id=comp.id).all() if comp else []
    elif current_user.role == "admin":
        convs = Conversation.query.order_by(Conversation.updated_at.desc()).limit(100).all()
    else:
        convs = Conversation.query.filter_by(traveler_id=current_user.id).all()
    return render_template("chat.html", conversations=convs, active=conv)


# ---- JSON API ----
@messaging_bp.get("/api/conversations")
@login_required
def api_list_conversations():
    if current_user.role == "operator":
        comp = TravelCompany.query.filter_by(user_id=current_user.id).first()
        convs = Conversation.query.filter_by(company_id=comp.id).all() if comp else []
    elif current_user.role == "admin":
        convs = Conversation.query.order_by(Conversation.updated_at.desc()).limit(100).all()
    else:
        convs = Conversation.query.filter_by(traveler_id=current_user.id).all()
    return jsonify({"conversations": [c.to_dict() for c in convs]})


@messaging_bp.post("/api/conversations")
@login_required
def api_create_conversation():
    data = request.get_json(force=True, silent=True) or {}
    company_id = data.get("company_id")
    package_id = data.get("package_id")
    if not company_id:
        return jsonify({"error": "company_id required"}), 400
    existing = Conversation.query.filter_by(
        traveler_id=current_user.id, company_id=company_id, package_id=package_id
    ).first()
    if existing:
        return jsonify({"conversation": existing.to_dict(include_messages=True)})
    conv = Conversation(
        traveler_id=current_user.id, company_id=company_id,
        package_id=package_id, status="New",
    )
    db.session.add(conv)
    db.session.commit()
    return jsonify({"conversation": conv.to_dict(include_messages=True)}), 201


@messaging_bp.get("/api/conversations/<int:conv_id>/messages")
@login_required
def api_get_messages(conv_id: int):
    conv = Conversation.query.get_or_404(conv_id)
    if not _can_access(conv):
        abort(403)
    return jsonify({"messages": [m.to_dict() for m in conv.messages]})


@messaging_bp.post("/api/conversations/<int:conv_id>/messages")
@login_required
def api_post_message(conv_id: int):
    conv = Conversation.query.get_or_404(conv_id)
    if not _can_access(conv):
        abort(403)
    data = request.get_json(force=True, silent=True) or {}
    body = (data.get("body") or "").strip()
    if not body:
        return jsonify({"error": "body required"}), 400
    msg = Message(conversation_id=conv.id, sender_id=current_user.id, body=body)
    conv.updated_at = datetime.utcnow()
    if current_user.id != conv.traveler_id and "status" in data:
        conv.status = data["status"]
    elif current_user.id != conv.traveler_id and conv.status == "New":
        conv.status = "Contacted"
    db.session.add(msg)
    db.session.commit()
    return jsonify({"message": msg.to_dict()}), 201
