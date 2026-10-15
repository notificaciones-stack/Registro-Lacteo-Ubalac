from .base import *  # noqa: F403


DEBUG = True
ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, "testserver"]))  # noqa: F405
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_SSL_REDIRECT = False

# Local development and tests do not build the production manifest first.
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}
