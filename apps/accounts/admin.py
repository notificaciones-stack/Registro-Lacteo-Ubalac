from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Operación UBALAC", {"fields": ("role", "must_change_password")}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Operación UBALAC", {"fields": ("role", "email", "must_change_password")}),
    )
    list_display = ("username", "email", "role", "is_staff", "is_active")
    list_filter = ("role", "is_staff", "is_active")

    def has_add_permission(self, request):
        return (request.user.is_superuser or request.user.role == User.Role.ADMIN) and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return (request.user.is_superuser or request.user.role == User.Role.ADMIN) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return (request.user.is_superuser or request.user.role == User.Role.ADMIN) and super().has_delete_permission(request, obj)
