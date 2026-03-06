# emoscreen/settings.py
from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------
# Load environment variables
# --------------------------------------------------

# Local development .env
LOCAL_ENV = BASE_DIR / ".env"

# Production secrets file
PROD_ENV = Path("/var/www/secrets/.env")

if PROD_ENV.exists():
    load_dotenv(PROD_ENV)
elif LOCAL_ENV.exists():
    load_dotenv(LOCAL_ENV)

# --------------------------------------------------
# Security
# --------------------------------------------------

SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-secret-key-change-me")

DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = os.getenv(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost"
).split(",")
# --------------------------------------------------
# Applications
# --------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "content",
    "paid",
    "social_django",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "emoscreen.urls"
WSGI_APPLICATION = "emoscreen.wsgi.application"

# --------------------------------------------------
# Templates
# --------------------------------------------------

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
            "social_django.context_processors.backends",
            "social_django.context_processors.login_redirect",
        ],
    },
}]

# --------------------------------------------------
# Database
# --------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST"),
        "PORT": os.getenv("DB_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

# --------------------------------------------------
# Static / Media
# --------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# --------------------------------------------------
# Report Templates
# --------------------------------------------------

DOCTOR_REPORT_TEMPLATE_PATH = BASE_DIR / "content" / "assets" / "DoctorReportBehaviorForm_unlocked.pdf"
PATIENT_REPORT_TEMPLATE_PATH = BASE_DIR / "content" / "assets" / "PatientReportBehaviorForm_unlocked.pdf"

# --------------------------------------------------
# Email / SendGrid
# --------------------------------------------------

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "noreply@example.com")

REPORT_FROM_NAME = os.getenv("REPORT_FROM_NAME", "EmoScreen")

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# --------------------------------------------------
# AiSensy
# --------------------------------------------------

AISENSY_API_KEY = os.getenv("AISENSY_API_KEY", "")

AISENSY_CAMPAIGN_NAME = os.getenv("AISENSY_CAMPAIGN_NAME", "")

# --------------------------------------------------
# Public Self Screen Defaults
# --------------------------------------------------

PUBLIC_DOCTOR_CODE = os.getenv("PUBLIC_DOCTOR_CODE", "PUBLIC0001")

PUBLIC_BRAND_NAME = os.getenv("PUBLIC_BRAND_NAME", "EmoScreen")

PUBLIC_PRO_EMAIL = os.getenv("PUBLIC_PRO_EMAIL", "products@example.com")

# --------------------------------------------------
# Google OAuth
# --------------------------------------------------

AUTHENTICATION_BACKENDS = (
    "social_core.backends.google.GoogleOAuth2",
    "django.contrib.auth.backends.ModelBackend",
)

LOGIN_URL = "/oauth/login/google-oauth2/"
LOGIN_REDIRECT_URL = "/auth/complete/"

SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = os.getenv("GOOGLE_OAUTH_CLIENT_ID")

SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET")

SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = ["email", "profile"]

SOCIAL_AUTH_REDIRECT_IS_HTTPS = os.getenv(
    "FORCE_HTTPS",
    "false"
).lower() == "true"

SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# --------------------------------------------------
# Internationalization
# --------------------------------------------------

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
