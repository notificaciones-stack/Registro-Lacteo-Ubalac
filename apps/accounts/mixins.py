from __future__ import annotations

from collections.abc import Iterable

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    allowed_roles: Iterable[str] = ()
    raise_exception = True

    def test_func(self):
        user = self.request.user
        return bool(user.is_superuser or user.role in set(self.allowed_roles))

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied("No tiene permisos para realizar esta acción.")
        return super().handle_no_permission()

