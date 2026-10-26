"""Cash journal (Caisse) views — journals, vouchers, statement, printable documents."""

from decimal import Decimal

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.utils import admin_required
from financial.cash_forms import CashJournalForm, CashPeriodForm, CashVoucherForm
from financial.cash_utils import amount_in_words, journal_statement, resolve_period
from financial.models import CashJournal, CashVoucher, Expense, Payment

MIN_PRINT_ROWS = 12


def _period_ctx(request):
    d_from, d_to, label = resolve_period(request.GET)
    return d_from, d_to, label, CashPeriodForm(request.GET or None)


def _warn_if_negative(request, journal):
    if journal.current_balance < 0:
        messages.warning(
            request,
            f"Attention : le solde de « {journal.name} » est négatif "
            f"({journal.current_balance:,.2f} DA).",
        )


# ── Journals ────────────────────────────────────────────────────────────── #


@admin_required
def cash_journal_list(request):
    journals = list(CashJournal.objects.all())
    return render(request, "financial/cash/journal_list.html", {"journals": journals})


@admin_required
def cash_journal_create(request):
    form = CashJournalForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        journal = form.save()
        messages.success(request, "Journal de caisse créé.")
        return redirect("financial:cash_journal_detail", pk=journal.pk)
    return render(
        request, "financial/cash/journal_form.html", {"form": form, "action": "Nouveau journal"}
    )


@admin_required
def cash_journal_edit(request, pk):
    journal = get_object_or_404(CashJournal, pk=pk)
    form = CashJournalForm(request.POST or None, instance=journal)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Journal mis à jour — les soldes sont recalculés.")
        _warn_if_negative(request, journal)
        return redirect("financial:cash_journal_detail", pk=pk)
    return render(
        request,
        "financial/cash/journal_form.html",
        {"form": form, "journal": journal, "action": "Modifier le journal"},
    )


@admin_required
def cash_journal_detail(request, pk):
    journal = get_object_or_404(CashJournal, pk=pk)
    d_from, d_to, label, form = _period_ctx(request)
    stmt = journal_statement(journal, d_from, d_to)
    return render(
        request,
        "financial/cash/journal_detail.html",
        {
            "journal": journal,
            "stmt": stmt,
            "period_label": label,
            "period_form": form,
            "querystring": request.GET.urlencode(),
            "current_balance": journal.current_balance,
        },
    )


@admin_required
def cash_journal_print(request, pk):
    """Journal de caisse — A4 paysage, filtered by month/year or custom range."""
    journal = get_object_or_404(CashJournal, pk=pk)
    d_from, d_to, label = resolve_period(request.GET)
    stmt = journal_statement(journal, d_from, d_to)
    n = len(stmt["rows"])
    blank = list(range(n + 1, max(n, MIN_PRINT_ROWS) + 1))
    return render(
        request,
        "financial/cash/journal_print.html",
        {
            "journal": journal,
            "stmt": stmt,
            "period_label": label,
            "date_from": d_from,
            "date_to": d_to,
            "blank_rows": blank,
            "printed_at": timezone.localtime(),
        },
    )


# ── Vouchers ────────────────────────────────────────────────────────────── #


@admin_required
def cash_voucher_create(request, journal_pk, kind):
    journal = get_object_or_404(CashJournal, pk=journal_pk)
    if kind not in (CashVoucher.Kind.IN, CashVoucher.Kind.OUT):
        return redirect("financial:cash_journal_detail", pk=journal.pk)
    form = CashVoucherForm(
        request.POST or None, kind=kind, initial={"date": timezone.localdate()}
    )
    if request.method == "POST" and form.is_valid():
        voucher = form.save(commit=False)
        voucher.journal, voucher.kind, voucher.created_by = journal, kind, request.user
        voucher.save()
        messages.success(request, f"Pièce {voucher.reference} enregistrée.")
        _warn_if_negative(request, journal)
        return redirect("financial:cash_voucher_detail", pk=voucher.pk)
    return render(
        request,
        "financial/cash/voucher_form.html",
        {"form": form, "journal": journal, "kind": kind, "action": "Nouvelle pièce"},
    )


