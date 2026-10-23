from django.urls import path

from . import views


app_name = "billing"
urlpatterns = [path("services/", views.service_list, name="services")]
