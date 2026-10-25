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
    return db.session.get(User, int(user_id))


import urllib.parse


class VercelMiddleware:
    """WSGI Middleware for seamless Vercel Serverless hosting.

    1. Resets SCRIPT_NAME to empty string so Flask mounts cleanly at the root.
    2. Rewrites PATH_INFO from __route parameter passed by vercel.json rewrites.
    3. Cleans QUERY_STRING so Flask request.args remains clean.
    """
    def __init__(self, wsgi_app):
        self.wsgi_app = wsgi_app

    def __call__(self, environ, start_response):
        environ["SCRIPT_NAME"] = ""
        qs = environ.get("QUERY_STRING", "")
        if "__route=" in qs:
            params = urllib.parse.parse_qs(qs, keep_blank_values=True)
            if "__route" in params and params["__route"]:
                target = params.pop("__route")[0]
                if not target.startswith("/"):
                    target = "/" + target
                environ["PATH_INFO"] = target
                clean_pairs = []
                for k, vs in params.items():
                    for v in vs:
                        clean_pairs.append((k, v))
                environ["QUERY_STRING"] = urllib.parse.urlencode(clean_pairs)
        elif environ.get("PATH_INFO", "").startswith("/api/index"):
            environ["PATH_INFO"] = "/"

        if not environ.get("PATH_INFO"):
            environ["PATH_INFO"] = "/"

        return self.wsgi_app(environ, start_response)

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    if hasattr(config_class, "init_app"):
        config_class.init_app(app)

    # Safely create local sqlite dir only when sqlite URI is used
    uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if uri.startswith("sqlite:///"):
        sqlite_path = uri.replace("sqlite:///", "", 1)
        db_dir = os.path.dirname(sqlite_path)
        if db_dir:
            try:
                os.makedirs(db_dir, exist_ok=True)
            except OSError:
                pass
    try:
        os.makedirs(app.config.get("UPLOAD_FOLDER", os.path.join(os.path.dirname(__file__), "instance", "uploads")), exist_ok=True)
    except OSError:
        pass

    db.init_app(app)
    login_manager.init_app(app)

    from routes.admin import admin_bp
    from routes.auth import auth_bp
    from routes.bookings import bookings_bp
    from routes.companion import companion_bp
    from routes.main import main_bp
    from routes.messaging import messaging_bp
    from routes.offers import offers_bp
    from routes.operator import operator_bp
    from routes.packages import packages_bp
    from routes.reports import reports_bp
    from routes.traveler import traveler_bp
    from routes.notifications import notifications_bp

    for bp in (main_bp, auth_bp, traveler_bp, packages_bp, operator_bp, messaging_bp, admin_bp, reports_bp, bookings_bp, offers_bp, companion_bp, notifications_bp):
        app.register_blueprint(bp)

    @app.context_processor
    def inject_brand():
        return {"brand": "VYBE", "tagline": "Your mood. Your trip. Your VYBE."}

    @app.get("/favicon.ico")
    def favicon():
        return app.send_static_file("images/favicon.svg")

    app.wsgi_app = VercelMiddleware(app.wsgi_app)

    @app.after_request
    def _add_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

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
        try:
            db.create_all()
            _migrate_schema()
            # Seed initial packages if the database is completely empty or AUTO_SEED_DEMO is True
            if not app.config.get("TESTING"):
                from models.package import TravelPackage

                is_empty = TravelPackage.query.first() is None
                if app.config.get("AUTO_SEED_DEMO") or is_empty:
                    from seed import seed_demo, seed_demo_packages

                    seed_demo()
                    seed_demo_packages()  # idempotent: only adds missing demo titles
        except Exception as e:
            app.logger.warning(f"Database bootstrap warning: {e}")

    return app


