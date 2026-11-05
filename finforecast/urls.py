from django.conf import settings
from django.contrib import admin
from django.urls import path

from apps.core import two_factor, views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("robots.txt", views.robots, name="robots"),
    path(f"{settings.ADMIN_URL}2fa/setup/", two_factor.two_factor_setup, name="two_factor_setup"),
    path(f"{settings.ADMIN_URL}2fa/verify/", two_factor.two_factor_verify, name="two_factor_verify"),
    path(settings.ADMIN_URL, admin.site.urls),
]
