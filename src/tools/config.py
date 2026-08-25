from dotenv import load_dotenv
import os

load_dotenv()


def require_env(key: str) -> str:
    """Fail fast at startup if a required variable is missing."""
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {key}. "
            f"Check your .env file"
        )
    return value


def get_bool_env(key: str, default: str = "False") -> bool:
    return os.getenv(key, default).lower() in ("true", "1", "t")


# --- App ---
DEBUG = get_bool_env("DEBUG", "True")
SECRET_KEY = require_env("SECRET_KEY")

# --- Base de datos ---
DATABASE_URL = os.getenv("DATABASE_URL", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "bulletin_builder_db")

# --- Keycloak: verificación de tokens (login de usuarios) ---
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "aclimate")
KEYCLOAK_CLIENT_ID = require_env("KEYCLOAK_CLIENT_ID")
KEYCLOAK_CLIENT_SECRET = require_env("KEYCLOAK_CLIENT_SECRET")

# --- Frontend / links en notificaciones ---
DEFAULT_LOCALE = os.getenv("DEFAULT_LOCALE", "en")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

# --- SMTP / notificaciones por correo ---
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USERNAME)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Bulletin Builder")
SMTP_TLS = get_bool_env("SMTP_TLS", "True")
SMTP_SSL = get_bool_env("SMTP_SSL", "False")

# --- Gmail API (opcional) ---
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "smtp")  # "smtp" o "gmail_api"
GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN = os.getenv("GMAIL_REFRESH_TOKEN")