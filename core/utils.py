# =============================================================================
# core/utils.py  —  Permission decorators & role helpers
# =============================================================================

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def get_user_role(user):
    """Return the role string for a user, or None if no profile exists."""
    try:
        return user.profile.role
    except AttributeError:
        return None


def is_admin(user):
    return get_user_role(user) == "admin"


def is_receptionist(user):
    return get_user_role(user) == "receptionist"


def admin_required(view_func):
    """
    Decorator: allows only authenticated users with the 'admin' role.
    Redirects unauthenticated users to login; raises 403 for non-admins.
    """

    @wraps(view_func)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapper


def login_and_active_required(view_func):
    """
    Decorator: requires login AND that the user's profile is marked active.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("accounts:login")
        try:
            if not request.user.profile.is_active:
                from django.contrib import messages
                from django.contrib.auth import logout

                logout(request)
                messages.error(request, "Votre compte a été désactivé.")
                return redirect("accounts:login")
        except AttributeError:
            pass
        return view_func(request, *args, **kwargs)

    return wrapper


def can_access_financial(user):
    """Only admins may access any financial data."""
    return is_admin(user)


def check_financial_access(request):
    """Call in views to raise 403 if user is not an admin."""
    if not is_admin(request.user):
        raise PermissionDenied
