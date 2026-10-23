from .models import User


def role_context(request):
    user = request.user
    if not getattr(user, "is_authenticated", False):
        return {}
    return {
        "is_administrator": user.is_superuser or user.role == User.Role.ADMINISTRATOR,
        "is_doctor": user.is_superuser or user.role == User.Role.DOCTOR,
        "is_director": user.is_superuser or user.role == User.Role.DIRECTOR,
    }
