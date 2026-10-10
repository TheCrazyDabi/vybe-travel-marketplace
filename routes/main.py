from flask import Blueprint, jsonify, render_template, send_from_directory
import os

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    return render_template("index.html")


@main_bp.get("/health")
def health():
    return jsonify({"status": "ok", "app": "VYBE"})


@main_bp.get("/sw.js")
def service_worker():
    # Serve at root scope so the PWA service worker can control all pages.
    root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    resp = send_from_directory(root, "sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp
