from django.urls import path

from . import views


app_name = "medical"
urlpatterns = [path("appointment/<int:appointment_pk>/", views.visit_edit, name="edit")]
