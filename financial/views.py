# =============================================================================
# financial/views.py  —  v3.1
# Changes:
#   * invoice_create — pre-populates from ?session=pk / ?client=pk GET params
#     and redirects directly to item_add after creation.
#   * invoice_finalize — wrapped in transaction.atomic() to prevent reference
#     race conditions; mode_reglement save consolidated correctly.
#   * invoice_cancel_finalization — new view to revert an UNPAID finale back
#     to PROFORMA/DRAFT for admin recovery of erroneous finalization.
# =============================================================================

from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.utils import admin_required
from financial.forms import (
    BeneficiaryForm,
    BeneficiaryTypeForm,
    BonCommandeForm,
    CreditNoteForm,
    ExpenseCategoryForm,
    ExpenseFilterForm,
    ExpenseForm,
    FinalizeInvoiceForm,
    FinancialPeriodForm,
    InvoiceFilterForm,
    InvoiceItemForm,
    PaymentAccountForm,
    PaymentForm,
    ProformaCreateForm,
    ReportFilterForm,
)
from financial.models import (
    Beneficiary,
    BeneficiaryType,
    CreditNote,
    Expense,
    ExpenseCategory,
    FinancialPeriod,
    Invoice,
    InvoiceItem,
    Payment,
    PaymentAccount,
)
from financial.utils import (
    amount_to_words_fr,
    current_year_range,
    outstanding_invoices,
    project_margin,
    proformas_pending_bc,
    proformas_ready_to_finalize,
    resolve_date_range,
    revenue_by_month,
    revenue_summary,
    session_margin,
    top_clients_by_revenue,
)

# ─────────────────────────────────────────────────────────────────────────── #
# Invoices — list & detail
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def invoice_list(request):
    qs = Invoice.objects.select_related("client").order_by(
        "-invoice_date", "-proforma_reference"
    )
    form = InvoiceFilterForm(request.GET or None)

    if form.is_valid():
        q = form.cleaned_data.get("q")
        phase = form.cleaned_data.get("phase")
        status = form.cleaned_data.get("status")
        invoice_type = form.cleaned_data.get("invoice_type")
        date_from = form.cleaned_data.get("date_from")
        date_to = form.cleaned_data.get("date_to")
        client = form.cleaned_data.get("client")
        amount_min = form.cleaned_data.get("amount_min")
        amount_max = form.cleaned_data.get("amount_max")

        if q:
            qs = qs.filter(
                Q(proforma_reference__icontains=q)
                | Q(reference__icontains=q)
                | Q(client__name__icontains=q)
                | Q(items__description__icontains=q)
            ).distinct()
        if phase:
            qs = qs.filter(phase=phase)
        if status:
            qs = qs.filter(status=status)
        if invoice_type:
            qs = qs.filter(invoice_type=invoice_type)
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)
        if client:
            qs = qs.filter(client=client)
        if amount_min is not None:
            qs = qs.filter(amount_ttc__gte=amount_min)
        if amount_max is not None:
            qs = qs.filter(amount_ttc__lte=amount_max)

    # KPIs for the strip
    kpis = {
        "proformas_open": Invoice.objects.filter(phase=Invoice.Phase.PROFORMA).count(),
        "unpaid_count": Invoice.objects.filter(
            phase=Invoice.Phase.FINALE,
            status__in=[Invoice.Status.UNPAID, Invoice.Status.PARTIALLY_PAID],
        ).count(),
        "outstanding": Invoice.objects.filter(
            phase=Invoice.Phase.FINALE,
            status__in=[Invoice.Status.UNPAID, Invoice.Status.PARTIALLY_PAID],
        ).aggregate(t=Sum("amount_remaining"))["t"]
        or Decimal("0"),
        "pending_bc": Invoice.objects.filter(
            phase=Invoice.Phase.PROFORMA, bon_commande_number=""
        ).count(),
    }

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    # Build query string without the 'page' key for pagination links
    qp = request.GET.copy()
    qp.pop("page", None)
    return render(
        request,
        "financial/invoice_list.html",
        {
            "page_obj": page_obj,
            "filter_form": form,
            "kpis": kpis,
            "query_params": qp.urlencode(),
        },
    )


@admin_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(Invoice.objects.select_related("client"), pk=pk)
    items = invoice.items.all().order_by("order")
    payments = invoice.payments.all().order_by("-date")
    credit_notes = invoice.credit_notes.all().order_by("-date")

    from datetime import date

    payment_form = PaymentForm(
        initial={"amount": invoice.amount_remaining, "date": date.today()}
    )

    return render(
        request,
        "financial/invoice_detail.html",
        {
            "invoice": invoice,
            "items": items,
            "payments": payments,
            "credit_notes": credit_notes,
            "payment_form": payment_form,
            "bc_form": BonCommandeForm(instance=invoice),
            "item_form": InvoiceItemForm(),
        },
    )


# ─────────────────────────────────────────────────────────────────────────── #
# Invoices — Stage 1: create proforma
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def invoice_create(request):
    """
    Create a new proforma invoice (Stage 1).

    Supports GET params for guided workflow pre-population:
      ?session=<pk>  — pre-fills client, type=formation, links session
      ?client=<pk>   — pre-fills client only
    After creation, redirects straight to item_add for immediate line entry.
    """
    initial = {}
    source_session = None
    source_project = None

    # Pre-populate from session
    session_pk = request.GET.get("session")
    if session_pk:
        try:
            from formations.models import Session as FSession

            source_session = FSession.objects.select_related("client", "formation").get(
                pk=session_pk
            )
            initial["client"] = source_session.client_id
            initial["invoice_type"] = Invoice.InvoiceType.FORMATION
            initial["session"] = source_session.pk
            initial["tva_rate"] = Decimal("0.09")
        except Exception:
            pass

    # Pre-populate from client only
    client_pk = request.GET.get("client")
    if client_pk and not session_pk:
        initial["client"] = client_pk

    # Pre-populate from study project
    project_pk = request.GET.get("project")
    if project_pk:
        try:
            from etudes.models import StudyProject

            source_project = StudyProject.objects.select_related("client").get(
                pk=project_pk
            )
            initial["client"] = source_project.client_id
            initial["invoice_type"] = Invoice.InvoiceType.ETUDE
            initial["study_project"] = source_project.pk
            initial["tva_rate"] = Decimal("0.19")
        except Exception:
            pass

    form = ProformaCreateForm(request.POST or None, initial=initial)

    if request.method == "POST" and form.is_valid():
        invoice = form.save(commit=False)
        invoice.phase = Invoice.Phase.PROFORMA
        invoice.status = Invoice.Status.DRAFT
        invoice.save()
        messages.success(
            request,
            f"Proforma {invoice.proforma_reference} créée. Ajoutez les lignes ci-dessous.",
        )
        # Guided workflow: go straight to item entry
        return redirect("financial:item_add", invoice_pk=invoice.pk)

    return render(
        request,
        "financial/invoice_form.html",
        {
            "form": form,
            "action": "Nouvelle facture proforma",
            "source_session": source_session,
            "source_project": source_project,
        },
    )


