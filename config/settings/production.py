import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import SECRET_KEY, env_bool


DEBUG = False

if SECRET_KEY.startswith("django-insecure-") or len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY debe ser secreta y tener al menos 50 caracteres.")
if not os.getenv("DJANGO_ALLOWED_HOSTS", "").strip():
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS es obligatorio en producción.")
if not os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").strip():
    raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS es obligatorio en producción.")
if not all(origin.startswith("https://") for origin in CSRF_TRUSTED_ORIGINS):  # noqa: F405
    raise ImproperlyConfigured("Los orígenes CSRF de producción deben usar HTTPS.")
if not os.getenv("DATABASE_URL", "").strip():
    raise ImproperlyConfigured("DATABASE_URL es obligatorio en producción.")
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":  # noqa: F405
    raise ImproperlyConfigured("Producción requiere PostgreSQL; SQLite no está permitido.")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_HSTS_SECONDS", "3600"))  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_HSTS_PRELOAD", False)
