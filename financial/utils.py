# =============================================================================
# financial/utils.py  —  v3.0
# Reference generation, date helpers, report builders.
# =============================================================================

from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth

# ── Reference generation ─────────────────────────────────────────────────── #


def next_proforma_reference(invoice_type, invoice_date=None):
    """PF-F-NNN-YYYY / PF-E-NNN-YYYY — sequential, independent from finale."""
    from financial.models import Invoice

    year = (invoice_date or date.today()).year
    return Invoice._next_proforma_reference(invoice_type, year)


def next_final_reference(invoice_type, finalized_date=None):
    """F-NNN-YYYY / E-NNN-YYYY — gapless sequence, assigned at finalization."""
    from financial.models import Invoice

    year = (finalized_date or date.today()).year
    return Invoice._next_final_reference(invoice_type, year)


def next_credit_note_reference(cn_date=None):
    from financial.models import CreditNote

    year = (cn_date or date.today()).year
    return CreditNote._next_reference(year)


# ── Date range helpers ────────────────────────────────────────────────────── #


def resolve_date_range(form_cleaned_data):
    """
    Given cleaned data from ReportFilterForm, return (date_from, date_to).
    Prefers an explicit FinancialPeriod over manual date fields.
    """
    period = form_cleaned_data.get("period")
    if period:
        return period.date_start, period.date_end
    return form_cleaned_data["date_from"], form_cleaned_data["date_to"]


def current_year_range():
    """Return (Jan 1, Dec 31) for the current calendar year."""
    y = date.today().year
    return date(y, 1, 1), date(y, 12, 31)


# ── Revenue aggregates ────────────────────────────────────────────────────── #

# Statuses that represent "active" revenue (not voided / credit-noted)
_REVENUE_STATUSES = None


def _revenue_statuses():
    """Lazy import to avoid circular imports at module load time."""
    global _REVENUE_STATUSES
    if _REVENUE_STATUSES is None:
        from financial.models import Invoice

        _REVENUE_STATUSES = [
            Invoice.Status.UNPAID,
            Invoice.Status.PARTIALLY_PAID,
            Invoice.Status.PAID,
        ]
    return _REVENUE_STATUSES


def revenue_summary(date_from, date_to, invoice_type=None):
    """
    Return a dict with invoiced HT, collected, outstanding, and expense totals
    for the given date range, optionally filtered by invoice_type.
    Only FINALE phase invoices are counted (proformas have no fiscal value).
    """
    from financial.models import Expense, Invoice, Payment

    inv_qs = Invoice.objects.filter(
        phase=Invoice.Phase.FINALE,
        invoice_date__range=[date_from, date_to],
        status__in=_revenue_statuses(),
    )
    if invoice_type:
        inv_qs = inv_qs.filter(invoice_type=invoice_type)

    pay_qs = Payment.objects.filter(
        date__range=[date_from, date_to],
        status=Payment.Status.CONFIRMED,
        invoice__phase=Invoice.Phase.FINALE,
    )
    if invoice_type:
        pay_qs = pay_qs.filter(invoice__invoice_type=invoice_type)

    exp_qs = Expense.objects.filter(
        date__range=[date_from, date_to],
        approval_status=Expense.ApprovalStatus.APPROVED,
    )

    totals = inv_qs.aggregate(
        invoiced_ht=Sum("amount_ht"),
        invoiced_ttc=Sum("amount_ttc"),
        outstanding=Sum("amount_remaining"),
    )
    collected = pay_qs.aggregate(total=Sum("amount"))["total"] or Decimal("0")
    exp_agg = exp_qs.aggregate(total=Sum("amount"), tva=Sum("tva_amount"))
    expenses = exp_agg["total"] or Decimal("0")
    expense_tva = exp_agg["tva"] or Decimal("0")

    invoiced_ht = totals["invoiced_ht"] or Decimal("0")
    return {
        "invoiced_ht": invoiced_ht,
        "invoiced_ttc": totals["invoiced_ttc"] or Decimal("0"),
        "outstanding": totals["outstanding"] or Decimal("0"),
        "collected": collected,
        "expenses": expenses,
        "expense_tva": expense_tva,
        "gross_margin": invoiced_ht - expenses,
        "margin_rate": (
            round(((invoiced_ht - expenses) / invoiced_ht) * 100, 1)
            if invoiced_ht
            else Decimal("0")
        ),
    }


def revenue_by_month(date_from, date_to):
    """
    Return [{month, formation_ht, etude_ht, total_ht}, ...] ordered by month.
    Only FINALE invoices counted.
    """
    from financial.models import Invoice

    rows = (
        Invoice.objects.filter(
            phase=Invoice.Phase.FINALE,
            invoice_date__range=[date_from, date_to],
            status__in=_revenue_statuses(),
        )
        .annotate(month=TruncMonth("invoice_date"))
        .values("month", "invoice_type")
        .annotate(total_ht=Sum("amount_ht"))
        .order_by("month")
    )

    pivot = {}
    for row in rows:
        m = row["month"].strftime("%Y-%m")
        pivot.setdefault(
            m, {"month": m, "formation_ht": Decimal("0"), "etude_ht": Decimal("0")}
        )
        if row["invoice_type"] == Invoice.InvoiceType.FORMATION:
            pivot[m]["formation_ht"] = row["total_ht"]
        else:
            pivot[m]["etude_ht"] = row["total_ht"]

    result = sorted(pivot.values(), key=lambda x: x["month"])
    for r in result:
        r["total_ht"] = r["formation_ht"] + r["etude_ht"]
    return result


