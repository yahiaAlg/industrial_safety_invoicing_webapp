"""
Accounts models — User Profile extension.
"""

from django.db import models
from django.contrib.auth.models import User

from core.base_models import TimeStampedModel


class UserProfile(TimeStampedModel):
    """
    Extended user profile with role-based access control.
    """

    ROLE_ADMIN = "admin"
    ROLE_RECEPTIONIST = "receptionist"

    ROLE_CHOICES = [
        (ROLE_ADMIN, "Administrateur"),
        (ROLE_RECEPTIONIST, "Réceptionniste"),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name="Utilisateur",
    )
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default=ROLE_RECEPTIONIST,
        verbose_name="Rôle",
    )
    phone = models.CharField(max_length=50, blank=True, verbose_name="Téléphone")
    # Soft-disable an account without deleting it
    is_active = models.BooleanField(default=True, verbose_name="Actif")
    # Optional avatar
    avatar = models.ImageField(upload_to="avatars/", blank=True, verbose_name="Avatar")
    # Preferred display language (future i18n)
    language = models.CharField(max_length=10, default="fr", verbose_name="Langue")

    class Meta:
        verbose_name = "Profil utilisateur"
        verbose_name_plural = "Profils utilisateurs"

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} — {self.get_role_display()}"

    # ------------------------------------------------------------------ #
    # Role helpers
    # ------------------------------------------------------------------ #

    @property
    def is_admin(self):
        """True if user holds the administrator role."""
        return self.role == self.ROLE_ADMIN

    @property
    def is_receptionist(self):
        """True if user holds the receptionist role."""
        return self.role == self.ROLE_RECEPTIONIST

    @property
    def full_name(self):
        """Return the Django auth full name, falling back to username."""
        return self.user.get_full_name() or self.user.username

    @property
    def last_login(self):
        """Proxy to the underlying auth user last-login datetime."""
        return self.user.last_login
