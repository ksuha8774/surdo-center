from django.shortcuts import render

from accounts.models import User
from accounts.permissions import role_required
from .models import Service


@role_required(User.Role.ADMINISTRATOR, User.Role.DIRECTOR)
def service_list(request):
    return render(request, "billing/service_list.html", {"services": Service.objects.all()})
