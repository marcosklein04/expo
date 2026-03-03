from django.urls import path

from api import views

urlpatterns = [
    path("lookup", views.lookup, name="lookup"),
    path("redeem", views.redeem, name="redeem"),
    path("redeem-batch", views.redeem_batch, name="redeem_batch"),
    path("reports/daily", views.report_daily, name="report_daily"),
    path("healthz", views.healthz, name="healthz"),
]
