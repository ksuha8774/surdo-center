from django.urls import path

from . import views


app_name = "scheduling"
urlpatterns = [
    path("", views.appointment_list, name="list"),
    path("new/", views.appointment_create, name="create"),
    path("available-slots/", views.available_slots, name="available_slots"),
    path("schedule/", views.schedule_view, name="schedule"),
    path("<int:pk>/", views.appointment_detail, name="detail"),
    path("<int:pk>/cancel/", views.appointment_cancel, name="cancel"),
    path("<int:pk>/reschedule/", views.appointment_reschedule, name="reschedule"),
    path("<int:pk>/reschedule/available-slots/", views.reschedule_available_slots, name="reschedule_available_slots"),
]
