import os

from django.core.exceptions import ImproperlyConfigured

from .base import *

DEBUG = False

if SECRET_KEY == "django-insecure-dev-change-me":
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set for production")

_allowed_hosts = os.getenv("DJANGO_ALLOWED_HOSTS", "").strip()
if _allowed_hosts:
    ALLOWED_HOSTS = [host.strip() for host in _allowed_hosts.split(",") if host.strip()]

_csrf_origins = os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").strip()
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in _csrf_origins.split(",") if origin.strip()]

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.getenv("DJANGO_SECURE_SSL_REDIRECT", "1") == "1"
SESSION_COOKIE_SECURE = os.getenv("DJANGO_SESSION_COOKIE_SECURE", "1") == "1"
CSRF_COOKIE_SECURE = os.getenv("DJANGO_CSRF_COOKIE_SECURE", "1") == "1"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# HSTS: заголовок отправляется только в ответах по HTTPS.
# Начните с небольшого значения и увеличьте до 31536000, когда HTTPS работает стабильно.
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "0") == "1"
SECURE_HSTS_PRELOAD = os.getenv("DJANGO_SECURE_HSTS_PRELOAD", "0") == "1"

# Логи пишутся в stderr: под systemd они попадают в journald
# (journalctl -u auto_service).
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "default"},
    },
    "root": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {
        "django": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"), "propagate": False},
    },
}
