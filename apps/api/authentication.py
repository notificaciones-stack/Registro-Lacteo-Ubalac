from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


class ExpiringTokenAuthentication(TokenAuthentication):
    """DRF token authentication with a short, server-enforced lifetime."""

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        expires_at = token.created + timedelta(hours=settings.API_TOKEN_TTL_HOURS)
        if expires_at <= timezone.now():
            token.delete()
            raise AuthenticationFailed("El token expiró. Inicie sesión nuevamente.")
        return user, token

    def authenticate(self, request):
        credentials = super().authenticate(request)
        if credentials:
            user, _ = credentials
            if user.role in {"DRIVER", "COLLECTOR"}:
                from apps.operations.assignments import driver_profile

                profile = driver_profile(user)
                if profile and profile.device_id and request.headers.get("X-Device-ID") != profile.device_id:
                    raise AuthenticationFailed("Equipo no autorizado. Envíe el ID registrado en X-Device-ID.")
        return credentials
