from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path
from api import views as api_views

urlpatterns = [
    path("healthz", api_views.healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("registro/", include(("core.urls", "core"), namespace="core")),
    path("api/", include(("api.urls", "api"), namespace="api")),
    path("tickets/", include(("tickets.urls", "tickets"), namespace="tickets")),
    path("", include(("kiosk.urls", "kiosk"), namespace="kiosk")),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
