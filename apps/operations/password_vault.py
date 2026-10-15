"""Limited administrator-facing recovery for newly provisioned driver credentials."""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _cipher():
    key = hashlib.sha256(("ubalac:driver-password:v1:" + settings.SECRET_KEY).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_driver_password(value):
    return _cipher().encrypt(value.encode()).decode()


def get_visible_driver_password(profile):
    if not profile or not profile.encrypted_login_password:
        return None
    try:
        value = _cipher().decrypt(profile.encrypted_login_password.encode()).decode()
    except (InvalidToken, ValueError, UnicodeDecodeError):
        return None
    # Changes made elsewhere invalidate the stored copy; never show a stale password.
    return value if profile.user.check_password(value) else None
