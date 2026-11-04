from django.conf import settings
from django.contrib import admin
from django.urls import path

from apps.core import views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("robots.txt", views.robots, name="robots"),
    path(settings.ADMIN_URL, admin.site.urls),
]
