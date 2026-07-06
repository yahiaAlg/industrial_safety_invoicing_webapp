# ============================================================
# accounts/urls.py
# ============================================================

from django.urls import path
from accounts import views

app_name = "accounts"

urlpatterns = [
    # Auth
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("change-password/", views.change_password, name="change_password"),
    # User management (admin only)
    path("users/", views.user_list, name="user_list"),
    path("users/create/", views.user_create, name="user_create"),
    path("users/<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:pk>/toggle/", views.user_toggle_active, name="user_toggle_active"),
    path(
        "users/<int:pk>/reset-password/",
        views.user_reset_password,
        name="user_reset_password",
    ),
    # Profile (own user)
    path("profile/", views.profile_view, name="profile"),
    path("profile/edit/", views.profile_edit, name="profile_edit"),
]
