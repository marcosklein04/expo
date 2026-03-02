from django.urls import path

from tickets import views

urlpatterns = [
    path("<str:ticket_numero>/", views.print_ticket, name="print_ticket"),
]
