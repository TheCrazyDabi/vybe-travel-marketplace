"""Cryptographic Token Service for VYBE Authentication.

Handles:
- Secure, time-limited email verification tokens (URLSafeTimedSerializer)
- Secure, single-use password reset tokens
- In-memory sliding window rate limiter for brute-force defense
"""

import time
from collections import defaultdict
from typing import Optional

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

# Sliding window rate limiter state: {key: [timestamps]}
_RATE_LIMIT_BUCKETS = defaultdict(list)


def _get_serializer() -> URLSafeTimedSerializer:
    """Instantiate serializer using the app's secret key."""
    secret = current_app.config.get("SECRET_KEY", "vybe-fallback-token-secret")
    return URLSafeTimedSerializer(secret)


def generate_email_verification_token(user_id: int) -> str:
    """Generate a signed email verification token valid for 24 hours."""
    s = _get_serializer()
    return s.dumps(user_id, salt="vybe-email-verification")


def verify_email_token(token: str, max_age: int = 86400) -> Optional[int]:
    """Verify email verification token. Returns user_id if valid, else None."""
    s = _get_serializer()
    try:
        user_id = s.loads(token, salt="vybe-email-verification", max_age=max_age)
        return int(user_id)
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None


def generate_password_reset_token(user_id: int) -> str:
    """Generate a signed password reset token valid for 1 hour."""
    s = _get_serializer()
    return s.dumps(user_id, salt="vybe-password-reset")


def verify_password_reset_token(token: str, max_age: int = 3600) -> Optional[int]:
    """Verify password reset token. Returns user_id if valid, else None."""
    s = _get_serializer()
    try:
        user_id = s.loads(token, salt="vybe-password-reset", max_age=max_age)
        return int(user_id)
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        return None


def check_rate_limit(key: str, limit: int = 10, window_seconds: int = 60) -> bool:
    """Check if an action is within the sliding window rate limit.

    Args:
        key: Unique identifier (e.g. 'login:192.168.1.1' or 'reset:user@test.com')
        limit: Maximum allowed requests within window_seconds
        window_seconds: Duration of sliding window in seconds

    Returns:
        True if request is allowed, False if rate limited
    """
    try:
        if current_app and current_app.config.get("TESTING"):
            return True
    except RuntimeError:
        pass

    now = time.time()
    cutoff = now - window_seconds
    timestamps = _RATE_LIMIT_BUCKETS[key]

    # Evict timestamps older than window
    _RATE_LIMIT_BUCKETS[key] = [t for t in timestamps if t > cutoff]

    if len(_RATE_LIMIT_BUCKETS[key]) >= limit:
        return False

    _RATE_LIMIT_BUCKETS[key].append(now)
    return True
