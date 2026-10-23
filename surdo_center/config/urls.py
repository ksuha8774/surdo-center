from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from accounts.views import SystemLoginView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", SystemLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("dashboard.urls")),
    path("patients/", include("patients.urls")),
    path("appointments/", include("scheduling.urls")),
    path("visits/", include("medical.urls")),
    path("billing/", include("billing.urls")),
]
