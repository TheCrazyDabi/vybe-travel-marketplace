import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _normalize_db_uri(uri: str) -> str:
    """Resolve sqlite paths to an absolute file under <repo>/instance/.

    Flask-SQLAlchemy resolves *relative* sqlite paths against the app
    instance folder, so ``sqlite:///vybe.db`` and ``sqlite:///instance/vybe.db``
    would land in different places (the latter crashes with "unable to open
    database file" as instance/instance/). Normalizing here makes every
    reasonable .env value point at <repo>/instance/vybe.db.
    """
    if uri.startswith("sqlite:///") and not uri.startswith("sqlite:////"):
        path = uri.replace("sqlite:///", "", 1).replace("\\", "/")
        if path.startswith("instance/"):
            path = path[len("instance/"):]
        if not os.path.isabs(path):
            path = os.path.join(BASE_DIR, "instance", path)
        return "sqlite:///" + os.path.abspath(path)
    return uri


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-vybe-change-me")
    SQLALCHEMY_DATABASE_URI = _normalize_db_uri(
        os.environ.get(
            "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "vybe.db")
        )
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Uploads (verification docs / logos). Kept small for hackathon.
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "instance", "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB
    ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}

    # Optional AI (graceful fallback when unset)
    VYBE_AI_API_URL = os.environ.get("VYBE_AI_API_URL", "")
    VYBE_AI_API_KEY = os.environ.get("VYBE_AI_API_KEY", "")
    VYBE_AI_MODEL = os.environ.get("VYBE_AI_MODEL", "")
