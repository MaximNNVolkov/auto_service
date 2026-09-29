from django.urls import path

from . import views

app_name = "service"

urlpatterns = [
    path("", views.service_card_view, name="service_card"),
    path("entries/", views.entry_list_view, name="entry_list"),
    path("entries/<int:pk>/edit/", views.entry_edit_view, name="entry_edit"),
    path("entries/<int:pk>/delete/", views.entry_delete_view, name="entry_delete"),
]