@admin_required
def invoice_edit(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.is_locked:
        # Locked invoices: only notes/due_date/footer_text are editable
        pass  # Allow through — ProformaCreateForm handles field locking

    form = ProformaCreateForm(request.POST or None, instance=invoice)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Facture mise à jour.")
        return redirect("financial:invoice_detail", pk=pk)

    return render(
        request,
        "financial/invoice_form.html",
        {"form": form, "action": "Modifier", "invoice": invoice},
    )


# ─────────────────────────────────────────────────────────────────────────── #
# Invoices — Stage 2: record Bon de Commande
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def invoice_record_bc(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.phase != Invoice.Phase.PROFORMA:
        messages.error(request, "Le BC ne peut être enregistré que sur une proforma.")
        return redirect("financial:invoice_detail", pk=pk)

    form = BonCommandeForm(
        request.POST or None, request.FILES or None, instance=invoice
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            f"Bon de Commande N° {invoice.bon_commande_number} enregistré. "
            "La proforma est prête à être finalisée.",
        )
        return redirect("financial:invoice_detail", pk=pk)

    return render(
        request,
        "financial/invoice_record_bc.html",
        {"form": form, "invoice": invoice},
    )


# ─────────────────────────────────────────────────────────────────────────── #
# Invoices — Stage 3: finalize
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def invoice_finalize(request, pk):
    """
    GET  — Show the finalization confirmation page with blockers / preview.
    POST — Execute finalization atomically (reference generation + save in one
           transaction to prevent duplicate reference race conditions).
    """
    invoice = get_object_or_404(Invoice.objects.select_related("client"), pk=pk)

    if invoice.phase == Invoice.Phase.FINALE:
        messages.info(request, "Cette facture est déjà finalisée.")
        return redirect("financial:invoice_detail", pk=pk)

    # ── Compute blockers ─────────────────────────────────────────────────
    blockers = []
    if not invoice.bon_commande_number:
        blockers.append("Numéro de Bon de Commande manquant.")
    missing_client_fields = invoice.client.missing_fields_for_invoice()
    if missing_client_fields:
        blockers.append(
            f"Profil client incomplet — champs manquants : "
            f"{', '.join(missing_client_fields)}."
        )
    if invoice.amount_ttc <= 0:
        blockers.append("La facture ne contient aucune ligne de facturation.")

    year = timezone.now().year
    next_reference = Invoice._peek_final_reference(invoice.invoice_type, year)

    if request.method == "GET":
        initial_words = amount_to_words_fr(invoice.amount_ttc) if not blockers else ""
        form = FinalizeInvoiceForm(
            initial={
                "amount_in_words": initial_words,
                "due_date": invoice.due_date,
                "mode_reglement": invoice.mode_reglement or "",
            }
        )
        return render(
            request,
            "financial/invoice_finalize.html",
            {
                "invoice": invoice,
                "form": form,
                "blockers": blockers,
                "next_reference": next_reference,
            },
        )

    # ── POST ─────────────────────────────────────────────────────────────
    if blockers:
        for b in blockers:
            messages.error(request, b)
        return redirect("financial:invoice_finalize", pk=pk)

    form = FinalizeInvoiceForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "financial/invoice_finalize.html",
            {
                "invoice": invoice,
                "form": form,
                "blockers": blockers,
                "next_reference": next_reference,
            },
        )

    amount_in_words = form.cleaned_data.get("amount_in_words") or amount_to_words_fr(
        invoice.amount_ttc
    )
    due_date = form.cleaned_data.get("due_date")
    mode_reglement = form.cleaned_data.get("mode_reglement", "")

    try:
        with transaction.atomic():
            # Set mode_reglement before finalize() so it's included in the save
            invoice.mode_reglement = mode_reglement
            invoice.finalize(amount_in_words=amount_in_words)
            # Apply due_date in the same transaction (only update those fields)
            if due_date:
                Invoice.objects.filter(pk=invoice.pk).update(due_date=due_date)
                invoice.due_date = due_date

        messages.success(
            request,
            f"Facture {invoice.reference} finalisée avec succès. "
            "Le paiement est maintenant activé.",
        )
    except ValidationError as exc:
        for msg in exc.messages:
            messages.error(request, msg)
        return redirect("financial:invoice_finalize", pk=pk)

    return redirect("financial:invoice_detail", pk=pk)


# ─────────────────────────────────────────────────────────────────────────── #
# Invoices — cancel finalization (admin recovery)
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
@require_POST
def invoice_cancel_finalization(request, pk):
    """
    Revert an UNPAID finalized invoice back to PROFORMA/DRAFT.
    Used to recover from erroneous or incomplete finalization.

    Conditions:
      - Invoice must be in FINALE phase
      - Status must be UNPAID (no partial payment)
      - No confirmed payments may exist
    """
    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.phase != Invoice.Phase.FINALE:
        messages.error(request, "Cette facture n'est pas finalisée.")
        return redirect("financial:invoice_detail", pk=pk)

    if invoice.status != Invoice.Status.UNPAID:
        messages.error(
            request,
            "Seule une facture impayée (sans paiements) peut être dé-finalisée.",
        )
        return redirect("financial:invoice_detail", pk=pk)

    if invoice.payments.filter(status=Payment.Status.CONFIRMED).exists():
        messages.error(
            request,
            "Impossible : des paiements confirmés existent sur cette facture.",
        )
        return redirect("financial:invoice_detail", pk=pk)

    with transaction.atomic():
        # Decrement the sequence counter only if this invoice holds the last number
        # (i.e. no newer finale invoice was issued after it).
        if invoice.reference:
            from financial.models import InvoiceSequence

            try:
                seq = InvoiceSequence.objects.select_for_update().get(
                    invoice_type=invoice.invoice_type,
                    year=(
                        invoice.finalized_at.year
                        if invoice.finalized_at
                        else timezone.now().year
                    ),
                    phase=InvoiceSequence.Phase.FINALE,
                )
                # Extract the number from the reference (e.g. "F-017-2026" → 17)
                ref_number = int(invoice.reference.split("-")[-2])
                if seq.last_number == ref_number:
                    seq.last_number -= 1
                    seq.save(update_fields=["last_number"])
            except (
                InvoiceSequence.DoesNotExist,
                ValueError,
                IndexError,
                AttributeError,
            ):
                pass  # Can't safely decrement — leave sequence as-is

        invoice.phase = Invoice.Phase.PROFORMA
        invoice.status = Invoice.Status.DRAFT
        invoice.reference = None
        invoice.finalized_at = None
        invoice.amount_remaining = invoice.amount_ttc
        invoice.amount_paid = Decimal("0.00")
        # Clear client snapshots so they are re-taken on next finalization
        invoice.client_name_snapshot = ""
        invoice.client_address_snapshot = ""
        invoice.client_type_snapshot = ""
        invoice.client_nif_snapshot = ""
        invoice.client_nis_snapshot = ""
        invoice.client_rc_snapshot = ""
        invoice.client_ai_snapshot = ""
        invoice.client_nin_snapshot = ""
        invoice.client_rib_snapshot = ""
        invoice.client_tin_snapshot = ""
        invoice.save()
        # Remove the proforma snapshot so it gets re-created on next finalization
        from financial.models import ProformaSnapshot

        ProformaSnapshot.objects.filter(invoice=invoice).delete()

    messages.success(
        request,
        f"Finalisation annulée. {invoice.proforma_reference} est revenu en brouillon — "
        "vous pouvez le finaliser à nouveau.",
    )
    return redirect("financial:invoice_detail", pk=pk)


# ─────────────────────────────────────────────────────────────────────────── #
# Invoices — void / delete / mark-sent
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
@require_POST
def invoice_void(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    reason = request.POST.get("reason", "").strip()
    try:
        invoice.void(reason=reason)
        messages.success(
            request,
            f"Facture {invoice.reference} annulée. "
            "Le numéro est conservé dans la séquence.",
        )
    except ValidationError as exc:
        for msg in exc.messages:
            messages.error(request, msg)
    return redirect("financial:invoice_detail", pk=pk)


@admin_required
@require_POST
def invoice_delete(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)

    if invoice.phase == Invoice.Phase.FINALE:
        messages.error(
            request,
            "Une facture finalisée ne peut pas être supprimée — utilisez l'annulation.",
        )
        return redirect("financial:invoice_detail", pk=pk)

    if invoice.payments.exists():
        messages.error(
            request, "Impossible de supprimer une facture ayant des paiements."
        )
        return redirect("financial:invoice_detail", pk=pk)

    ref = invoice.proforma_reference
    invoice.delete()
    messages.success(request, f"Proforma {ref} supprimée définitivement.")
    return redirect("financial:invoice_list")


@admin_required
@require_POST
def invoice_mark_sent(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)

    if (
        invoice.phase != Invoice.Phase.PROFORMA
        or invoice.status != Invoice.Status.DRAFT
    ):
        messages.error(
            request,
            "Seules les proformas en brouillon peuvent être marquées comme envoyées.",
        )
        return redirect("financial:invoice_detail", pk=pk)

    invoice.status = Invoice.Status.SENT
    invoice.save(update_fields=["status"])
    messages.success(
        request, f"{invoice.proforma_reference} marquée comme envoyée au client."
    )
    return redirect("financial:invoice_detail", pk=pk)


# ─────────────────────────────────────────────────────────────────────────── #
# Invoices — print
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def invoice_print(request, pk):
    """
    Render the printable invoice.
    ?proforma=1  — on a finalized invoice, renders the frozen proforma snapshot
                   (original amounts, validity date, no payment history).
                   On a proforma, renders the live proforma template.
    """
    invoice = get_object_or_404(Invoice.objects.select_related("client"), pk=pk)
    items = invoice.items.all().order_by("order")

    from core.models import BureauEtudeInfo, FormationInfo, InstituteInfo

    institute = InstituteInfo.get_instance()
    if invoice.invoice_type == Invoice.InvoiceType.FORMATION:
        business_line = FormationInfo.get_instance()
    else:
        business_line = BureauEtudeInfo.get_instance()

    force_proforma = request.GET.get("proforma") == "1"
    profile = getattr(request.user, "profile", None)
    user_role = getattr(profile, "role", None) if profile else None

    base_ctx = {
        "invoice": invoice,
        "items": items,
        "institute": institute,
        "business_info": business_line,
        "print_user_is_admin": user_role == "admin",
        "print_user_full_name": request.user.get_full_name() or request.user.username,
        "print_user_role": user_role or "",
    }

    # Finalized invoice + ?proforma=1 → serve the frozen snapshot
    if force_proforma and invoice.phase == Invoice.Phase.FINALE:
        from financial.models import ProformaSnapshot

        snap = ProformaSnapshot.objects.filter(invoice=invoice).first()
        return render(
            request,
            "financial/invoice_print_proforma_snapshot.html",
            {**base_ctx, "snap": snap},
        )

    if invoice.phase == Invoice.Phase.PROFORMA:
        template = "financial/invoice_print.html"
    else:
        template = "financial/invoice_print_finale.html"

    return render(request, template, base_ctx)


# ─────────────────────────────────────────────────────────────────────────── #
# Invoice line items
# ─────────────────────────────────────────────────────────────────────────── #


def _get_source_list(invoice):
    if invoice.invoice_type == Invoice.InvoiceType.FORMATION:
        from formations.models import Formation

        return Formation.objects.filter(is_active=True).order_by("title")
    else:
        from etudes.models import StudyProject

        return (
            StudyProject.objects.filter(
                status__in=[
                    StudyProject.STATUS_IN_PROGRESS,
                    StudyProject.STATUS_COMPLETED,
                ]
            )
            .select_related("client")
            .order_by("title")
        )


@admin_required
def item_add(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)

    if invoice.is_locked:
        messages.error(
            request, "Impossible d'ajouter des lignes à une facture finalisée."
        )
        return redirect("financial:invoice_detail", pk=invoice_pk)

    form = InvoiceItemForm(request.POST or None, invoice=invoice)

    if request.method == "POST" and form.is_valid():
        item = form.save(commit=False)
        item.invoice = invoice
        try:
            item.save()
            messages.success(request, "Ligne ajoutée.")
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
        return redirect("financial:invoice_detail", pk=invoice_pk)

    return render(
        request,
        "financial/invoice_item_form.html",
        {
            "form": form,
            "invoice": invoice,
            "action": "Ajouter une ligne",
            "source_list": _get_source_list(invoice),
        },
    )


@admin_required
def item_edit(request, invoice_pk, pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    item = get_object_or_404(InvoiceItem, pk=pk, invoice=invoice)

    if invoice.is_locked:
        messages.error(
            request, "Impossible de modifier les lignes d'une facture finalisée."
        )
        return redirect("financial:invoice_detail", pk=invoice_pk)

    form = InvoiceItemForm(request.POST or None, instance=item)

    if request.method == "POST" and form.is_valid():
        try:
            form.save()
            messages.success(request, "Ligne mise à jour.")
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
        return redirect("financial:invoice_detail", pk=invoice_pk)

    return render(
        request,
        "financial/invoice_item_form.html",
        {
            "form": form,
            "invoice": invoice,
            "item": item,
            "action": "Modifier la ligne",
            "source_list": _get_source_list(invoice),
        },
    )


@admin_required
@require_POST
def item_delete(request, invoice_pk, pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    item = get_object_or_404(InvoiceItem, pk=pk, invoice=invoice)

    if invoice.is_locked:
        messages.error(
            request, "Impossible de supprimer les lignes d'une facture finalisée."
        )
        return redirect("financial:invoice_detail", pk=invoice_pk)

    try:
        item.delete()
        messages.success(request, "Ligne supprimée.")
    except ValidationError as exc:
        for msg in exc.messages:
            messages.error(request, msg)

    return redirect("financial:invoice_detail", pk=invoice_pk)


# ─────────────────────────────────────────────────────────────────────────── #
# Payments
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def payment_add(request, invoice_pk, pk=None):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)

    if not invoice.is_payable and pk is None:
        messages.error(request, _payment_blocked_reason(invoice))
        return redirect("financial:invoice_detail", pk=invoice_pk)

    instance = get_object_or_404(Payment, pk=pk, invoice=invoice) if pk else None
    if instance:
        initial = {}
    else:
        date_str = invoice.invoice_date.strftime("%Y%m%d")
        prefix = f"REF-{date_str}-"
        last = (
            Payment.objects.filter(reference__startswith=prefix)
            .order_by("reference")
            .values_list("reference", flat=True)
            .last()
        )
        if last:
            try:
                seq = int(last.split("-")[-1]) + 1
            except (ValueError, IndexError):
                seq = 1
        else:
            seq = 1
        initial = {
            "amount": invoice.amount_remaining,
            "reference": f"{prefix}{seq:04d}",
        }
    form = PaymentForm(request.POST or None, instance=instance, initial=initial)

    if request.method == "POST" and form.is_valid():
        payment = form.save(commit=False)
        payment.invoice = invoice
        try:
            payment.full_clean()
            payment.save()
            action = "mis à jour" if pk else "enregistré"
            messages.success(request, f"Paiement {action}.")
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
        return redirect("financial:invoice_detail", pk=invoice_pk)

    action = "Modifier le paiement" if pk else "Enregistrer un paiement"
    return render(
        request,
        "financial/payment_form.html",
        {
            "form": form,
            "invoice": invoice,
            "action": action,
            "next_ref": initial.get("reference", ""),
        },
    )


@admin_required
@require_POST
def payment_delete(request, invoice_pk, pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    payment = get_object_or_404(Payment, pk=pk, invoice=invoice)
    payment.delete()
    messages.success(request, "Paiement supprimé.")
    return redirect("financial:invoice_detail", pk=invoice_pk)


@admin_required
@require_POST
def payment_confirm(request, invoice_pk, pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    payment = get_object_or_404(Payment, pk=pk, invoice=invoice)
    payment.status = Payment.Status.CONFIRMED
    payment.save(update_fields=["status"])
    invoice.refresh_payment_totals()
    messages.success(request, "Paiement confirmé.")
    return redirect("financial:invoice_detail", pk=invoice_pk)


@admin_required
@require_POST
def payment_reverse(request, invoice_pk, pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)
    payment = get_object_or_404(Payment, pk=pk, invoice=invoice)
    payment.status = Payment.Status.REVERSED
    payment.save(update_fields=["status"])
    invoice.refresh_payment_totals()
    messages.success(request, "Paiement annulé / retourné.")
    return redirect("financial:invoice_detail", pk=invoice_pk)


def _payment_blocked_reason(invoice: Invoice) -> str:
    if invoice.phase == Invoice.Phase.PROFORMA:
        return (
            "Impossible d'enregistrer un paiement sur une proforma. Finalisez d'abord."
        )
    if invoice.status == Invoice.Status.PAID:
        return "Cette facture est déjà intégralement payée."
    if invoice.status == Invoice.Status.VOIDED:
        return "Cette facture est annulée."
    if invoice.status == Invoice.Status.CREDIT_NOTE:
        return "Un avoir a été émis sur cette facture."
    return "Cette facture n'est pas en attente de paiement."


# ─────────────────────────────────────────────────────────────────────────── #
# Credit notes
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def credit_note_list(request):
    credit_notes = CreditNote.objects.select_related(
        "original_invoice", "original_invoice__client"
    ).order_by("-date")
    paginator = Paginator(credit_notes, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(request, "financial/credit_note_list.html", {"page_obj": page_obj})


@admin_required
def credit_note_create(request, invoice_pk):
    invoice = get_object_or_404(Invoice, pk=invoice_pk)

    if invoice.phase != Invoice.Phase.FINALE:
        messages.error(
            request, "Un avoir ne peut être émis que sur une facture finalisée."
        )
        return redirect("financial:invoice_detail", pk=invoice_pk)

    if invoice.status == Invoice.Status.VOIDED:
        messages.error(request, "Cette facture est déjà annulée.")
        return redirect("financial:invoice_detail", pk=invoice_pk)

    form = CreditNoteForm(request.POST or None)
    if not request.POST:
        form.fields["tva_rate"].initial = invoice.tva_rate

    if request.method == "POST" and form.is_valid():
        cn = form.save(commit=False)
        cn.original_invoice = invoice
        cn.save()
        messages.success(
            request, f"Avoir {cn.reference} émis sur la facture {invoice.reference}."
        )
        return redirect("financial:credit_note_detail", pk=cn.pk)

    return render(
        request, "financial/credit_note_form.html", {"form": form, "invoice": invoice}
    )


@admin_required
def credit_note_detail(request, pk):
    cn = get_object_or_404(
        CreditNote.objects.select_related(
            "original_invoice", "original_invoice__client"
        ),
        pk=pk,
    )
    return render(request, "financial/credit_note_detail.html", {"cn": cn})


@admin_required
def credit_note_print(request, pk):
    cn = get_object_or_404(
        CreditNote.objects.select_related(
            "original_invoice", "original_invoice__client"
        ),
        pk=pk,
    )
    from core.models import BureauEtudeInfo, FormationInfo, InstituteInfo

    institute = InstituteInfo.get_instance()
    inv = cn.original_invoice
    business_line = (
        FormationInfo.get_instance()
        if inv.invoice_type == Invoice.InvoiceType.FORMATION
        else BureauEtudeInfo.get_instance()
    )
    return render(
        request,
        "financial/credit_note_print.html",
        {"cn": cn, "institute": institute, "business_line": business_line},
    )


# ─────────────────────────────────────────────────────────────────────────── #
# Expenses
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def expense_list(request):
    from django.utils.timezone import now

    qs = Expense.objects.select_related(
        "category",
        "allocated_to_session",
        "allocated_to_project",
        "beneficiary",
        "beneficiary__beneficiary_type",
        "payment_account",
    ).order_by("-date")
    form = ExpenseFilterForm(request.GET or None)

    date_from = date_to = None
    payment_date_from = payment_date_to = None
    g50_month = None
    fiscal_year = None
    quarter = None

    if form.is_valid():
        q = form.cleaned_data.get("q")
        category = form.cleaned_data.get("category")
        approval_status = form.cleaned_data.get("approval_status")
        date_from = form.cleaned_data.get("date_from")
        date_to = form.cleaned_data.get("date_to")
        allocation = form.cleaned_data.get("allocation")
        missing_receipt = form.cleaned_data.get("missing_receipt")
        beneficiary = form.cleaned_data.get("beneficiary")
        beneficiary_type = form.cleaned_data.get("beneficiary_type")
        has_irg = form.cleaned_data.get("has_irg")
        g50_month = form.cleaned_data.get("g50_month")
        trainer_payment_mode = form.cleaned_data.get("trainer_payment_mode")
        fiscal_year = form.cleaned_data.get("fiscal_year")
        quarter = form.cleaned_data.get("quarter")
        payment_date_from = form.cleaned_data.get("payment_date_from")
        payment_date_to = form.cleaned_data.get("payment_date_to")
        amount_min = form.cleaned_data.get("amount_min")
        amount_max = form.cleaned_data.get("amount_max")

        if q:
            qs = qs.filter(
                Q(description__icontains=q)
                | Q(beneficiary__name__icontains=q)
                | Q(supplier__icontains=q)
            )
        if category:
            qs = qs.filter(category=category)
        if approval_status:
            qs = qs.filter(approval_status=approval_status)
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        if allocation == "session":
            qs = qs.filter(allocated_to_session__isnull=False)
        elif allocation == "project":
            qs = qs.filter(allocated_to_project__isnull=False)
        elif allocation == "overhead":
            qs = qs.filter(is_overhead=True)
        if missing_receipt:
            qs = qs.filter(receipt="", receipt_missing=False)
        if beneficiary:
            qs = qs.filter(beneficiary=beneficiary)
        if beneficiary_type:
            qs = qs.filter(beneficiary__beneficiary_type=beneficiary_type)
        if has_irg == "yes":
            qs = qs.filter(irg_rate__gt=0)
        elif has_irg == "no":
            qs = qs.filter(irg_rate=0)
        if fiscal_year:
            qs = qs.filter(date__year=fiscal_year)
        if g50_month:
            qs = qs.filter(g50_month=g50_month)
        if trainer_payment_mode:
            qs = qs.filter(trainer_payment_mode=trainer_payment_mode)
        if payment_date_from:
            qs = qs.filter(payment_date__gte=payment_date_from)
        if payment_date_to:
            qs = qs.filter(payment_date__lte=payment_date_to)
        if amount_min is not None:
            qs = qs.filter(amount__gte=amount_min)
        if amount_max is not None:
            qs = qs.filter(amount__lte=amount_max)
        if quarter:
            year, q_num = int(quarter[:4]), int(quarter[5])
            month_start = (q_num - 1) * 3 + 1
            from datetime import date as _date

            qs = qs.filter(
                date__gte=_date(year, month_start, 1),
                date__lt=(
                    _date(year, month_start + 3, 1)
                    if month_start <= 9
                    else _date(year + 1, 1, 1)
                ),
            )

    today = now().date()
    first_of_month = today.replace(day=1)
    first_of_year = today.replace(month=1, day=1)
    pending_qs = Expense.objects.filter(approval_status=Expense.ApprovalStatus.PENDING)

    # ── Period KPI: approved total for whichever date filter(s) are active ── #
    period_qs = Expense.objects.filter(approval_status=Expense.ApprovalStatus.APPROVED)
    period_active = bool(
        date_from
        or date_to
        or payment_date_from
        or payment_date_to
        or g50_month
        or fiscal_year
        or quarter
    )
    if date_from:
        period_qs = period_qs.filter(date__gte=date_from)
    if date_to:
        period_qs = period_qs.filter(date__lte=date_to)
    if payment_date_from:
        period_qs = period_qs.filter(payment_date__gte=payment_date_from)
    if payment_date_to:
        period_qs = period_qs.filter(payment_date__lte=payment_date_to)
    if g50_month:
        period_qs = period_qs.filter(g50_month=g50_month)
    if fiscal_year:
        period_qs = period_qs.filter(date__year=fiscal_year)
    if quarter:
        year, q_num = int(quarter[:4]), int(quarter[5])
        month_start = (q_num - 1) * 3 + 1
        from datetime import date as _date

        period_qs = period_qs.filter(
            date__gte=_date(year, month_start, 1),
            date__lt=(
                _date(year, month_start + 3, 1)
                if month_start <= 9
                else _date(year + 1, 1, 1)
            ),
        )
    period_total = period_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0")

    kpis = {
        "pending_count": pending_qs.count(),
        "pending_amount": pending_qs.aggregate(s=Sum("amount"))["s"] or Decimal("0"),
        "approved_month": Expense.objects.filter(
            approval_status=Expense.ApprovalStatus.APPROVED,
            date__gte=first_of_month,
        ).aggregate(s=Sum("amount"))["s"]
        or Decimal("0"),
        "missing_receipt_count": Expense.objects.filter(
            receipt="", receipt_missing=False
        ).count(),
        "total_year": Expense.objects.filter(
            date__gte=first_of_year,
            approval_status=Expense.ApprovalStatus.APPROVED,
        ).aggregate(s=Sum("amount"))["s"]
        or Decimal("0"),
        "period_total": period_total,
        "period_active": period_active,
    }

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    # Build query string without the 'page' key for pagination links (Django 4.2 compat)
    qp = request.GET.copy()
    qp.pop("page", None)
    return render(
        request,
        "financial/expense_list.html",
        {
            "page_obj": page_obj,
            "filter_form": form,
            "kpis": kpis,
            "query_params": qp.urlencode(),
        },
    )


@admin_required
def expense_detail(request, pk):
    expense = get_object_or_404(
        Expense.objects.select_related(
            "category",
            "allocated_to_session",
            "allocated_to_project",
            "beneficiary",
            "beneficiary__beneficiary_type",
            "payment_account",
        ),
        pk=pk,
    )
    return render(request, "financial/expense_detail.html", {"expense": expense})


def _expense_form_context(form, expense=None, action=""):
    """Build extra context for expense create/edit (modal forms, beneficiary types)."""
    from financial.forms import BeneficiaryForm, BeneficiaryTypeForm, PaymentAccountForm

    return {
        "form": form,
        "expense": expense,
        "action": action,
        "beneficiary_form": BeneficiaryForm(),
        "beneficiary_type_form": BeneficiaryTypeForm(),
        "payment_account_form": PaymentAccountForm(),
        "beneficiary_types": BeneficiaryType.objects.filter(is_active=True).order_by(
            "name"
        ),
    }


@admin_required
def expense_create(request):
    form = ExpenseForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        expense = form.save(commit=False)
        try:
            expense.full_clean()
            expense.save()
            messages.success(request, "Dépense enregistrée.")
            return redirect("financial:expense_detail", pk=expense.pk)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)

    return render(
        request,
        "financial/expense_form.html",
        _expense_form_context(form, action="Nouvelle dépense"),
    )


@admin_required
def expense_edit(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    form = ExpenseForm(request.POST or None, request.FILES or None, instance=expense)

    if request.method == "POST" and form.is_valid():
        try:
            updated = form.save(commit=False)
            updated.full_clean()
            updated.save()
            messages.success(request, "Dépense mise à jour.")
            return redirect("financial:expense_detail", pk=expense.pk)
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)

    return render(
        request,
        "financial/expense_form.html",
        _expense_form_context(form, expense=expense, action="Modifier la dépense"),
    )


@admin_required
@require_POST
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    expense.delete()
    messages.success(request, "Dépense supprimée.")
    return redirect("financial:expense_list")


@admin_required
@require_POST
def expense_approve(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    expense.approval_status = Expense.ApprovalStatus.APPROVED
    expense.save(update_fields=["approval_status"])
    messages.success(request, "Dépense approuvée.")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER", "")
    return (
        redirect(next_url) if next_url else redirect("financial:expense_detail", pk=pk)
    )


@admin_required
@require_POST
def expense_reject(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    reason = request.POST.get("reason", "").strip()
    expense.approval_status = Expense.ApprovalStatus.REJECTED
    if reason:
        expense.approval_notes = reason
    expense.save(update_fields=["approval_status", "approval_notes"])
    messages.success(request, "Dépense refusée.")
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER", "")
    return (
        redirect(next_url) if next_url else redirect("financial:expense_detail", pk=pk)
    )


@admin_required
def expense_category_list(request):
    from django.db.models import Count
    from django.utils.timezone import now

    today = now().date()
    first_of_month = today.replace(day=1)
    categories = (
        ExpenseCategory.objects.all()
        .order_by("name")
        .annotate(
            expense_count_month=Sum(
                "expenses__id",
                filter=Q(expenses__date__gte=first_of_month),
                distinct=True,
            ),
            expense_total_month=Sum(
                "expenses__amount",
                filter=Q(expenses__date__gte=first_of_month),
            ),
        )
    )
    return render(
        request, "financial/expense_category_list.html", {"categories": categories}
    )


@admin_required
def expense_category_create(request):
    form = ExpenseCategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Catégorie créée.")
        return redirect("financial:expense_category_list")
    return render(
        request,
        "financial/expense_category_form.html",
        {"form": form, "action": "Nouvelle catégorie"},
    )


@admin_required
def expense_category_edit(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk)
    form = ExpenseCategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Catégorie mise à jour.")
        return redirect("financial:expense_category_list")
    return render(
        request,
        "financial/expense_category_form.html",
        {"form": form, "category": category, "action": "Modifier la catégorie"},
    )


# ─────────────────────────────────────────────────────────────────────────── #
# Financial periods
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def period_list(request):
    periods = FinancialPeriod.objects.order_by("-date_start")
    return render(request, "financial/period_list.html", {"periods": periods})


@admin_required
def period_create(request):
    form = FinancialPeriodForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Période créée.")
        return redirect("financial:period_list")
    return render(
        request,
        "financial/period_form.html",
        {"form": form, "action": "Nouvelle période"},
    )


@admin_required
def period_detail(request, pk):
    period = get_object_or_404(FinancialPeriod, pk=pk)
    return render(request, "financial/period_detail.html", {"period": period})


@admin_required
def period_edit(request, pk):
    period = get_object_or_404(FinancialPeriod, pk=pk)
    if period.is_closed:
        messages.error(request, "Une période clôturée ne peut pas être modifiée.")
        return redirect("financial:period_detail", pk=pk)
    form = FinancialPeriodForm(request.POST or None, instance=period)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Période mise à jour.")
        return redirect("financial:period_detail", pk=pk)
    return render(
        request, "financial/period_form.html", {"form": form, "action": "Modifier"}
    )


@admin_required
@require_POST
def period_close(request, pk):
    period = get_object_or_404(FinancialPeriod, pk=pk)
    period.is_closed = True
    period.save(update_fields=["is_closed"])
    messages.success(request, f"Période « {period.name} » clôturée.")
    return redirect("financial:period_detail", pk=pk)


# ─────────────────────────────────────────────────────────────────────────── #
# Analytics & reporting
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def financial_analytics(request):
    date_from, date_to = current_year_range()
    summary = revenue_summary(date_from, date_to)
    pending_bc = proformas_pending_bc()[:10]
    ready_to_finalize = proformas_ready_to_finalize()[:10]
    overdue = outstanding_invoices().filter(invoice_date__lt=timezone.now().date())[:10]
    top_clients = top_clients_by_revenue(limit=5, date_from=date_from, date_to=date_to)
    return render(
        request,
        "financial/analytics_dashboard.html",
        {
            "summary": summary,
            "pending_bc": pending_bc,
            "ready_to_finalize": ready_to_finalize,
            "overdue": overdue,
            "top_clients": top_clients,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def revenue_report(request):
    form = ReportFilterForm(request.GET or None)
    context = {"filter_form": form}
    if form.is_valid():
        date_from, date_to = resolve_date_range(form.cleaned_data)
        invoice_type = form.cleaned_data.get("invoice_type") or None
        context["summary"] = revenue_summary(date_from, date_to, invoice_type)
        context["monthly"] = revenue_by_month(date_from, date_to)
        context["date_from"] = date_from
        context["date_to"] = date_to
    return render(request, "financial/revenue_report.html", context)


@admin_required
def outstanding_report(request):
    return render(
        request,
        "financial/outstanding_report.html",
        {
            "overdue_finals": outstanding_invoices(),
            "pending_bc": proformas_pending_bc(),
            "ready_to_finalize": proformas_ready_to_finalize(),
        },
    )


@admin_required
def expense_report(request):
    from django.db.models import Count

    form = ReportFilterForm(request.GET or None)
    context = {"form": form}

    if form.is_valid():
        date_from, date_to = resolve_date_range(form.cleaned_data)
        base_qs = Expense.objects.filter(
            date__range=[date_from, date_to],
            approval_status=Expense.ApprovalStatus.APPROVED,
        ).select_related("category")
        agg = base_qs.aggregate(
            total=Sum("amount"),
            by_session=Sum("amount", filter=Q(allocated_to_session__isnull=False)),
            by_project=Sum("amount", filter=Q(allocated_to_project__isnull=False)),
            overhead=Sum("amount", filter=Q(is_overhead=True)),
        )
        by_category = (
            base_qs.values(
                "category__name", "category__color", "category__is_direct_cost"
            )
            .annotate(total=Sum("amount"), count=Count("id"))
            .order_by("-total")
        )
        all_qs = Expense.objects.filter(date__range=[date_from, date_to])
        approval_agg = all_qs.aggregate(
            approved_total=Sum(
                "amount", filter=Q(approval_status=Expense.ApprovalStatus.APPROVED)
            ),
            approved_count=Count(
                "id", filter=Q(approval_status=Expense.ApprovalStatus.APPROVED)
            ),
            pending_total=Sum(
                "amount", filter=Q(approval_status=Expense.ApprovalStatus.PENDING)
            ),
            pending_count=Count(
                "id", filter=Q(approval_status=Expense.ApprovalStatus.PENDING)
            ),
            rejected_total=Sum(
                "amount", filter=Q(approval_status=Expense.ApprovalStatus.REJECTED)
            ),
            rejected_count=Count(
                "id", filter=Q(approval_status=Expense.ApprovalStatus.REJECTED)
            ),
        )
        missing_qs = all_qs.filter(receipt="", receipt_missing=False)
        context.update(
            {
                "date_from": date_from,
                "date_to": date_to,
                "total": agg["total"] or Decimal("0"),
                "by_session": agg["by_session"] or Decimal("0"),
                "by_project": agg["by_project"] or Decimal("0"),
                "overhead": agg["overhead"] or Decimal("0"),
                "by_category": by_category,
                "approved_total": approval_agg["approved_total"] or Decimal("0"),
                "approved_count": approval_agg["approved_count"] or 0,
                "pending_total": approval_agg["pending_total"] or Decimal("0"),
                "pending_count": approval_agg["pending_count"] or 0,
                "rejected_total": approval_agg["rejected_total"] or Decimal("0"),
                "rejected_count": approval_agg["rejected_count"] or 0,
                "missing_receipt_count": missing_qs.count(),
                "missing_receipt_amount": missing_qs.aggregate(s=Sum("amount"))["s"]
                or Decimal("0"),
            }
        )

    return render(request, "financial/expense_report.html", context)


@admin_required
def margin_report(request):
    from formations.models import Session
    from etudes.models import StudyProject

    sessions = (
        Session.objects.filter(status=Session.STATUS_COMPLETED)
        .select_related("formation", "client")
        .order_by("-date_start")[:50]
    )
    projects = (
        StudyProject.objects.filter(status=StudyProject.STATUS_COMPLETED)
        .select_related("client")
        .order_by("-start_date")[:50]
    )
    return render(
        request,
        "financial/margin_report.html",
        {
            "session_margins": [{"session": s, **session_margin(s)} for s in sessions],
            "project_margins": [{"project": p, **project_margin(p)} for p in projects],
        },
    )


@admin_required
def revenue_chart_data(request):
    form = ReportFilterForm(request.GET or None)
    if not form.is_valid():
        date_from, date_to = current_year_range()
    else:
        date_from, date_to = resolve_date_range(form.cleaned_data)
    data = revenue_by_month(date_from, date_to)
    for row in data:
        row["formation_ht"] = float(row["formation_ht"])
        row["etude_ht"] = float(row["etude_ht"])
        row["total_ht"] = float(row["total_ht"])
    return JsonResponse({"data": data})


# ── Invoice sequence counter override ─────────────────────────────────────── #


@admin_required
def invoice_sequence_list(request):
    """List all known sequences and allow setting the next number for each."""
    from datetime import date

    from financial.models import InvoiceSequence

    current_year = date.today().year
    # Show current year + adjacent years so ops can set up coming year in advance
    years = [current_year - 1, current_year, current_year + 1]

    if request.method == "POST":
        seq_id = request.POST.get("seq_id")
        next_number_raw = request.POST.get("next_number", "").strip()
        try:
            seq = InvoiceSequence.objects.get(pk=seq_id)
            next_number = int(next_number_raw)
            seq.set_next_number(next_number)
            messages.success(
                request,
                f"Compteur {seq} mis à jour — prochain numéro : {next_number:03d}.",
            )
        except InvoiceSequence.DoesNotExist:
            messages.error(request, "Séquence introuvable.")
        except (ValueError, TypeError):
            messages.error(request, "Numéro invalide.")
        return redirect("financial:invoice_sequence_list")

    # Ensure rows exist for the displayed year × type × phase combinations
    for year in years:
        for inv_type in Invoice.InvoiceType.values:
            for phase in InvoiceSequence.Phase.values:
                InvoiceSequence.objects.get_or_create(
                    invoice_type=inv_type,
                    year=year,
                    phase=phase,
                    defaults={"last_number": 0},
                )

    sequences = InvoiceSequence.objects.filter(year__in=years).order_by(
        "-year", "invoice_type", "phase"
    )
    return render(
        request,
        "financial/invoice_sequence_list.html",
        {"sequences": sequences, "years": years},
    )


# ─────────────────────────────────────────────────────────────────────────── #
# Beneficiary directory — CRUD
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def beneficiary_list(request):
    qs = Beneficiary.objects.select_related("beneficiary_type", "trainer").order_by(
        "name"
    )

    q = request.GET.get("q", "").strip()
    btype = request.GET.get("type", "").strip()
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(nif__icontains=q))
    if btype:
        qs = qs.filter(beneficiary_type_id=btype)

    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(request.GET.get("page"))
    btypes = BeneficiaryType.objects.order_by("name")
    return render(
        request,
        "financial/beneficiary_list.html",
        {"page_obj": page_obj, "btypes": btypes, "q": q, "btype": btype},
    )


@admin_required
def beneficiary_detail(request, pk):
    beneficiary = get_object_or_404(
        Beneficiary.objects.select_related("beneficiary_type", "trainer"),
        pk=pk,
    )
    accounts = beneficiary.accounts.order_by("-is_default", "account_type")
    expenses = (
        Expense.objects.filter(beneficiary=beneficiary)
        .select_related("category")
        .order_by("-date")[:20]
    )
    return render(
        request,
        "financial/beneficiary_detail.html",
        {
            "beneficiary": beneficiary,
            "accounts": accounts,
            "expenses": expenses,
            "account_form": PaymentAccountForm(beneficiary=beneficiary),
        },
    )


@admin_required
def beneficiary_create(request):
    from financial.forms import BeneficiaryForm, BeneficiaryTypeForm

    form = BeneficiaryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        beneficiary = form.save()
        messages.success(request, f"Bénéficiaire « {beneficiary.name} » créé.")
        return redirect("financial:beneficiary_detail", pk=beneficiary.pk)
    return render(
        request,
        "financial/beneficiary_form.html",
        {
            "form": form,
            "action": "Nouveau bénéficiaire",
            "beneficiary_type_form": BeneficiaryTypeForm(),
        },
    )


@admin_required
def beneficiary_edit(request, pk):
    from financial.forms import BeneficiaryForm

    beneficiary = get_object_or_404(Beneficiary, pk=pk)
    form = BeneficiaryForm(request.POST or None, instance=beneficiary)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Bénéficiaire mis à jour.")
        return redirect("financial:beneficiary_detail", pk=pk)
    return render(
        request,
        "financial/beneficiary_form.html",
        {"form": form, "action": "Modifier", "beneficiary": beneficiary},
    )


# ─────────────────────────────────────────────────────────────────────────── #
# PaymentAccount — nested under beneficiary
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def payment_account_create(request, beneficiary_pk):
    beneficiary = get_object_or_404(Beneficiary, pk=beneficiary_pk)
    form = PaymentAccountForm(request.POST or None, beneficiary=beneficiary)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Compte ajouté.")
        return redirect("financial:beneficiary_detail", pk=beneficiary_pk)
    return render(
        request,
        "financial/payment_account_form.html",
        {"form": form, "beneficiary": beneficiary, "action": "Nouveau compte"},
    )


@admin_required
def payment_account_edit(request, beneficiary_pk, pk):
    beneficiary = get_object_or_404(Beneficiary, pk=beneficiary_pk)
    account = get_object_or_404(PaymentAccount, pk=pk, beneficiary=beneficiary)
    form = PaymentAccountForm(
        request.POST or None, instance=account, beneficiary=beneficiary
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Compte mis à jour.")
        return redirect("financial:beneficiary_detail", pk=beneficiary_pk)
    return render(
        request,
        "financial/payment_account_form.html",
        {
            "form": form,
            "beneficiary": beneficiary,
            "account": account,
            "action": "Modifier le compte",
        },
    )


@admin_required
@require_POST
def payment_account_delete(request, beneficiary_pk, pk):
    account = get_object_or_404(PaymentAccount, pk=pk, beneficiary_id=beneficiary_pk)
    account.delete()
    messages.success(request, "Compte supprimé.")
    return redirect("financial:beneficiary_detail", pk=beneficiary_pk)


# ─────────────────────────────────────────────────────────────────────────── #
# BeneficiaryType — inline management
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def beneficiary_type_list(request):
    from financial.forms import BeneficiaryTypeForm as BTForm

    types = BeneficiaryType.objects.order_by("name")
    form = BTForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        btype = form.save()
        messages.success(request, f"Type « {btype.name} » créé.")
        return redirect("financial:beneficiary_type_list")
    return render(
        request,
        "financial/beneficiary_type_list.html",
        {"types": types, "form": form},
    )


@admin_required
@require_POST
def beneficiary_type_delete(request, pk):
    btype = get_object_or_404(BeneficiaryType, pk=pk)
    if btype.beneficiaries.exists():
        messages.error(
            request,
            f"Impossible de supprimer « {btype.name} » — des bénéficiaires y sont rattachés.",
        )
    else:
        btype.delete()
        messages.success(request, f"Type « {btype.name} » supprimé.")
    return redirect("financial:beneficiary_type_list")


# ─────────────────────────────────────────────────────────────────────────── #
# AJAX / modal quick-add endpoints
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def beneficiary_quick_add(request):
    """
    POST-only modal endpoint.
    On success: returns JSON {success: true, id, name, irg_rate, default_account_id}.
    On error:   returns JSON {success: false, errors: {field: [msg]}}.
    The expense form JS uses this to add the new beneficiary to the select
    and immediately populate the accounts dropdown.
    """
    from financial.forms import BeneficiaryForm

    if request.method != "POST":
        return JsonResponse(
            {"success": False, "errors": {"__all__": ["Méthode non autorisée."]}},
            status=405,
        )

    form = BeneficiaryForm(request.POST)
    if form.is_valid():
        beneficiary = form.save()
        default_acct = beneficiary.default_payment_account
        return JsonResponse(
            {
                "success": True,
                "id": beneficiary.pk,
                "name": beneficiary.name,
                "irg_rate": str(beneficiary.irg_rate),
                "default_account_id": default_acct.pk if default_acct else None,
            }
        )
    return JsonResponse({"success": False, "errors": form.errors}, status=400)


@admin_required
def payment_account_quick_add(request):
    """
    POST-only modal endpoint.
    Expects beneficiary_id in POST data.
    On success: returns JSON {success: true, id, label, account_type, is_default}.
    """
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "errors": {"__all__": ["Méthode non autorisée."]}},
            status=405,
        )

    beneficiary_pk = request.POST.get("beneficiary_id")
    try:
        beneficiary = Beneficiary.objects.get(pk=beneficiary_pk)
    except (Beneficiary.DoesNotExist, ValueError, TypeError):
        return JsonResponse(
            {
                "success": False,
                "errors": {"beneficiary_id": ["Bénéficiaire introuvable."]},
            },
            status=400,
        )

    form = PaymentAccountForm(request.POST, beneficiary=beneficiary)
    if form.is_valid():
        account = form.save()
        # Build the display label using the same logic as beneficiary_accounts_json:
        # prefer the stored label field; fall back to type + number + bank.
        if account.label:
            display_label = account.label
        else:
            parts = [account.get_account_type_display()]
            if account.account_number:
                parts.append(account.account_number)
            if account.bank_name:
                parts.append(f"({account.bank_name})")
            display_label = " — ".join(parts)
        return JsonResponse(
            {
                "success": True,
                "id": account.pk,
                "label": display_label,
                "account_type": account.account_type,
                "account_type_display": account.get_account_type_display(),
                "is_default": account.is_default,
            }
        )
    return JsonResponse({"success": False, "errors": form.errors}, status=400)


@admin_required
def beneficiary_type_quick_add(request):
    """
    POST-only modal endpoint to create a BeneficiaryType on-the-fly.
    Returns JSON {success: true, id, name}.
    """
    from financial.forms import BeneficiaryTypeForm

    if request.method != "POST":
        return JsonResponse({"success": False}, status=405)

    form = BeneficiaryTypeForm(request.POST)
    if form.is_valid():
        btype = form.save()
        return JsonResponse({"success": True, "id": btype.pk, "name": btype.name})
    return JsonResponse({"success": False, "errors": form.errors}, status=400)


@admin_required
def beneficiary_accounts_json(request, pk):
    """
    GET endpoint — returns all payment accounts for a beneficiary as JSON.
    Used by the expense form to populate the accounts <select> when the
    beneficiary dropdown changes.

    Response shape:
      {
        accounts: [{id, label, account_type, account_type_display, is_default}, ...],
        irg_rate: "0.10"
      }
    """
    beneficiary = get_object_or_404(Beneficiary, pk=pk)
    accounts = list(
        beneficiary.payment_accounts.values(
            "id", "account_type", "label", "account_number", "bank_name", "is_default"
        ).order_by("-is_default", "account_type")
    )
    # Build human-readable label for each account
    type_display = dict(PaymentAccount.AccountType.choices)
    for acct in accounts:
        # Prefer the stored label field; fall back to building one from parts
        if acct.get("label"):
            display_label = acct["label"]
        else:
            parts = [type_display.get(acct["account_type"], acct["account_type"])]
            if acct["account_number"]:
                parts.append(acct["account_number"])
            if acct["bank_name"]:
                parts.append(f"({acct['bank_name']})")
            display_label = " — ".join(parts)
        acct["label"] = display_label
        acct["account_type_display"] = type_display.get(acct["account_type"], "")

    # Trainer-specific data
    trainer_sessions = []
    try:
        trainer_obj = (
            beneficiary.trainer
            if beneficiary.is_trainer and beneficiary.trainer_id
            else None
        )
    except Exception:
        trainer_obj = None
    if trainer_obj:
        from formations.models import Session

        sessions_qs = (
            Session.objects.filter(
                trainer=trainer_obj,
            )
            .order_by("-date_start")
            .values("id", "formation__title", "date_start")
        )
        for s in sessions_qs:
            label = f"{s['formation__title']} — {s['date_start'].strftime('%Y-%m-%d') if s['date_start'] else ''}"
            trainer_sessions.append({"id": s["id"], "label": label})

    return JsonResponse(
        {
            "accounts": accounts,
            "irg_rate": str(beneficiary.irg_rate),
            "is_trainer": beneficiary.is_trainer,
            "daily_rate": (
                str(beneficiary.daily_rate) if beneficiary.daily_rate else "0"
            ),
            "monthly_rate": (
                str(beneficiary.monthly_rate) if beneficiary.monthly_rate else "0"
            ),
            "trainer_sessions": trainer_sessions,
        }
    )
