from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(("api.urls", "api"), namespace="api")),
    path("tickets/", include(("tickets.urls", "tickets"), namespace="tickets")),
    path("", include(("kiosk.urls", "kiosk"), namespace="kiosk")),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
