import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-vybe-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "instance", "vybe.db")
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