def outstanding_invoices():
    """Unpaid / partially-paid FINALE invoices, oldest first."""
    from financial.models import Invoice

    return (
        Invoice.objects.filter(
            phase=Invoice.Phase.FINALE,
            status__in=[Invoice.Status.UNPAID, Invoice.Status.PARTIALLY_PAID],
        )
        .select_related("client")
        .order_by("invoice_date")
    )


def proformas_pending_bc():
    """Proformas that have been sent but have no BC number recorded yet."""
    from financial.models import Invoice

    return (
        Invoice.objects.filter(
            phase=Invoice.Phase.PROFORMA,
            status__in=[Invoice.Status.DRAFT, Invoice.Status.SENT],
            bon_commande_number="",
        )
        .select_related("client")
        .order_by("invoice_date")
    )


def proformas_ready_to_finalize():
    """Proformas with a BC recorded, waiting for finalization."""
    from financial.models import Invoice

    return (
        Invoice.objects.filter(
            phase=Invoice.Phase.PROFORMA,
        )
        .exclude(bon_commande_number="")
        .select_related("client")
        .order_by("invoice_date")
    )


def top_clients_by_revenue(limit=10, date_from=None, date_to=None):
    """Clients annotated with total_paid from FINALE invoices, desc order."""
    from clients.models import Client
    from financial.models import Invoice

    filters = Q(
        invoices__phase=Invoice.Phase.FINALE,
        invoices__status=Invoice.Status.PAID,
    )
    if date_from:
        filters &= Q(invoices__invoice_date__gte=date_from)
    if date_to:
        filters &= Q(invoices__invoice_date__lte=date_to)

    return (
        Client.objects.filter(filters)
        .annotate(total_paid=Sum("invoices__amount_ttc"))
        .distinct()
        .order_by("-total_paid")[:limit]
    )


# ── Session / project margin ──────────────────────────────────────────────── #


def session_margin(session):
    """
    Return {revenue, expenses, margin, margin_rate} for a single session.
    Revenue = effective_price × attended participants.
    Note: invoiced revenue is tracked on Invoice; this uses session.total_revenue
    as a quick operational estimate.
    """
    from financial.models import Expense

    revenue = session.total_revenue
    expenses = Expense.objects.filter(
        allocated_to_session=session,
        approval_status=Expense.ApprovalStatus.APPROVED,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    margin = revenue - expenses
    return {
        "revenue": revenue,
        "expenses": expenses,
        "margin": margin,
        "margin_rate": round((margin / revenue * 100), 1) if revenue else Decimal("0"),
    }


def project_margin(project):
    """Return {budget, expenses, margin, margin_rate} for a study project."""
    from financial.models import Expense

    expenses = Expense.objects.filter(
        allocated_to_project=project,
        approval_status=Expense.ApprovalStatus.APPROVED,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")
    margin = project.budget - expenses
    return {
        "budget": project.budget,
        "expenses": expenses,
        "margin": margin,
        "margin_rate": (
            round((margin / project.budget * 100), 1)
            if project.budget
            else Decimal("0")
        ),
    }


# ── Amount in words (French / Algerian DA) ───────────────────────────────── #


def amount_to_words_fr(amount: Decimal) -> str:
    """
    Convert a Decimal DA amount to French words for the mandatory
    "Arrêtée la présente facture à la somme de …" line on printed invoices.

    Handles amounts up to 999 999 999 DA.  Centimes are appended as digits
    (e.g. "… et 50/100") when non-zero.

    This is a functional implementation covering the common invoice range.
    For production, consider the `num2words` library with lang='fr'.
    """
    ones = [
        "",
        "un",
        "deux",
        "trois",
        "quatre",
        "cinq",
        "six",
        "sept",
        "huit",
        "neuf",
        "dix",
        "onze",
        "douze",
        "treize",
        "quatorze",
        "quinze",
        "seize",
        "dix-sept",
        "dix-huit",
        "dix-neuf",
    ]
    tens = [
        "",
        "",
        "vingt",
        "trente",
        "quarante",
        "cinquante",
        "soixante",
        "soixante-dix",
        "quatre-vingt",
        "quatre-vingt-dix",
    ]

    def _under_100(n):
        if n < 20:
            return ones[n]
        t, o = divmod(n, 10)
        if t == 7:  # 70–79
            return f"soixante-{ones[10 + o]}"
        if t == 9:  # 90–99
            return f"quatre-vingt-{ones[10 + o]}"
        sep = "-" if o else ""
        et = "-et" if o == 1 and t not in (8,) else sep
        return f"{tens[t]}{et}-{ones[o]}" if o else tens[t]

    def _under_1000(n):
        if n == 0:
            return ""
        h, rem = divmod(n, 100)
        parts = []
        if h == 1:
            parts.append("cent")
        elif h > 1:
            suffix = "" if rem else "s"
            parts.append(f"{ones[h]} cent{suffix}")
        if rem:
            parts.append(_under_100(rem))
        return " ".join(p for p in parts if p)

    total_cents = int(amount * 100)
    dinars, centimes = divmod(total_cents, 100)

    if dinars == 0:
        word = "zéro"
    else:
        millions, rest = divmod(dinars, 1_000_000)
        thousands, hundreds = divmod(rest, 1000)
        parts = []
        if millions:
            m_word = _under_1000(millions)
            parts.append(f"{m_word} million{'s' if millions > 1 else ''}")
        if thousands:
            t_word = _under_1000(thousands)
            parts.append("mille" if thousands == 1 else f"{t_word} mille")
        if hundreds:
            parts.append(_under_1000(hundreds))
        word = " ".join(p for p in parts if p)

    result = f"{word.capitalize()} Dinars Algériens"
    if centimes:
        result += f" et {centimes:02d}/100"
    return result
