from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core import two_factor, views
from apps.web import views as web_views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("robots.txt", web_views.robots, name="robots"),
    path(f"{settings.ADMIN_URL}2fa/setup/", two_factor.two_factor_setup, name="two_factor_setup"),
    path(f"{settings.ADMIN_URL}2fa/verify/", two_factor.two_factor_verify, name="two_factor_verify"),
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("apps.web.urls")),
]
