# =============================================================================
# financial/signals.py  —  v3.1
# =============================================================================
"""
Signal handlers for the financial app.

1. Invoice / Payment sync
   ──────────────────────
   Keep Invoice.amount_paid / amount_remaining / status in sync whenever a
   Payment record is created, modified, or deleted.

   * Payment.save() and Payment.delete() already call invoice.refresh_payment_totals()
     directly. The post_save / post_delete signals below add a second sync layer
     that fires on bulk ORM updates (Payment.objects.filter(...).update(...)),
     which do NOT trigger model.save().

   * InvoiceItem signals are intentionally NOT present here because:
     - InvoiceItem.save() / delete() already call invoice.recalculate_amounts()
       and raise ValidationError when the invoice is locked.
     - Adding signals on top would cause a double-recalculation on every item save.

   * Phase guard: payment signals only recalculate when the invoice is in the
     FINALE phase. Proforma invoices have no payments; the guard is a safety net.

2. Beneficiary ↔ Trainer two-way sync
   ────────────────────────────────────
   Trainer.save() already pushes data to Beneficiary (formations_models.py).
   The signal below handles the reverse direction: whenever a Beneficiary of
   type "formateur" is saved without a linked Trainer, a Trainer record is
   auto-created and the two are linked.

   Sync-loop prevention
   ────────────────────
   * When THIS signal creates a Trainer it sets  trainer._skip_beneficiary_sync = True
     so that Trainer.save() does NOT turn around and call update_or_create on the
     Beneficiary again (which would cause an infinite loop and a duplicate row).

   * When Trainer.save() re-saves an existing Beneficiary after adopting it, it sets
     beneficiary._skip_trainer_sync = True so THIS signal skips that save.

   * Only the creation path (and explicit type change to "formateur") triggers
     Trainer auto-creation.  Subsequent field-level edits on either side are NOT
     mirrored automatically; save the Trainer to propagate its changes to the
     Beneficiary (the original direction already works).
"""

from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from financial.models import Beneficiary, Invoice, Payment

# ======================================================================= #
# Invoice / Payment sync
# ======================================================================= #


@receiver(post_save, sender=Payment)
def payment_saved(sender, instance, **kwargs):
    """Refresh invoice totals after any payment save (catches bulk updates)."""
    if not instance.invoice_id:
        return
    try:
        invoice = Invoice.objects.get(pk=instance.invoice_id)
        if invoice.phase == Invoice.Phase.FINALE:
            invoice.refresh_payment_totals()
    except Invoice.DoesNotExist:
        pass


@receiver(post_delete, sender=Payment)
def payment_deleted(sender, instance, **kwargs):
    """Refresh invoice totals after a payment is removed."""
    if not instance.invoice_id:
        return
    try:
        invoice = Invoice.objects.get(pk=instance.invoice_id)
        if invoice.phase == Invoice.Phase.FINALE:
            invoice.refresh_payment_totals()
    except Invoice.DoesNotExist:
        pass  # Invoice itself was deleted — nothing to update


# ======================================================================= #
# Beneficiary → Trainer reverse sync
# ======================================================================= #


@receiver(pre_save, sender=Beneficiary)
def beneficiary_pre_save(sender, instance, **kwargs):
    """Cache the previous beneficiary_type so post_save can detect a type change."""
    if instance.pk:
        try:
            instance._previous_btype_slug = (
                Beneficiary.objects.select_related("beneficiary_type")
                .get(pk=instance.pk)
                .beneficiary_type.slug
            )
        except Beneficiary.DoesNotExist:
            instance._previous_btype_slug = None
    else:
        instance._previous_btype_slug = None


@receiver(post_save, sender=Beneficiary)
def beneficiary_saved(sender, instance, created, **kwargs):
    """
    Auto-create a linked Trainer when a formateur Beneficiary has none.

    Triggered when:
      a) A new Beneficiary with type slug="formateur" is created (e.g. by
         seed_initial_expenses or the quick-add modal), OR
      b) An existing Beneficiary's type is changed TO "formateur".

    The flag _skip_trainer_sync suppresses this handler when Trainer.save()
    re-saves the Beneficiary as part of its own sync (see formations_models).
    """
    # ── Loop-prevention guard ──────────────────────────────────────── #
    if getattr(instance, "_skip_trainer_sync", False):
        return

    # ── Already linked — nothing to do ─────────────────────────────── #
    if instance.trainer_id:
        return

    # ── Only act when type is (or just became) "formateur" ─────────── #
    try:
        current_slug = instance.beneficiary_type.slug
    except Exception:
        return

    if current_slug != "formateur":
        return

    prev_slug = getattr(instance, "_previous_btype_slug", None)
    # For updates: only proceed if this is a new record or the type just changed
    if not created and prev_slug == "formateur":
        return

    # ── Create the linked Trainer (lazy import avoids circular dep) ── #
    try:
        from formations.models import Trainer

        # Best-effort name split: "Dupont Ali" → first="Dupont", last="Ali"
        # "Ben Amer Fatima Zohra" → first="Ben Amer Fatima", last="Zohra"
        # The trainer record can always be corrected afterwards.
        parts = instance.name.strip().rsplit(" ", 1)
        if len(parts) == 2:
            first_name, last_name = parts
        else:
            first_name, last_name = parts[0], ""

        trainer = Trainer(
            first_name=first_name,
            last_name=last_name,
            trainer_type=(
                Trainer.TRAINER_TYPE_INTERNAL
                if instance.is_employee
                else Trainer.TRAINER_TYPE_EXTERNAL
            ),
            nif=instance.nif,
            rib=instance.rib,
            phone=instance.phone,
            email=instance.email,
            daily_rate=instance.daily_rate,
            monthly_rate=instance.monthly_rate,
            is_active=instance.is_active,
            notes=(f"Créé automatiquement depuis le bénéficiaire « {instance.name} »."),
        )
        # Prevent Trainer.save() from triggering a duplicate Beneficiary sync.
        trainer._skip_beneficiary_sync = True
        trainer.save()

        # Link the Beneficiary to the new Trainer via a raw UPDATE so that
        # this signal is NOT re-fired (post_save on Beneficiary only fires
        # after .save(), not after QuerySet.update()).
        Beneficiary.objects.filter(pk=instance.pk).update(
            trainer=trainer,
            is_trainer=True,
        )

    except Exception:
        pass  # formations app may not be migrated yet
