from django.urls import path

from . import views


app_name = "audiometry"
urlpatterns = [
    path("patient/<int:patient_pk>/new/", views.exam_create_for_patient, name="create_for_patient"),
    path("patient/<int:patient_pk>/compare/", views.exam_compare, name="compare"),
    path("visit/<int:visit_pk>/new/", views.exam_create_for_visit, name="create_for_visit"),
    path("<int:pk>/", views.exam_detail, name="detail"),
    path("<int:pk>/analyze/", views.exam_analyze, name="analyze"),
]