@admin_required
def cash_voucher_detail(request, pk):
    voucher = get_object_or_404(CashVoucher.objects.select_related("journal"), pk=pk)
    return render(
        request,
        "financial/cash/voucher_detail.html",
        {"voucher": voucher, "words": amount_in_words(voucher.amount)},
    )


@admin_required
def cash_voucher_edit(request, pk):
    voucher = get_object_or_404(CashVoucher.objects.select_related("journal"), pk=pk)
    form = CashVoucherForm(request.POST or None, instance=voucher, kind=voucher.kind)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Pièce modifiée — le journal est recalculé.")
        _warn_if_negative(request, voucher.journal)
        return redirect("financial:cash_voucher_detail", pk=pk)
    return render(
        request,
        "financial/cash/voucher_form.html",
        {
            "form": form,
            "voucher": voucher,
            "journal": voucher.journal,
            "kind": voucher.kind,
            "action": f"Modifier {voucher.reference}",
        },
    )


@admin_required
@require_POST
def cash_voucher_delete(request, pk):
    voucher = get_object_or_404(CashVoucher, pk=pk)
    journal_pk, ref = voucher.journal_id, voucher.reference
    voucher.delete()
    messages.success(request, f"Pièce {ref} supprimée.")
    return redirect("financial:cash_journal_detail", pk=journal_pk)


@admin_required
def cash_voucher_print(request, pk):
    voucher = get_object_or_404(CashVoucher.objects.select_related("journal"), pk=pk)
    tpl = "voucher_print_in.html" if voucher.is_in else "voucher_print_out.html"
    return render(
        request,
        f"financial/cash/{tpl}",
        {"voucher": voucher, "words": amount_in_words(voucher.amount)},
    )


# ── Import cash operations already recorded elsewhere ───────────────────── #


def _import_candidates():
    payments = (
        Payment.objects.filter(
            method=Payment.Method.ESPECES,
            status=Payment.Status.CONFIRMED,
            cash_voucher__isnull=True,
        )
        .select_related("invoice__client")
        .order_by("date")
    )
    expenses = (
        Expense.objects.filter(
            approval_status=Expense.ApprovalStatus.APPROVED,
            payment_account__account_type="especes",
            cash_voucher__isnull=True,
        )
        .select_related("beneficiary")
        .order_by("date")
    )
    return payments, expenses


@admin_required
def cash_import(request, journal_pk):
    journal = get_object_or_404(CashJournal, pk=journal_pk)
    payments, expenses = _import_candidates()
    if request.method == "POST":
        created = 0
        for p in payments.filter(pk__in=request.POST.getlist("payments")):
            CashVoucher.objects.create(
                journal=journal, kind=CashVoucher.Kind.IN, payment=p,
                date=p.date, amount=p.amount,
                label=f"Règlement facture {p.invoice.reference}",
                counterparty=p.invoice.client.name, created_by=request.user,
            )
            created += 1
        for e in expenses.filter(pk__in=request.POST.getlist("expenses")):
            CashVoucher.objects.create(
                journal=journal, kind=CashVoucher.Kind.OUT, expense=e,
                date=e.payment_date or e.date, amount=e.amount, label=e.description,
                counterparty=e.beneficiary.name if e.beneficiary_id else e.supplier,
                created_by=request.user,
            )
            created += 1
        messages.success(request, f"{created} opération(s) importée(s) dans la caisse.")
        _warn_if_negative(request, journal)
        return redirect("financial:cash_journal_detail", pk=journal.pk)
    return render(
        request,
        "financial/cash/import.html",
        {"journal": journal, "payments": payments, "expenses": expenses},
    )
