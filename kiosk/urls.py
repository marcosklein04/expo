from django.urls import path

from kiosk import views

urlpatterns = [
    path("", views.start_screen, name="start"),
    path("kiosk/dni/", views.dni_screen, name="dni"),
    path("kiosk/vouchers/", views.vouchers_screen, name="vouchers"),
]
