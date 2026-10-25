"""Production WSGI entrypoint for VYBE.

Loads configuration via environment variables (defaults to ProductionConfig in production)
and initializes the application instance for Gunicorn / uWSGI / Render.
"""

import os
from app import create_app
from config import config_by_name, get_config

env_name = os.environ.get("FLASK_ENV") or os.environ.get("ENV") or "production"
config_cls = config_by_name.get(env_name.lower(), get_config())

application = create_app(config_cls)
app = application

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    application.run(host="0.0.0.0", port=port)
