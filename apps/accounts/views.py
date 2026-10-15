from __future__ import annotations

import hashlib

from django.contrib.auth.views import LoginView, PasswordChangeView
from django.core.cache import cache
from django.urls import reverse_lazy

from .forms import SecureAuthenticationForm


class RateLimitedLoginView(LoginView):
    authentication_form = SecureAuthenticationForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True
    max_attempts = 5
    window_seconds = 15 * 60

    def _cache_key(self) -> str:
        username = self.request.POST.get("username", "").strip().casefold()
        remote_address = self.request.META.get("REMOTE_ADDR", "unknown")
        digest = hashlib.sha256(f"{username}|{remote_address}".encode()).hexdigest()
        return f"login-attempts:{digest}"

    def post(self, request, *args, **kwargs):
        key = self._cache_key()
        if int(cache.get(key, 0)) >= self.max_attempts:
            form = self.get_form()
            form.add_error(None, "Demasiados intentos. Intente nuevamente en 15 minutos.")
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        key = self._cache_key()
        attempts = int(cache.get(key, 0)) + 1
        cache.set(key, attempts, timeout=self.window_seconds)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._cache_key())
        return super().form_valid(form)


class SecurePasswordChangeView(PasswordChangeView):
    template_name = "registration/password_change_form.html"
    success_url = reverse_lazy("accounts:password_change_done")

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.user.must_change_password:
            self.request.user.must_change_password = False
            self.request.user.save(update_fields=["must_change_password"])
        return response
