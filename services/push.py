"""Firebase Cloud Messaging (FCM) & In-App Notification Service for VYBE.

Handles:
- Persistent in-app notifications
- Secure device token registration & rotation (Android / Web / iOS)
- Push delivery via Firebase Cloud Messaging HTTP API
- User notification preferences enforcement
- Offline / simulation fallback when Firebase credentials are not set
"""

import json
import logging
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error

from flask import current_app
from models import DeviceToken, Notification, User, db

logger = logging.getLogger(__name__)


class PushService:
    """Service provider for multi-channel user notifications and FCM push delivery."""

    @classmethod
    def register_device_token(cls, user_id: int, token: str, platform: str = "android") -> DeviceToken:
        """Register or rotate an FCM device token for a user."""
        token = token.strip()
        existing = DeviceToken.query.filter_by(token=token).first()
        if existing:
            existing.user_id = user_id
            existing.platform = platform
            db.session.commit()
            return existing

        dev_token = DeviceToken(user_id=user_id, token=token, platform=platform)
        db.session.add(dev_token)
        db.session.commit()
        logger.info("Registered device token for user %s (%s)", user_id, platform)
        return dev_token

    @classmethod
    def unregister_device_token(cls, token: str) -> bool:
        """Remove a device token upon logout or token invalidation."""
        token = token.strip()
        dev_token = DeviceToken.query.filter_by(token=token).first()
        if dev_token:
            db.session.delete(dev_token)
            db.session.commit()
            logger.info("Unregistered device token %s...", token[:12])
            return True
        return False

    @classmethod
    def send_notification(
        cls,
        user_id: int,
        title: str,
        body: str,
        notif_type: str = "info",
        data: Optional[Dict[str, Any]] = None,
    ) -> Notification:
        """Create a persistent notification record and attempt FCM push delivery."""
        notif = Notification(
            user_id=user_id,
            title=title,
            body=body,
            type=notif_type,
            data=data or {},
        )
        db.session.add(notif)
        db.session.commit()
        logger.info("Created persistent notification #%d for user %d: %s", notif.id, user_id, title)

        # Check if user has push notifications enabled
        user = db.session.get(User, user_id)
        if user and user.preference and not getattr(user.preference, "push_notifications", True):
            logger.info("Push notification suppressed by user preference for user %d", user_id)
            return notif

        # Attempt FCM push delivery
        cls._dispatch_fcm(user_id=user_id, title=title, body=body, data=data)
        return notif

    @classmethod
    def _dispatch_fcm(cls, user_id: int, title: str, body: str, data: Optional[Dict[str, Any]] = None):
        """Deliver push notification to all active devices registered to the user."""
        tokens = DeviceToken.query.filter_by(user_id=user_id).all()
        if not tokens:
            return

        server_key = current_app.config.get("FIREBASE_SERVER_KEY")
        if not server_key:
            logger.debug("Firebase server key not configured. Push simulated for user %d", user_id)
            return

        fcm_url = "https://fcm.googleapis.com/fcm/send"
        headers = {
            "Authorization": f"key={server_key}",
            "Content-Type": "application/json",
        }

        for dt in tokens:
            payload = {
                "to": dt.token,
                "notification": {
                    "title": title,
                    "body": body,
                    "sound": "default",
                },
                "data": {str(k): str(v) for k, v in (data or {}).items()},
            }
            try:
                req = urllib.request.Request(
                    fcm_url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    res_body = response.read().decode("utf-8")
                    if "InvalidRegistration" in res_body or "NotRegistered" in res_body:
                        logger.warning("Stale FCM token detected; removing %s...", dt.token[:12])
                        db.session.delete(dt)
                        db.session.commit()
            except Exception as e:
                logger.warning("FCM delivery error to token %s...: %s", dt.token[:12], e)


push_service = PushService
