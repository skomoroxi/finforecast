from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from apps.core import views
from apps.web import views as web_views

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("robots.txt", web_views.robots, name="robots"),
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("apps.web.urls")),
]
