# =============================================================================
# accounts/admin.py
# =============================================================================

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from accounts.models import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = "Profil"
    fields = ["role", "phone", "avatar", "language", "is_active"]


class UserAdmin(BaseUserAdmin):
    inlines = [UserProfileInline]
    list_display = [
        "username",
        "get_full_name",
        "email",
        "get_role",
        "get_profile_active",
        "is_staff",
        "last_login",
    ]
    list_filter = ["profile__role", "profile__is_active", "is_staff"]
    search_fields = ["username", "first_name", "last_name", "email"]

    @admin.display(description="Rôle")
    def get_role(self, obj):
        return obj.profile.get_role_display() if hasattr(obj, "profile") else "—"

    @admin.display(description="Actif", boolean=True)
    def get_profile_active(self, obj):
        return obj.profile.is_active if hasattr(obj, "profile") else False


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
