# =============================================================================
# accounts/signals.py
# =============================================================================
"""
Auto-create / sync UserProfile whenever a Django User is saved.
"""

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

from accounts.models import UserProfile


@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """Ensure every User always has a matching UserProfile."""
    if created:
        UserProfile.objects.get_or_create(
            user=instance,
            defaults={"role": UserProfile.ROLE_RECEPTIONIST},
        )
    else:
        # Sync is_active: if the auth User is deactivated, mirror it
        if hasattr(instance, "profile"):
            if not instance.is_active and instance.profile.is_active:
                instance.profile.is_active = False
                instance.profile.save(update_fields=["is_active"])
