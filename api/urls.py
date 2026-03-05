from django.urls import path

from api import views

urlpatterns = [
    path("lookup", views.lookup, name="lookup"),
    path("redeem", views.redeem, name="redeem"),
    path("redeem-batch", views.redeem_batch, name="redeem_batch"),
    path("reprint-last", views.reprint_last, name="reprint_last"),
    path("reports/daily", views.report_daily, name="report_daily"),
    path("reports/redeems", views.report_redeems, name="report_redeems"),
    path("reports/redeems.csv", views.report_redeems_csv, name="report_redeems_csv"),
    path("healthz", views.healthz, name="healthz"),
]
