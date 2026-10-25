from flask import Blueprint, jsonify, render_template, send_from_directory
from sqlalchemy import text
import os
from models import db

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    return render_template("index.html")


@main_bp.get("/health")
@main_bp.get("/api/health")
def health():
    """Production health-check endpoint: verifies database connectivity without leaking secrets."""
    try:
        db.session.execute(text("SELECT 1"))
        return jsonify({"status": "ok", "app": "VYBE", "database": "connected"}), 200
    except Exception:
        return jsonify({"status": "degraded", "app": "VYBE", "database": "disconnected"}), 503


@main_bp.get("/sw.js")
def service_worker():
    # Serve at root scope so the PWA service worker can control all pages.
    root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    resp = send_from_directory(root, "sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@main_bp.get("/privacy")
def privacy_policy():
    """Public privacy policy fulfilling Google Play developer requirements."""
    return render_template("privacy_policy.html")

