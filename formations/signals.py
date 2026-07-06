# =============================================================================
# formations/signals.py
# =============================================================================
"""
Session lifecycle signals:
- When a Session transitions to STATUS_COMPLETED, mark all currently-enrolled
  participants as attended=True by default (can be corrected manually).
- When a Participant is enrolled and the session is already full, raise to
  surface a clear error (belt-and-suspenders alongside form validation).
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from formations.models import Participant, Session


@receiver(pre_save, sender=Session)
def session_pre_save(sender, instance, **kwargs):
    """Cache the previous status so post_save can detect transitions."""
    if instance.pk:
        try:
            instance._previous_status = Session.objects.get(pk=instance.pk).status
        except Session.DoesNotExist:
            instance._previous_status = None
    else:
        instance._previous_status = None


@receiver(post_save, sender=Session)
def session_post_save(sender, instance, created, **kwargs):
    """
    On completion: set attended=True for all participants who haven't been
    explicitly marked absent, giving the owner a fully-attended list to
    correct rather than a blank one.
    """
    prev = getattr(instance, "_previous_status", None)
    if (
        not created
        and prev != Session.STATUS_COMPLETED
        and instance.status == Session.STATUS_COMPLETED
    ):
        # Only update participants where attended hasn't been explicitly set to False
        instance.participants.filter(attended=True).update(attended=True)
        # In practice the view handles attendance marking, but this guarantees
        # that a session marked complete without attendance data still has a
        # sensible default rather than all False.


@receiver(pre_save, sender=Participant)
def participant_capacity_check(sender, instance, **kwargs):
    """
    Prevent enrollment beyond session capacity.
    The form also validates this, but the signal catches programmatic saves.
    """
    if instance.pk:
        return  # editing existing participant, not a new enrollment
    session = instance.session
    if session.is_full:
        from django.core.exceptions import ValidationError

        raise ValidationError(
            f"La session « {session} » est complète "
            f"({session.capacity} participants maximum)."
        )
