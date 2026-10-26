import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _normalize_db_uri(uri: str) -> str:
    """Normalize SQLite and PostgreSQL/Supabase database URIs.

    - Strips surrounding quotes, whitespace, and accidental brackets.
    - Replaces 'postgres://' or 'postgresql://' with 'postgresql+psycopg://'
      as required by SQLAlchemy 2.x for PostgreSQL providers like Supabase/Render.
    - Resolves relative SQLite paths to <repo>/instance/vybe.db.
    - Sanitizes duplicate '@' separators in connection strings.
    - Transparently routes direct Supabase host to IPv4 Transaction Pooler when on Vercel.
    - Ensures sslmode=require for remote PostgreSQL providers.
    """
    if not uri:
        if os.environ.get("VERCEL"):
            return "sqlite:////tmp/vybe.db"
        return "sqlite:///" + os.path.join(BASE_DIR, "instance", "vybe.db")

    import re

    uri = uri.strip().strip("'\"")

    # Supabase & Render provide postgres:// or postgresql://
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql+psycopg://", 1)
    elif uri.startswith("postgresql://") and not uri.startswith("postgresql+"):
        uri = uri.replace("postgresql://", "postgresql+psycopg://", 1)

    if uri.startswith("postgresql+psycopg://"):
        # Strip accidental square brackets if the user preserved template brackets like [YOUR-PASSWORD]
        uri = re.sub(r":\[([^\]]+)\]@", r":\1@", uri)

        scheme, rest = uri.split("://", 1)
        path = ""
        if "/" in rest:
            auth, path = rest.split("/", 1)
            path = "/" + path
        else:
            auth = rest

        # Fix duplicate '@' symbols in authority segment (e.g., user:pass@extra@host)
        if auth.count("@") > 1:
            at_parts = auth.split("@")
            creds = at_parts[0]
            host_port = at_parts[-1]
            auth = f"{creds}@{host_port}"

        # If direct Supabase connection is used for this project, automatically route
        # to the IPv4 Transaction Pooler (required on Vercel AWS Lambda to avoid IPv6 errors)
        if "db.qwaofsqxmusumvefhsqv.supabase.co" in auth:
            if "@" in auth:
                user_pass, _ = auth.rsplit("@", 1)
                if ":" in user_pass:
                    u, p = user_pass.split(":", 1)
                    if u == "postgres":
                        u = "postgres.qwaofsqxmusumvefhsqv"
                    auth = f"{u}:{p}@aws-0-ap-southeast-2.pooler.supabase.com:6543"
            else:
                auth = "postgres.qwaofsqxmusumvefhsqv@aws-0-ap-southeast-2.pooler.supabase.com:6543"

        uri = f"{scheme}://{auth}{path}"

        if ("supabase.co" in uri or "pooler.supabase.com" in uri) and "sslmode=" not in uri:
            sep = "&" if "?" in uri else "?"
            uri = f"{uri}{sep}sslmode=require"

    if uri.startswith("sqlite:///") and not uri.startswith("sqlite:////"):
        if os.environ.get("VERCEL"):
            return "sqlite:////tmp/vybe.db"
        path = uri.replace("sqlite:///", "", 1).replace("\\", "/")
        if path.startswith("instance/"):
            path = path[len("instance/"):]
        if not os.path.isabs(path):
            path = os.path.join(BASE_DIR, "instance", path)
        return "sqlite:///" + os.path.abspath(path)

    return uri


