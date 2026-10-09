"""VYBE — Your mood. Your trip. Your VYBE."""

import os

from flask import Flask
from flask_login import LoginManager

from config import Config
from models import User, db

login_manager = LoginManager()
login_manager.login_view = "auth.login_page"
login_manager.login_message_category = "error"


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db_path = app.config["SQLALCHEMY_DATABASE_URI"].replace("sqlite:///", "")
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from routes.admin import admin_bp
    from routes.auth import auth_bp
    from routes.main import main_bp
    from routes.messaging import messaging_bp
    from routes.operator import operator_bp
    from routes.packages import packages_bp
    from routes.reports import reports_bp
    from routes.traveler import traveler_bp

    for bp in (main_bp, auth_bp, traveler_bp, packages_bp, operator_bp, messaging_bp, admin_bp, reports_bp):
        app.register_blueprint(bp)

    @app.context_processor
    def inject_brand():
        return {"brand": "VYBE", "tagline": "Your mood. Your trip. Your VYBE."}

    @app.get("/favicon.ico")
    def favicon():
        return app.send_static_file("images/favicon.svg")

    @app.before_request
    def _enforce_account_status():
        from flask import jsonify, redirect, request, url_for
        from flask_login import current_user, logout_user

        if current_user.is_authenticated and (current_user.status or "active") != "active":
            logout_user()
            if request.path.startswith("/api/"):
                return jsonify({"error": "account suspended"}), 403
            from flask import flash

            flash("Account suspended. Contact support.", "error")
            return redirect(url_for("auth.login_page"))

    with app.app_context():
        db.create_all()
        _migrate_schema()
        # Lazy seed on first run so `python app.py` just works.
        # Skip auto-seed under TESTING so tests get an isolated DB.
        if not app.config.get("TESTING"):
            from seed import seed_if_empty

            seed_if_empty()

    return app


def _migrate_schema():
    """Safe additive migration for existing dev DBs (never drops data).

    db.create_all() creates new tables but won't add columns to existing
    ones, so backfill new columns here with ALTER TABLE when missing.
    """
    from sqlalchemy import text

    cols = {r[1] for r in db.session.execute(text("PRAGMA table_info(users)"))}
    if "status" not in cols:
        db.session.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
    if "status_reason" not in cols:
        db.session.execute(text("ALTER TABLE users ADD COLUMN status_reason VARCHAR(255)"))
    db.session.execute(text("UPDATE users SET status='active' WHERE status IS NULL"))
    db.session.commit()


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
