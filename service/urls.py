from django.urls import path

from .views import service_card_view

app_name = "service"

urlpatterns = [
    path("", service_card_view, name="service_card"),
]
