import os
from datetime import timedelta
from pathlib import Path

# ── Load .env file automatically ───────────────────────────────
# python-dotenv reads KEY=VALUE pairs from .env into os.environ.
# If the package is missing the app still works (env vars must be
# set manually in that case).
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / '.env'
    load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass  # python-dotenv not installed — rely on shell environment


def _env_bool(name, default='False'):
    return os.environ.get(name, default).lower() in ('1', 'true', 'yes')


class Config:
    # ── Flask Core ────────────────────────────────────────────
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'change-me-in-production'
    # Safe default: debug stays off unless explicitly enabled (.env sets True for dev)
    DEBUG = _env_bool('DEBUG', 'False')

    # ── SQLAlchemy ────────────────────────────────────────────
    _db_default = 'sqlite:///' + str(
        Path(__file__).parent / 'insta_analytics.db'
    )
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or _db_default
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── JWT ───────────────────────────────────────────────────
    JWT_SECRET_KEY = os.environ.get('JWT_SECRET_KEY') or 'change-me-jwt-in-production'
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=2)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_TOKEN_LOCATION = ['headers', 'cookies']
    # Set JWT_COOKIE_SECURE=True in production (HTTPS) via env
    JWT_COOKIE_SECURE = _env_bool('JWT_COOKIE_SECURE', 'False')
    JWT_COOKIE_CSRF_PROTECT = _env_bool('JWT_COOKIE_CSRF_PROTECT', 'False')
    JWT_HEADER_NAME = 'Authorization'
    JWT_HEADER_TYPE = 'Bearer'

    # ── Redis / Celery ────────────────────────────────────────
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or REDIS_URL
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND') or REDIS_URL

    # ── Instagram Graph API ───────────────────────────────────
    INSTAGRAM_SIMULATE = _env_bool('INSTAGRAM_SIMULATE', 'True')
    INSTAGRAM_APP_ID = os.environ.get('INSTAGRAM_APP_ID', '')
    INSTAGRAM_APP_SECRET = os.environ.get('INSTAGRAM_APP_SECRET', '')
    INSTAGRAM_REDIRECT_URI = os.environ.get(
        'INSTAGRAM_REDIRECT_URI',
        'http://localhost:5001/api/auth/instagram/callback'
    )
    # Graph API version used for all graph.instagram.com requests. Pin this so
    # field/metric behaviour doesn't shift when Instagram rolls a new default.
    INSTAGRAM_API_VERSION = os.environ.get('INSTAGRAM_API_VERSION', 'v23.0')

    # ── RapidAPI (public Reels/media downloader) ──────────────
    # Used by the login-free "Downloader" page. The key stays server-side;
    # the frontend only talks to our own /api/downloader/* endpoints.
    RAPIDAPI_KEY = os.environ.get('RAPIDAPI_KEY', '')
    RAPIDAPI_HOST = os.environ.get('RAPIDAPI_HOST', 'instagram120.p.rapidapi.com')

    # ── Telegram bot (public reels/posts/stories downloader) ──
    # Token from @BotFather. The bot is a separate process:
    #   python telegram_bot.py
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')

    # ── Anthropic Claude (AI features) ────────────────────────
    # When ANTHROPIC_API_KEY is set, the AI Assistant uses the real Claude API.
    # Otherwise it falls back to built-in heuristics — the app works either way.
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
    ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-opus-4-8')

    # ── Token encryption ──────────────────────────────────────
    # urlsafe-base64 32-byte Fernet key. If unset, a key is derived from
    # SECRET_KEY. Set an explicit, rotated key in production.
    TOKEN_ENCRYPTION_KEY = os.environ.get('TOKEN_ENCRYPTION_KEY', '')

    # ── Mail (optional) ───────────────────────────────────────
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'localhost')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 1025))
    MAIL_USE_TLS = _env_bool('MAIL_USE_TLS', 'False')
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', '')
