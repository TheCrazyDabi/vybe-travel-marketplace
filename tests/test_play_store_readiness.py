"""Test suite for Prompt 7 & Prompt 8: Google Play Store Release Readiness.

Verifies:
1. Public Privacy Policy page at GET /privacy.
2. Public Web Account Deletion page at GET /account/delete-request.
3. Public Web Account Deletion submission at POST /account/delete-request.
4. Verification of Android project files, SDK target 35, and minimal permissions.
"""

import os
import pytest
import xml.etree.ElementTree as ET

from config import Config
from models import User, db


@pytest.fixture
def test_app():
    from app import create_app

    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
        WTF_CSRF_ENABLED = False

    app = create_app(TestConfig)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(test_app):
    return test_app.test_client()


def test_public_privacy_policy_endpoint(client):
    """GET /privacy returns HTTP 200 and details essential data collection disclosures."""
    res = client.get("/privacy")
    assert res.status_code == 200
    html = res.get_data(as_text=True)

    assert "Privacy Policy" in html
    assert "Razorpay" in html
    assert "Cloudflare R2" in html
    assert "Account Deletion" in html
    assert "privacy@vybe.travel" in html


def test_public_account_deletion_page_and_flow(client, test_app):
    """GET /account/delete-request renders form; POST /account/delete-request anonymizes user."""
    # 1. GET page
    get_res = client.get("/account/delete-request")
    assert get_res.status_code == 200
    assert "Request Account Deletion" in get_res.get_data(as_text=True)

    # 2. Seed user for deletion
    with test_app.app_context():
        user = User(name="Charlie ToDelete", email="charlie@delete.test", role="traveler")
        user.set_password("mypassword123")
        db.session.add(user)
        db.session.commit()
        u_id = user.id

    # 3. Invalid credentials test
    bad_res = client.post(
        "/account/delete-request",
        data={"email": "charlie@delete.test", "password": "wrongpassword"},
    )
    assert bad_res.status_code == 200
    assert "Invalid credentials" in bad_res.get_data(as_text=True)

    # 4. Valid credentials test (HTML form submit)
    good_res = client.post(
        "/account/delete-request",
        data={"email": "charlie@delete.test", "password": "mypassword123"},
    )
    assert good_res.status_code == 200
    assert "Account Deletion Completed" in good_res.get_data(as_text=True)

    # 5. Verify database user is anonymized
    with test_app.app_context():
        del_user = db.session.get(User, u_id)
        assert del_user.status == "deleted"
        assert del_user.name == "Deleted User"
        assert "anonymized.vybe" in del_user.email
        assert del_user.check_password("mypassword123") is False


def test_public_account_deletion_json_api(client, test_app):
    """POST /account/delete-request supports JSON API clients."""
    with test_app.app_context():
        user = User(name="David ApiDelete", email="david@api.test", role="traveler")
        user.set_password("pass456")
        db.session.add(user)
        db.session.commit()
        u_id = user.id

    res = client.post(
        "/account/delete-request",
        json={"email": "david@api.test", "password": "pass456"},
    )
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    with test_app.app_context():
        u = db.session.get(User, u_id)
        assert u.status == "deleted"


def test_android_manifest_and_permissions():
    """Verify Android manifest targets correct package and limits permissions."""
    manifest_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "android", "app", "src", "main", "AndroidManifest.xml")
    assert os.path.exists(manifest_path), "AndroidManifest.xml must exist"

    tree = ET.parse(manifest_path)
    root = tree.getroot()

    permissions = [elem.attrib.get("{http://schemas.android.com/apk/res/android}name") for elem in root.findall("uses-permission")]
    # Verify required network permissions
    assert "android.permission.INTERNET" in permissions
    assert "android.permission.ACCESS_NETWORK_STATE" in permissions
    assert "android.permission.POST_NOTIFICATIONS" in permissions

    # Verify no dangerous unjustified permissions
    assert "android.permission.ACCESS_FINE_LOCATION" not in permissions
    assert "android.permission.READ_CONTACTS" not in permissions
    assert "android.permission.READ_SMS" not in permissions


def test_android_build_gradle_and_assets():
    """Verify Android build.gradle targets SDK 35 and offline assets exist."""
    root_dir = os.path.dirname(os.path.dirname(__file__))
    gradle_path = os.path.join(root_dir, "android", "app", "build.gradle")
    assert os.path.exists(gradle_path), "android/app/build.gradle must exist"

    with open(gradle_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert 'applicationId = "com.vybe.travel"' in content
    assert "targetSdk = 35" in content
    assert "compileSdk = 35" in content

    offline_path = os.path.join(root_dir, "android", "app", "src", "main", "assets", "offline.html")
    assert os.path.exists(offline_path), "offline.html asset must exist"

    main_activity_path = os.path.join(root_dir, "android", "app", "src", "main", "java", "com", "vybe", "travel", "MainActivity.java")
    assert os.path.exists(main_activity_path), "MainActivity.java must exist"