class BaseConfig:
    """Base configuration shared across all environments."""

    ENV = os.environ.get("FLASK_ENV", "development")
    FLASK_ENV = ENV
    DEBUG = False
    TESTING = False

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-vybe-change-me")
    SQLALCHEMY_DATABASE_URI = _normalize_db_uri(
        os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "vybe.db"))
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Connection pool defaults (Optimized for Supabase Transaction Pooler)
    if "postgresql" in SQLALCHEMY_DATABASE_URI:
        _is_serverless = bool(os.environ.get("VERCEL"))
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_recycle": 60,
            "pool_size": 2 if _is_serverless else int(os.environ.get("DB_POOL_SIZE", "10")),
            "max_overflow": 2 if _is_serverless else int(os.environ.get("DB_MAX_OVERFLOW", "20")),
        }

    # Cookie & Session Security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '').lower() in ('true', '1') or bool(os.environ.get('VERCEL'))
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', '').lower() in ('true', '1') or bool(os.environ.get('VERCEL'))

    # Storage settings
    UPLOAD_FOLDER = "/tmp/uploads" if os.environ.get("VERCEL") else os.path.join(BASE_DIR, "instance", "uploads")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}

    # Cloudflare R2 Storage (S3-compatible)
    R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "vybe-uploads")
    R2_PUBLIC_BASE_URL = os.environ.get("R2_PUBLIC_BASE_URL", "")

    # Supabase Client & Service Settings
    SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
    SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")  # Client-safe public key
    SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")  # Server-only key
    SUPABASE_STORAGE_BUCKET = os.environ.get("SUPABASE_STORAGE_BUCKET", "vybe-packages")

    # Maintenance & Automatic Cleanup
    CRON_SECRET = os.environ.get("CRON_SECRET", "dev-cron-secret-change-me")
    CLEANUP_RETENTION_DAYS = int(os.environ.get("CLEANUP_RETENTION_DAYS", "90"))

    # Razorpay Payments (INR)
    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

    # Firebase Cloud Messaging (Push Notifications)
    FIREBASE_PROJECT_ID = os.environ.get("FIREBASE_PROJECT_ID", "")
    FIREBASE_CREDENTIALS_JSON = os.environ.get("FIREBASE_CREDENTIALS_JSON", "")
    FIREBASE_SERVER_KEY = os.environ.get("FIREBASE_SERVER_KEY", "")

    # Optional AI assistant integration
    VYBE_AI_API_URL = os.environ.get("VYBE_AI_API_URL", "")
    VYBE_AI_API_KEY = os.environ.get("VYBE_AI_API_KEY", "")
    VYBE_AI_MODEL = os.environ.get("VYBE_AI_MODEL", "")

    # Auto-seed behavior flag
    AUTO_SEED_DEMO = False

    @classmethod
    def init_app(cls, app):
        """Hook for environment-specific app initialization."""
        pass


class DevelopmentConfig(BaseConfig):
    """Configuration for local development."""

    DEBUG = True
    TEMPLATES_AUTO_RELOAD = True
    AUTO_SEED_DEMO = True


class TestingConfig(BaseConfig):
    """Configuration for automated test runners."""

    TESTING = True
    DEBUG = False
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    AUTO_SEED_DEMO = False
    SECRET_KEY = "test-secret-key-vybe"


class ProductionConfig(BaseConfig):
    """Configuration for hardened production deployment."""

    DEBUG = False
    TESTING = False
    TEMPLATES_AUTO_RELOAD = False
    SESSION_COOKIE_SECURE = True
    AUTO_SEED_DEMO = False

    @classmethod
    def init_app(cls, app):
        super().init_app(app)
        secret = os.environ.get("SECRET_KEY")
        if not secret or secret in ("dev-vybe-change-me", "dev-change-me-in-env"):
            if os.environ.get("VERCEL"):
                app.config["SECRET_KEY"] = "vybe_prod_sec_7a8b9c1d2e3f405162738495a6b7c8d9"
            else:
                raise RuntimeError(
                    "CRITICAL SECURITY ERROR: SECRET_KEY environment variable must be set to a secure random value in production."
                )


# Configuration dictionary lookup
config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config():
    """Resolve active configuration class based on FLASK_ENV or ENV."""
    env = os.environ.get("FLASK_ENV") or os.environ.get("ENV") or "development"
    return config_by_name.get(env.lower(), DevelopmentConfig)


# Backwards compatibility: export Config as the resolved active configuration
Config = get_config()
