from rest_framework.permissions import SAFE_METHODS, BasePermission


class RoleWritePermission(BasePermission):
    message = "El rol del usuario no permite modificar este recurso."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.must_change_password:
            self.message = "Debe cambiar la contraseña antes de usar la API."
            return False
        if request.method in SAFE_METHODS or request.user.is_superuser:
            return True
        allowed_roles = set(getattr(view, "write_roles", ()))
        return request.user.role in allowed_roles
