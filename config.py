import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _normalize_db_uri(uri: str) -> str:
    """Normalize SQLite and PostgreSQL/Supabase database URIs.

    - Replaces 'postgres://' with 'postgresql+psycopg://' (or 'postgresql://')
      as required by SQLAlchemy 2.x for PostgreSQL providers like Supabase/Render.
    - Resolves relative SQLite paths to <repo>/instance/vybe.db.
    """
    if not uri:
        return "sqlite:///" + os.path.join(BASE_DIR, "instance", "vybe.db")

    # Supabase & Render provide postgres:// or postgresql://
    if uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql+psycopg://", 1)
    elif uri.startswith("postgresql://") and not uri.startswith("postgresql+"):
        uri = uri.replace("postgresql://", "postgresql+psycopg://", 1)

    if uri.startswith("sqlite:///") and not uri.startswith("sqlite:////"):
        path = uri.replace("sqlite:///", "", 1).replace("\\", "/")
        if path.startswith("instance/"):
            path = path[len("instance/"):]
        if not os.path.isabs(path):
            path = os.path.join(BASE_DIR, "instance", path)
        return "sqlite:///" + os.path.abspath(path)

    return uri


class Config:
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-vybe-change-me")

    # In production, require an explicit secret key
    if FLASK_ENV == "production" and (not SECRET_KEY or SECRET_KEY == "dev-vybe-change-me"):
        raise RuntimeError("CRITICAL: SECRET_KEY environment variable must be set in production.")

    SQLALCHEMY_DATABASE_URI = _normalize_db_uri(
        os.environ.get(
            "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "vybe.db")
        )
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TEMPLATES_AUTO_RELOAD = FLASK_ENV != "production"

    # Database connection pool settings (resilient for Supabase transaction pooler)
    if "postgresql" in SQLALCHEMY_DATABASE_URI:
        SQLALCHEMY_ENGINE_OPTIONS = {
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "pool_size": int(os.environ.get("DB_POOL_SIZE", "10")),
            "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "20")),
        }

    # Session security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = FLASK_ENV == "production"

    # Local upload fallback (used in dev or when R2 is unconfigured)
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "instance", "uploads")
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}

    # Cloudflare R2 Storage (S3-compatible)
    R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
    R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
    R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
    R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "vybe-uploads")
    R2_PUBLIC_BASE_URL = os.environ.get("R2_PUBLIC_BASE_URL", "")  # Optional custom domain for public images

    # Razorpay Payments (INR)
    RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")

    # Optional AI (graceful fallback when unset)
    VYBE_AI_API_URL = os.environ.get("VYBE_AI_API_URL", "")
    VYBE_AI_API_KEY = os.environ.get("VYBE_AI_API_KEY", "")
    VYBE_AI_MODEL = os.environ.get("VYBE_AI_MODEL", "")
