# accounts/views.py

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render

from accounts.forms import (
    AdminPasswordResetForm,
    LoginForm,
    PasswordChangeForm,
    ProfileEditForm,
    UserCreateForm,
    UserEditForm,
)
from accounts.models import UserProfile


# ---------------------------------------------------------------------------
# Decorators / helpers
# ---------------------------------------------------------------------------


def admin_required(view_func):
    """Restrict access to admin-role users only."""

    @login_required
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, "profile") or not request.user.profile.is_admin:
            messages.error(request, "Accès réservé aux administrateurs.")
            return redirect("reporting:dashboard")
        return view_func(request, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def login_view(request):
    if request.user.is_authenticated:
        return redirect("reporting:dashboard")

    form = LoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )
        if user is not None:
            # Check profile active flag
            profile_active = True
            if hasattr(user, "profile") and not user.profile.is_active:
                profile_active = False

            if not user.is_active or not profile_active:
                messages.error(request, "Ce compte a été désactivé.")
            else:
                login(request, user)
                next_url = request.GET.get("next", "reporting:dashboard")
                return redirect(next_url)
        else:
            messages.error(request, "Nom d'utilisateur ou mot de passe incorrect.")

    return render(request, "accounts/login.html", {"form": form})


@login_required
def logout_view(request):
    if request.method == "POST":
        logout(request)
        messages.success(request, "Vous avez été déconnecté.")
        return redirect("accounts:login")
    # GET — show confirmation or just log out
    logout(request)
    return redirect("accounts:login")


@login_required
def change_password(request):
    form = PasswordChangeForm(request.POST or None, user=request.user)

    if request.method == "POST" and form.is_valid():
        form.save()
        # Re-authenticate so the session stays valid after password change
        from django.contrib.auth import update_session_auth_hash

        update_session_auth_hash(request, request.user)
        messages.success(request, "Mot de passe modifié avec succès.")
        return redirect("accounts:profile")

    return render(request, "accounts/change_password.html", {"form": form})


# ---------------------------------------------------------------------------
# User management (admin only)
# ---------------------------------------------------------------------------


@admin_required
def user_list(request):
    users = (
        User.objects.select_related("profile")
        .all()
        .order_by("last_name", "first_name", "username")
    )
    return render(request, "accounts/user_list.html", {"users": users})


@admin_required
def user_create(request):
    form = UserCreateForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(
            request,
            f"Compte « {user.username} » créé avec succès.",
        )
        return redirect("accounts:user_list")

    return render(request, "accounts/user_form.html", {"form": form, "action": "Créer"})


@admin_required
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)

    # Prevent admins from accidentally locking themselves out
    is_self = user == request.user

    form = UserEditForm(request.POST or None, instance=user)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Utilisateur mis à jour avec succès.")
        return redirect("accounts:user_list")

    return render(
        request,
        "accounts/user_form.html",
        {"form": form, "action": "Modifier", "edited_user": user, "is_self": is_self},
    )


@admin_required
def user_toggle_active(request, pk):
    if request.method != "POST":
        return redirect("accounts:user_list")

    user = get_object_or_404(User, pk=pk)

    if user == request.user:
        messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
        return redirect("accounts:user_list")

    profile, _ = UserProfile.objects.get_or_create(user=user)
    new_state = not profile.is_active
    profile.is_active = new_state
    profile.save(update_fields=["is_active"])

    # Also mirror on the auth User
    user.is_active = new_state
    user.save(update_fields=["is_active"])

    state_label = "activé" if new_state else "désactivé"
    messages.success(request, f"Compte « {user.username} » {state_label}.")
    return redirect("accounts:user_list")


@admin_required
def user_reset_password(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = AdminPasswordResetForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        user.set_password(form.cleaned_data["new_password1"])
        user.save()
        messages.success(
            request,
            f"Mot de passe de « {user.username} » réinitialisé avec succès.",
        )
        return redirect("accounts:user_list")

    return render(
        request,
        "accounts/user_reset_password.html",
        {"form": form, "edited_user": user},
    )


# ---------------------------------------------------------------------------
# Own profile
# ---------------------------------------------------------------------------


@login_required
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    return render(request, "accounts/profile.html", {"profile": profile})


@login_required
def profile_edit(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    form = ProfileEditForm(
        request.POST or None, request.FILES or None, instance=profile
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profil mis à jour avec succès.")
        return redirect("accounts:profile")

    return render(request, "accounts/profile_edit.html", {"form": form})
