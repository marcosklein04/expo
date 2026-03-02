from django.urls import path

from api import views

urlpatterns = [
    path("lookup", views.lookup, name="lookup"),
    path("redeem", views.redeem, name="redeem"),
]
