from django.urls import path

from kiosk import views

urlpatterns = [
    path("", views.start_default, name="start"),
    path("kiosk/dni/", views.dni_default, name="dni"),
    path("kiosk/vouchers/", views.vouchers_default, name="vouchers"),
    path("totem/<slug:brand>/", views.start_screen, name="start_brand"),
    path("totem/<slug:brand>/dni/", views.dni_screen, name="dni_brand"),
    path("totem/<slug:brand>/vouchers/", views.vouchers_screen, name="vouchers_brand"),
]
