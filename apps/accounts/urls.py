from django.contrib.auth.views import LogoutView, PasswordChangeDoneView
from django.urls import path

from .views import RateLimitedLoginView, SecurePasswordChangeView


app_name = "accounts"

urlpatterns = [
    path("iniciar-sesion/", RateLimitedLoginView.as_view(), name="login"),
    path("cerrar-sesion/", LogoutView.as_view(), name="logout"),
    path(
        "cambiar-clave/",
        SecurePasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "clave-actualizada/",
        PasswordChangeDoneView.as_view(template_name="registration/password_change_done.html"),
        name="password_change_done",
    ),
]
