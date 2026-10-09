from flask import Blueprint, jsonify, render_template

from models import TravelPackage

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    featured = (
        TravelPackage.query.filter_by(is_active=True)
        .order_by(TravelPackage.created_at.desc())
        .limit(6)
        .all()
    )
    return render_template("index.html", featured=featured)


@main_bp.get("/health")
def health():
    return jsonify({"status": "ok", "app": "VYBE"})
