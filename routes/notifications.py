"""Notification and FCM Token API routes for VYBE."""

from datetime import datetime
from flask import Blueprint, abort, jsonify, request
from flask_login import current_user, login_required

from models import Notification, db
from services.push import push_service

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.get("/api/notifications")
@login_required
def api_list_notifications():
    """Retrieve all notifications for the current authenticated user."""
    unread_only = request.args.get("unread") == "true"
    limit = min(100, max(1, int(request.args.get("limit", 50))))

    query = Notification.query.filter_by(user_id=current_user.id)
    if unread_only:
        query = query.filter_by(is_read=False)

    notifications = query.order_by(Notification.created_at.desc()).limit(limit).all()
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()

    return jsonify({
        "notifications": [n.to_dict() for n in notifications],
        "unread_count": unread_count,
    })


@notifications_bp.get("/api/notifications/poll")
@login_required
def api_poll_notifications():
    """Realtime long-polling fallback for new notifications since a given timestamp."""
    since_str = request.args.get("since")
    query = Notification.query.filter_by(user_id=current_user.id)

    if since_str:
        try:
            since_dt = datetime.fromisoformat(since_str.replace("Z", "+00:00")).replace(tzinfo=None)
            query = query.filter(Notification.created_at > since_dt)
        except (ValueError, TypeError):
            pass

    new_items = query.order_by(Notification.created_at.asc()).limit(50).all()
    unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()

    return jsonify({
        "notifications": [n.to_dict() for n in new_items],
        "unread_count": unread_count,
        "polled_at": datetime.utcnow().isoformat(),
    })


@notifications_bp.post("/api/notifications/<int:notif_id>/read")
@login_required
def api_mark_read(notif_id: int):
    """Mark a specific notification as read."""
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id != current_user.id:
        abort(403)

    notif.is_read = True
    db.session.commit()
    return jsonify({"ok": True, "notification": notif.to_dict()})


@notifications_bp.post("/api/notifications/read-all")
@login_required
def api_mark_all_read():
    """Mark all notifications for the current user as read."""
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"ok": True})


@notifications_bp.post("/api/notifications/device-token")
@login_required
def api_register_device_token():
    """Register or rotate an FCM device token for Android push notifications."""
    data = request.get_json(force=True, silent=True) or {}
    token = (data.get("token") or "").strip()
    platform = (data.get("platform") or "android").strip().lower()

    if not token:
        return jsonify({"error": "token is required"}), 400

    dev_token = push_service.register_device_token(
        user_id=current_user.id,
        token=token,
        platform=platform,
    )
    return jsonify({"ok": True, "device_token": dev_token.to_dict()})


@notifications_bp.delete("/api/notifications/device-token")
@login_required
def api_unregister_device_token():
    """Unregister an FCM device token."""
    data = request.get_json(force=True, silent=True) or {}
    token = (data.get("token") or "").strip()
    if not token:
        return jsonify({"error": "token is required"}), 400

    push_service.unregister_device_token(token)
    return jsonify({"ok": True})
