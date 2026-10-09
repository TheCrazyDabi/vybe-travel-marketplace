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
    from routes.traveler import traveler_bp

    for bp in (main_bp, auth_bp, traveler_bp, packages_bp, operator_bp, messaging_bp, admin_bp):
        app.register_blueprint(bp)

    @app.context_processor
    def inject_brand():
        return {"brand": "VYBE", "tagline": "Your mood. Your trip. Your VYBE."}

    with app.app_context():
        db.create_all()
        # Lazy seed on first run so `python app.py` just works.
        from seed import seed_if_empty

        seed_if_empty()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
