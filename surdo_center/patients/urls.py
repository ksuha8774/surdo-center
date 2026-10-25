from django.urls import path

from . import views


app_name = "patients"
urlpatterns = [
    path("", views.patient_list, name="list"),
    path("new/", views.patient_create, name="create"),
    path("<int:pk>/", views.patient_detail, name="detail"),
    path("duplicates/", views.patient_duplicates, name="duplicates"),
    path("<int:pk>/edit/", views.patient_edit, name="edit"),
    path("<int:pk>/archive/", views.patient_archive, name="archive"),
    path("<int:pk>/restore/", views.patient_restore, name="restore"),
]
