"""Automated tests for Authentication resilience, Demo Account compatibility, and Real-time Security Protocols."""

import pytest
from app import create_app
from config import TestingConfig
from models import User, db
from services.auth_tokens import check_rate_limit


@pytest.fixture
def app():
    app = create_app(TestingConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_demo_password_compatibility_and_aliases(app, client):
    """Verify demo accounts accept both their role-named passwords and the 'pw123456' alias."""
    with app.app_context():
        # Create demo accounts with initial default password
        for email, role, pw in [
            ("traveler@vybe.demo", "traveler", "traveler123"),
            ("operator@vybe.demo", "operator", "operator123"),
            ("admin@vybe.demo", "admin", "admin123"),
        ]:
            u = User(name=f"Demo {role.capitalize()}", email=email, role=role)
            u.set_password(pw)
            db.session.add(u)
        db.session.commit()

        traveler = User.query.filter_by(email="traveler@vybe.demo").first()
        operator = User.query.filter_by(email="operator@vybe.demo").first()
        admin = User.query.filter_by(email="admin@vybe.demo").first()

        # 1. Role-specific passwords
        assert traveler.check_password("traveler123") is True
        assert operator.check_password("operator123") is True
        assert admin.check_password("admin123") is True

        # 2. Universal demo alias 'pw123456'
        assert traveler.check_password("pw123456") is True
        assert operator.check_password("pw123456") is True
        assert admin.check_password("pw123456") is True

        # 3. Invalid passwords rejected
        assert traveler.check_password("wrongpassword") is False
        assert operator.check_password("random123") is False
        assert admin.check_password("") is False


def test_api_login_with_demo_alias(app, client):
    """Test API login with pw123456 and role password."""
    with app.app_context():
        u = User(name="Demo Traveler", email="traveler@vybe.demo", role="traveler")
        u.set_password("traveler123")
        db.session.add(u)
        db.session.commit()

    # Login with role password
    res1 = client.post("/api/auth/login", json={"email": "traveler@vybe.demo", "password": "traveler123"})
    assert res1.status_code == 200
    assert res1.get_json()["user"]["email"] == "traveler@vybe.demo"

    # Login with alias password
    res2 = client.post("/api/auth/login", json={"email": "traveler@vybe.demo", "password": "pw123456"})
    assert res2.status_code == 200
    assert res2.get_json()["user"]["email"] == "traveler@vybe.demo"

    # Login with invalid password
    res3 = client.post("/api/auth/login", json={"email": "traveler@vybe.demo", "password": "wrong"})
    assert res3.status_code == 401


def test_demo_user_auto_provisioning_on_login(app, client):
    """Verify demo accounts are automatically provisioned if they don't yet exist in the DB."""
    with app.app_context():
        # Ensure user does not exist in clean DB
        assert User.query.filter_by(email="traveler@vybe.demo").first() is None

    # Logging in as traveler should auto-provision the user
    res = client.post("/api/auth/login", json={"email": "traveler@vybe.demo", "password": "traveler123"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["user"]["email"] == "traveler@vybe.demo"
    assert data["user"]["role"] == "traveler"

    with app.app_context():
        u = User.query.filter_by(email="traveler@vybe.demo").first()
        assert u is not None
        assert u.name == "Demo Traveler"


def test_realtime_security_headers(client):
    """Verify production security headers are attached to responses."""
    res = client.get("/login")
    assert res.status_code == 200

    headers = res.headers
    # MIME sniffing prevention
    assert headers.get("X-Content-Type-Options") == "nosniff"
    # Clickjacking protection
    assert headers.get("X-Frame-Options") == "SAMEORIGIN"
    # Referrer policy
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    # Permissions Policy
    assert "geolocation=(self)" in headers.get("Permissions-Policy", "")
    assert "microphone=()" in headers.get("Permissions-Policy", "")
    # Cross-Origin-Opener-Policy
    assert headers.get("Cross-Origin-Opener-Policy") == "same-origin-allow-popups"
    # Content-Security-Policy on HTML response
    csp = headers.get("Content-Security-Policy", "")
    assert "default-src 'self'" in csp
    assert "script-src" in csp
    assert "style-src" in csp


def test_rate_limiting_sliding_window():
    """Verify rate limiter blocks requests exceeding the threshold."""
    key = "test_rate_limit_unique_key"
    limit = 5
    window = 10

    for _ in range(limit):
        assert check_rate_limit(key, limit=limit, window_seconds=window) is True

    # Limit exceeded
    assert check_rate_limit(key, limit=limit, window_seconds=window) is False
