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

    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(VercelMiddleware(app.wsgi_app), x_for=1, x_proto=1, x_host=1, x_prefix=1)

    @app.after_request
    def _add_security_headers(response):
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Clickjacking defense
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        # XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Referrer privacy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Restrict sensitive device APIs
        response.headers["Permissions-Policy"] = "geolocation=(self), microphone=(), camera=()"
        # Browser popup / context isolation
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"

        # Content Security Policy (CSP) for HTML responses
        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type:
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com https://cdn.jsdelivr.net https://checkout.razorpay.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
                "font-src 'self' https://fonts.gstatic.com data:; "
                "img-src 'self' data: blob: https:; "
                "connect-src 'self' https://*.supabase.co https://api.razorpay.com https://unpkg.com; "
                "frame-src 'self' https://api.razorpay.com https://checkout.razorpay.com; "
                "object-src 'none'; "
                "base-uri 'self';"
            )
            response.headers["Content-Security-Policy"] = csp

        # Strict-Transport-Security (HSTS) on HTTPS / Vercel
        from flask import request
        if request.is_secure or bool(os.environ.get("VERCEL")):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

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
        # Only run DDL bootstrap in development or tests (never block Vercel serverless requests)
        if not os.environ.get("VERCEL"):
            try:
                db.create_all()
                _migrate_schema()
                if app.config.get("AUTO_SEED_DEMO") and not app.config.get("TESTING"):
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
        if is_pg:
            try:
                db.session.execute(text("ALTER TABLE travel_companies DROP CONSTRAINT IF EXISTS travel_companies_user_id_key"))
                db.session.commit()
            except Exception:
                db.session.rollback()
    except Exception:
        return

    # Master schema mapping for all models to guarantee zero UndefinedColumn errors
    SCHEMA_MAP = {
        'users': {'name': 'VARCHAR(120)', 'email': 'VARCHAR(255)', 'password_hash': 'VARCHAR(255)', 'role': 'VARCHAR(20)', 'status': "VARCHAR(20) DEFAULT 'active'", 'status_reason': 'VARCHAR(255)', 'auth_user_id': 'VARCHAR(64)', 'age_range': 'VARCHAR(20)', 'is_email_verified': 'BOOLEAN DEFAULT FALSE', 'last_login_at': 'TIMESTAMP', 'created_at': 'TIMESTAMP'},
        'traveler_profiles': {'user_id': 'INTEGER', 'budget_max': 'INTEGER', 'duration_days': 'INTEGER', 'preferred_regions': 'JSON', 'preferred_climate': 'JSON', 'scenery': 'JSON', 'interests': 'JSON', 'group_type': 'VARCHAR(20)', 'current_mood': 'VARCHAR(40)', 'avoid': 'JSON', 'updated_at': 'TIMESTAMP', 'travel_moods': 'JSON', 'travel_pace': 'VARCHAR(20)', 'trip_desires': 'JSON', 'destination_prefs': 'JSON', 'activity_prefs': 'JSON', 'preferred_destinations': 'JSON', 'avoid_destinations': 'JSON', 'preferred_region_text': 'VARCHAR(200)', 'start_city': 'VARCHAR(120)', 'destination_text': 'VARCHAR(200)', 'budget_per_person': 'INTEGER', 'budget_flex_pct': 'INTEGER DEFAULT 20', 'travel_start_date': 'VARCHAR(20)', 'travel_end_date': 'VARCHAR(20)', 'date_flexible': 'BOOLEAN DEFAULT TRUE', 'num_travellers': 'INTEGER DEFAULT 2', 'accommodation_prefs': 'JSON', 'transport_prefs': 'JSON', 'trip_mode': 'VARCHAR(20)', 'travel_style': 'VARCHAR(20)', 'group_size_pref': 'VARCHAR(30)', 'itinerary_pref': 'VARCHAR(20)', 'priority': 'VARCHAR(20)', 'disliked_activities': 'JSON', 'accessibility_notes': 'TEXT', 'dietary_notes': 'TEXT', 'other_notes': 'TEXT', 'ideal_trip_text': 'TEXT', 'onboarding_completed': 'BOOLEAN DEFAULT FALSE', 'onboarding_step': 'INTEGER DEFAULT 1'},
        'user_preferences': {'user_id': 'INTEGER', 'long_term': 'JSON', 'mood_weights': 'JSON', 'weights': 'JSON', 'updated_at': 'TIMESTAMP'},
        'travel_companies': {'user_id': 'INTEGER', 'company_name': 'VARCHAR(160)', 'business_email': 'VARCHAR(255)', 'contact_details': 'VARCHAR(255)', 'description': 'TEXT', 'licence_info': 'VARCHAR(255)', 'document_path': 'VARCHAR(512)', 'service_regions': 'JSON', 'logo': 'VARCHAR(512)', 'status': 'VARCHAR(20)', 'is_verified': 'BOOLEAN', 'created_at': 'TIMESTAMP', 'contact_person': 'VARCHAR(120)', 'business_type': 'VARCHAR(80)', 'phone': 'VARCHAR(50)', 'operating_regions': 'JSON', 'is_demo': 'BOOLEAN DEFAULT FALSE'},
        'verification_records': {'company_id': 'INTEGER', 'submitted_by': 'INTEGER', 'status': 'VARCHAR(20)', 'reviewer_note': 'TEXT', 'reviewed_by': 'INTEGER', 'created_at': 'TIMESTAMP', 'reviewed_at': 'TIMESTAMP'},
        'travel_packages': {'operator_id': 'INTEGER', 'title': 'VARCHAR(200)', 'destination': 'VARCHAR(120)', 'lat': 'FLOAT', 'lng': 'FLOAT', 'cover_image': 'VARCHAR(1024)', 'short_desc': 'VARCHAR(500)', 'itinerary': 'TEXT', 'price': 'INTEGER', 'currency': "VARCHAR(10) DEFAULT 'INR'", 'duration_days': 'INTEGER', 'available_dates': 'VARCHAR(255)', 'group_size': 'VARCHAR(64)', 'included': 'JSON', 'excluded': 'JSON', 'accommodation': 'VARCHAR(255)', 'transportation': 'VARCHAR(255)', 'activities': 'JSON', 'region_tags': 'JSON', 'climate_tags': 'JSON', 'scenery_tags': 'JSON', 'interest_tags': 'JSON', 'mood_tags': 'JSON', 'cancellation_terms': 'TEXT', 'is_active': 'BOOLEAN DEFAULT TRUE', 'is_deleted': 'BOOLEAN DEFAULT FALSE', 'deleted_at': 'TIMESTAMP', 'created_at': 'TIMESTAMP', 'nights': 'INTEGER', 'min_group_size': 'INTEGER', 'max_group_size': 'INTEGER', 'suitable_travel_styles': 'JSON', 'suitable_groups': 'JSON', 'capacity': 'INTEGER', 'seats_remaining': 'INTEGER', 'customization_options': 'TEXT', 'images': 'JSON', 'departure_dates_list': 'JSON', 'price_breakdown': 'JSON', 'price_kind': 'VARCHAR(20)', 'price_confirmed_at': 'TIMESTAMP', 'is_demo': 'BOOLEAN DEFAULT FALSE', 'updated_at': 'TIMESTAMP', 'status': "VARCHAR(30) DEFAULT 'active'", 'trip_start_date': 'TIMESTAMP', 'trip_end_date': 'TIMESTAMP', 'booking_deadline': 'TIMESTAMP', 'valid_until': 'TIMESTAMP'},
        'package_images': {'package_id': 'INTEGER', 'storage_path': 'VARCHAR(1024)', 'url': 'VARCHAR(1024)', 'is_cover': 'BOOLEAN DEFAULT FALSE', 'file_size': 'INTEGER', 'mime_type': 'VARCHAR(100)', 'uploaded_by': 'INTEGER', 'created_at': 'TIMESTAMP'},
        'interests': {'traveler_id': 'INTEGER', 'package_id': 'INTEGER', 'action': 'VARCHAR(10)', 'reason': 'VARCHAR(120)', 'comment': 'TEXT', 'feedback_at': 'TIMESTAMP', 'created_at': 'TIMESTAMP'},
        'conversations': {'traveler_id': 'INTEGER', 'company_id': 'INTEGER', 'package_id': 'INTEGER', 'status': 'VARCHAR(30)', 'created_at': 'TIMESTAMP', 'updated_at': 'TIMESTAMP'},
        'messages': {'conversation_id': 'INTEGER', 'sender_id': 'INTEGER', 'body': 'TEXT', 'is_read': 'BOOLEAN', 'created_at': 'TIMESTAMP'},
        'reports': {'reporter_id': 'INTEGER', 'target_type': 'VARCHAR(20)', 'target_id': 'INTEGER', 'reason': 'VARCHAR(120)', 'details': 'TEXT', 'status': 'VARCHAR(20)', 'action_taken': 'VARCHAR(255)', 'handled_by': 'INTEGER', 'handled_at': 'TIMESTAMP', 'created_at': 'TIMESTAMP'},
        'enquiries': {'traveler_id': 'INTEGER', 'package_id': 'INTEGER', 'company_id': 'INTEGER', 'status': 'VARCHAR(30)', 'num_travellers': 'INTEGER', 'travel_date': 'VARCHAR(30)', 'message': 'TEXT', 'total_cost': 'INTEGER', 'created_at': 'TIMESTAMP', 'updated_at': 'TIMESTAMP'},
        'quotations': {'enquiry_id': 'INTEGER', 'operator_id': 'INTEGER', 'price_per_person': 'INTEGER', 'total_price': 'INTEGER', 'availability_note': 'TEXT', 'valid_until': 'VARCHAR(30)', 'message': 'TEXT', 'status': 'VARCHAR(20)', 'created_at': 'TIMESTAMP'},
        'bookings': {'booking_reference': 'VARCHAR(36)', 'idempotency_key': 'VARCHAR(100)', 'enquiry_id': 'INTEGER', 'traveler_id': 'INTEGER', 'package_id': 'INTEGER', 'company_id': 'INTEGER', 'num_travellers': 'INTEGER DEFAULT 1', 'status': 'VARCHAR(20)', 'agreed_price_snapshot': 'INTEGER', 'price_breakdown_snapshot': 'JSON', 'terms_snapshot': 'TEXT', 'capacity_reserved': 'BOOLEAN DEFAULT FALSE', 'cancellation_reason': 'TEXT', 'cancelled_by': 'INTEGER', 'cancelled_at': 'TIMESTAMP', 'accepted_at': 'TIMESTAMP', 'traveller_details': 'JSON', 'total_cost': 'INTEGER', 'itinerary_snapshot': 'TEXT', 'terms': 'TEXT', 'payment_status': 'VARCHAR(30)', 'created_at': 'TIMESTAMP', 'confirmed_at': 'TIMESTAMP', 'razorpay_order_id': 'VARCHAR(100)', 'razorpay_payment_id': 'VARCHAR(100)', 'razorpay_signature': 'VARCHAR(255)', 'currency': "VARCHAR(10) DEFAULT 'INR'", 'amount_paid': 'INTEGER', 'payment_method': 'VARCHAR(50)'},
        'trip_plans': {'user_id': 'INTEGER', 'title': 'VARCHAR(160)', 'destination': 'VARCHAR(120)', 'country': 'VARCHAR(120)', 'dates': 'VARCHAR(120)', 'duration_days': 'INTEGER', 'traveler_count': 'INTEGER', 'status': 'VARCHAR(20)', 'summary': 'TEXT', 'meeting_point': 'VARCHAR(255)', 'announcements': 'JSON', 'created_at': 'TIMESTAMP'},
        'trip_days': {'trip_id': 'INTEGER', 'day_number': 'INTEGER', 'title': 'VARCHAR(160)', 'date': 'VARCHAR(80)'},
        'trip_stops': {'day_id': 'INTEGER', 'key': 'VARCHAR(60)', 'name': 'VARCHAR(160)', 'category': 'VARCHAR(80)', 'time_slot': 'VARCHAR(40)', 'duration': 'VARCHAR(40)', 'short_desc': 'TEXT', 'full_desc': 'TEXT', 'tips': 'JSON', 'precautions': 'JSON', 'visited': 'BOOLEAN', 'departure_ack': 'BOOLEAN'},
        'stop_activities': {'stop_id': 'INTEGER', 'key': 'VARCHAR(60)', 'title': 'VARCHAR(255)', 'done': 'BOOLEAN'},
        'pack_items': {'user_id': 'INTEGER', 'key': 'VARCHAR(60)', 'title': 'VARCHAR(255)', 'category': 'VARCHAR(40)', 'packed': 'BOOLEAN', 'belonging': 'BOOLEAN', 'custom': 'BOOLEAN'},
        'companion_messages': {'user_id': 'INTEGER', 'sender': 'VARCHAR(10)', 'body': 'TEXT', 'chips': 'JSON', 'created_at': 'TIMESTAMP'},
        'custom_offers': {'traveler_id': 'INTEGER', 'package_id': 'INTEGER', 'company_id': 'INTEGER', 'enquiry_id': 'INTEGER', 'parent_id': 'INTEGER', 'version': 'INTEGER', 'status': 'VARCHAR(30)', 'travel_dates': 'VARCHAR(120)', 'num_travellers': 'INTEGER', 'desired_budget': 'INTEGER', 'accommodation_pref': 'VARCHAR(255)', 'itinerary_changes': 'TEXT', 'transport_reqs': 'VARCHAR(255)', 'notes': 'TEXT', 'revised_price': 'INTEGER', 'revised_itinerary': 'TEXT', 'inclusions': 'JSON', 'exclusions': 'JSON', 'additional_charges': 'JSON', 'valid_until': 'VARCHAR(30)', 'operator_note': 'TEXT', 'created_at': 'TIMESTAMP', 'updated_at': 'TIMESTAMP'},
        'reviews': {'booking_id': 'INTEGER', 'traveler_id': 'INTEGER', 'package_id': 'INTEGER', 'company_id': 'INTEGER', 'rating': 'INTEGER', 'text': 'TEXT', 'status': 'VARCHAR(20)', 'created_at': 'TIMESTAMP'},
        'notifications': {'user_id': 'INTEGER', 'title': 'VARCHAR(200)', 'body': 'TEXT', 'type': 'VARCHAR(50)', 'data': 'JSON', 'is_read': 'BOOLEAN', 'created_at': 'TIMESTAMP'},
        'device_tokens': {'user_id': 'INTEGER', 'token': 'VARCHAR(500)', 'platform': 'VARCHAR(30)', 'created_at': 'TIMESTAMP', 'updated_at': 'TIMESTAMP'},
        'audit_events': {'user_id': 'INTEGER', 'action': 'VARCHAR(100)', 'target_type': 'VARCHAR(50)', 'target_id': 'VARCHAR(100)', 'ip_address': 'VARCHAR(45)', 'user_agent': 'VARCHAR(255)', 'details': 'JSON', 'created_at': 'TIMESTAMP'},
    }

    for table, col_ddl in SCHEMA_MAP.items():
        if table not in existing_tables:
            continue
        try:
            existing_cols = {c["name"] for c in inspector.get_columns(table)}
        except Exception:
            existing_cols = set()
        
        missing_cols = [(col, ddl) for col, ddl in col_ddl.items() if col not in existing_cols]
        if not missing_cols:
            continue
            
        try:
            if is_pg:
                clauses = [f"ADD COLUMN IF NOT EXISTS {col} {ddl}" for col, ddl in missing_cols]
                db.session.execute(text(f"ALTER TABLE {table} " + ", ".join(clauses)))
                db.session.commit()
            else:
                for col, ddl in missing_cols:
                    db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
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
