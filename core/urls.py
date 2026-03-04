from django.urls import path

from core import views

urlpatterns = [
    path("personas/", views.personas_registro, name="personas_registro"),
]