def _migrate_schema():
    """Safe additive migration for existing dev & production DBs (never drops data).

    Uses SQLAlchemy engine inspection so it works seamlessly across both
    SQLite and PostgreSQL (Supabase).
    """
    from sqlalchemy import inspect, text

    try:
        inspector = inspect(db.engine)
        existing_tables = set(inspector.get_table_names())
        is_pg = db.engine.dialect.name == "postgresql"
    except Exception:
        return

    b_false = "FALSE" if is_pg else "0"
    b_true = "TRUE" if is_pg else "1"

    def get_existing_cols(table: str):
        if table not in existing_tables:
            return set()
        try:
            return {c["name"] for c in inspector.get_columns(table)}
        except Exception:
            return set()

    def ensure(table: str, col_ddl: dict):
        cols = get_existing_cols(table)
        for col, ddl in col_ddl.items():
            if col not in cols:
                try:
                    if is_pg:
                        db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {ddl}"))
                    else:
                        db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
                    db.session.commit()
                except Exception:
                    db.session.rollback()

    user_cols = get_existing_cols("users")
    if "status" not in user_cols and "users" in existing_tables:
        try:
            db.session.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
            db.session.commit()
        except Exception:
            db.session.rollback()
    if "status_reason" not in user_cols and "users" in existing_tables:
        try:
            db.session.execute(text("ALTER TABLE users ADD COLUMN status_reason VARCHAR(255)"))
            db.session.commit()
        except Exception:
            db.session.rollback()
    try:
        db.session.execute(text("UPDATE users SET status='active' WHERE status IS NULL"))
        db.session.commit()
    except Exception:
        db.session.rollback()

    ensure("users", {
        "age_range": "VARCHAR(20)",
        "is_email_verified": f"BOOLEAN DEFAULT {b_false}",
        "last_login_at": "TIMESTAMP",
    })

    ensure("traveler_profiles", {
        "travel_moods": "JSON",
        "travel_pace": "VARCHAR(20)",
        "trip_desires": "JSON",
        "destination_prefs": "JSON",
        "activity_prefs": "JSON",
        "preferred_destinations": "JSON",
        "avoid_destinations": "JSON",
        "preferred_region_text": "VARCHAR(200)",
        "start_city": "VARCHAR(120)",
        "destination_text": "VARCHAR(200)",
        "budget_per_person": "INTEGER",
        "budget_flex_pct": "INTEGER DEFAULT 20",
        "travel_start_date": "VARCHAR(20)",
        "travel_end_date": "VARCHAR(20)",
        "date_flexible": f"BOOLEAN DEFAULT {b_true}",
        "num_travellers": "INTEGER DEFAULT 2",
        "accommodation_prefs": "JSON",
        "transport_prefs": "JSON",
        "trip_mode": "VARCHAR(20)",
        "travel_style": "VARCHAR(20)",
        "group_size_pref": "VARCHAR(30)",
        "itinerary_pref": "VARCHAR(20)",
        "priority": "VARCHAR(20)",
        "disliked_activities": "JSON",
        "accessibility_notes": "TEXT",
        "dietary_notes": "TEXT",
        "other_notes": "TEXT",
        "ideal_trip_text": "TEXT",
        "onboarding_completed": f"BOOLEAN DEFAULT {b_false}",
        "onboarding_step": "INTEGER DEFAULT 1",
    })
    ensure("travel_companies", {
        "contact_person": "VARCHAR(120)",
        "business_type": "VARCHAR(80)",
        "phone": "VARCHAR(50)",
        "operating_regions": "JSON",
        "is_demo": f"BOOLEAN DEFAULT {b_false}",
    })
    ensure("travel_packages", {
        "nights": "INTEGER",
        "min_group_size": "INTEGER",
        "max_group_size": "INTEGER",
        "suitable_travel_styles": "JSON",
        "suitable_groups": "JSON",
        "capacity": "INTEGER",
        "seats_remaining": "INTEGER",
        "customization_options": "TEXT",
        "images": "JSON",
        "departure_dates_list": "JSON",
        "price_breakdown": "JSON",
        "price_kind": "VARCHAR(20)",
        "price_confirmed_at": "TIMESTAMP",
        "is_demo": f"BOOLEAN DEFAULT {b_false}",
        "updated_at": "TIMESTAMP",
        "is_deleted": f"BOOLEAN DEFAULT {b_false}",
        "deleted_at": "TIMESTAMP",
        "status": "VARCHAR(30) DEFAULT 'active'",
        "trip_start_date": "TIMESTAMP",
        "trip_end_date": "TIMESTAMP",
        "booking_deadline": "TIMESTAMP",
        "valid_until": "TIMESTAMP",
    })
    ensure("interests", {
        "comment": "TEXT",
        "feedback_at": "TIMESTAMP",
    })
    ensure("bookings", {
        "booking_reference": "VARCHAR(36)",
        "idempotency_key": "VARCHAR(100)",
        "num_travellers": "INTEGER DEFAULT 1",
        "agreed_price_snapshot": "INTEGER",
        "price_breakdown_snapshot": "TEXT",
        "terms_snapshot": "TEXT",
        "capacity_reserved": f"BOOLEAN DEFAULT {b_false}",
        "cancellation_reason": "TEXT",
        "cancelled_by": "INTEGER",
        "cancelled_at": "TIMESTAMP",
        "accepted_at": "TIMESTAMP",
        "razorpay_order_id": "VARCHAR(100)",
        "razorpay_payment_id": "VARCHAR(100)",
        "razorpay_signature": "VARCHAR(255)",
        "currency": "VARCHAR(10) DEFAULT 'INR'",
        "amount_paid": "INTEGER",
        "payment_method": "VARCHAR(50)",
    })
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


app = create_app()


@app.route("/api/bootstrap", methods=["GET", "POST"])
def api_bootstrap():
    from flask import jsonify, request
    from models.package import TravelPackage
    secret = request.args.get("secret", "")
    if secret != app.config.get("SECRET_KEY") and TravelPackage.query.count() > 0:
        return jsonify({"error": "unauthorized", "packages_count": TravelPackage.query.count()}), 403
    try:
        _migrate_schema()
        from seed import seed_demo, seed_demo_packages
        counts = seed_demo()
        added = seed_demo_packages()
        return jsonify({
            "status": "seeded",
            "counts": counts,
            "expansion_added": added,
            "total_packages": TravelPackage.query.count()
        })
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("FLASK_PORT", "5000")))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug, host=host, port=port)
