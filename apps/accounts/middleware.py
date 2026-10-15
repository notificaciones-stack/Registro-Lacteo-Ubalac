from __future__ import annotations

import secrets

from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse


class SecurityHeadersMiddleware:
    """Adds a restrictive browser policy to the user-facing application."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = request.headers.get("X-Request-ID") or secrets.token_hex(12)
        response = self.get_response(request)
        response.headers.setdefault("X-Request-ID", request.request_id)
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        if not request.path.startswith("/admin/"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
                "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
            )
        return response


class NoStoreAuthenticatedMiddleware:
    """Prevents shared browsers and proxies from caching authenticated HTML."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        content_type = response.headers.get("Content-Type", "")
        if request.path.startswith("/api/") or (
            request.user.is_authenticated and "text/html" in content_type
        ):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Pragma"] = "no-cache"
        return response


class ForcePasswordChangeMiddleware:
    """Blocks normal use until a provisioned temporary password is replaced."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated and user.must_change_password:
            allowed_paths = {
                reverse("accounts:password_change"),
                reverse("accounts:password_change_done"),
                reverse("accounts:logout"),
            }
            if request.path not in allowed_paths and not request.path.startswith("/static/"):
                if request.path.startswith("/api/"):
                    return JsonResponse(
                        {"detail": "Debe cambiar la contraseña antes de continuar."},
                        status=403,
                    )
                return redirect("accounts:password_change")
        return self.get_response(request)
