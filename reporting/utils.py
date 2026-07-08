# =============================================================================
# reporting/utils.py  —  Dashboard & report KPI aggregations
# =============================================================================

from datetime import date
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone


def dashboard_kpis(date_from=None, date_to=None):
    """
    Compute all KPIs needed by the dashboard in as few queries as possible.
    Returns a flat dict consumed directly by the dashboard template context.
    Accepts optional date_from / date_to to filter the period (defaults to
    current calendar year).
    """
    from clients.models import Client
    from etudes.models import StudyProject
    from financial.models import Expense, Invoice, Payment
    from formations.models import Session

    today = date.today()

    # ── Period bounds ──────────────────────────────────────────────────── #
    year_start = date(today.year, 1, 1)
    year_end = date(today.year, 12, 31)
    date_from = date_from or year_start
    date_to = date_to or year_end

    inv_year = Invoice.objects.filter(
        phase=Invoice.Phase.FINALE,
        invoice_date__range=[date_from, date_to],
        status__in=[
            Invoice.Status.UNPAID,
            Invoice.Status.PARTIALLY_PAID,
            Invoice.Status.PAID,
        ],
    ).aggregate(
        total_ht=Sum("amount_ht"),
        formation_ht=Sum(
            "amount_ht", filter=Q(invoice_type=Invoice.InvoiceType.FORMATION)
        ),
        etude_ht=Sum("amount_ht", filter=Q(invoice_type=Invoice.InvoiceType.ETUDE)),
    )

    # ── Collections ───────────────────────────────────────────────────── #
    collected_year = Payment.objects.filter(
        date__range=[date_from, date_to],
        status=Payment.Status.CONFIRMED,
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    # ── Outstanding ───────────────────────────────────────────────────── #
    outstanding = Invoice.objects.filter(
        phase=Invoice.Phase.FINALE,
        status__in=[Invoice.Status.UNPAID, Invoice.Status.PARTIALLY_PAID],
    ).aggregate(
        count=Count("pk"),
        total=Sum("amount_remaining"),
        overdue_count=Count("pk", filter=Q(due_date__lt=today)),
        overdue_total=Sum("amount_remaining", filter=Q(due_date__lt=today)),
    )

    # ── Formations actives (is_active + base_price > 0) ──────────────── #
    from formations.models import Formation

    active_formations_count = Formation.objects.filter(
        is_active=True,
        base_price__gt=0,
    ).count()

    # ── Sessions ──────────────────────────────────────────────────────── #
    sessions = Session.objects.aggregate(
        upcoming=Count(
            "pk", filter=Q(status=Session.STATUS_PLANNED, date_start__gte=today)
        ),
        in_progress=Count("pk", filter=Q(status=Session.STATUS_IN_PROGRESS)),
        completed_year=Count(
            "pk",
            filter=Q(
                status=Session.STATUS_COMPLETED,
                date_start__range=[date_from, date_to],
            ),
        ),
    )

    # ── Projects ──────────────────────────────────────────────────────── #
    projects = StudyProject.objects.aggregate(
        active=Count("pk", filter=Q(status=StudyProject.STATUS_IN_PROGRESS)),
        overdue=Count(
            "pk",
            filter=Q(
                status=StudyProject.STATUS_IN_PROGRESS,
                end_date__lt=today,
            ),
        ),
    )

    # -- Expenses (year - approved) --
    exp_approved = Expense.objects.filter(
        date__range=[date_from, date_to],
        approval_status=Expense.ApprovalStatus.APPROVED,
    ).aggregate(
        total=Sum("amount"),
        count=Count("pk"),
        tva=Sum("tva_amount"),
        timbre=Sum("timbre_fiscal"),
    )
    expenses_year = exp_approved["total"] or Decimal("0")
    expenses_approved_count = exp_approved["count"] or 0
    expenses_tva_year = exp_approved["tva"] or Decimal("0")
    # Unlike Invoice.timbre_fiscal, Expense.timbre_fiscal is a persisted field
    # computed unconditionally on every expense's gross_amount (no cash-only
    # gate) — see Expense.save(). It's purely informational/stats, so this is
    # a straight DB Sum, not the per-row Python loop the invoice side needs.
    expenses_timbre_fiscal = exp_approved["timbre"] or Decimal("0")

    # -- Expenses (year - all) --
    exp_all = Expense.objects.filter(
        date__range=[date_from, date_to],
    ).aggregate(total=Sum("amount"), count=Count("pk"))
    expenses_year_total = exp_all["total"] or Decimal("0")
    expenses_total_count = exp_all["count"] or 0

    # -- Expenses (year - non-approved) --
    exp_non_approved = (
        Expense.objects.filter(
            date__range=[date_from, date_to],
        )
        .exclude(
            approval_status=Expense.ApprovalStatus.APPROVED,
        )
        .aggregate(total=Sum("amount"), count=Count("pk"))
    )
    expenses_year_non_approved = exp_non_approved["total"] or Decimal("0")
    expenses_non_approved_count = exp_non_approved["count"] or 0

    # -- Expenses needing action --
    _exp_action = Expense.objects.filter(
        Q(receipt_missing=True) | Q(approval_status=Expense.ApprovalStatus.PENDING)
    ).aggregate(count=Count("pk"), total=Sum("amount"))
    expenses_action = _exp_action["count"] or 0
    expenses_action_total = _exp_action["total"] or Decimal("0")

    total_ht = inv_year["total_ht"] or Decimal("0")

    # ── Invoices — full breakdown (finale, non-voided, period) ────────── #
    inv_full = (
        Invoice.objects.filter(
            phase=Invoice.Phase.FINALE,
            invoice_date__range=[date_from, date_to],
        )
        .exclude(status=Invoice.Status.VOIDED)
        .aggregate(
            ht=Sum("amount_ht"),
            tva=Sum("amount_tva"),
            ttc=Sum("amount_ttc"),
        )
    )

    invoices_ht_total = inv_full["ht"] or Decimal("0")
    invoices_tva_total = inv_full["tva"] or Decimal("0")
    invoices_ttc_total = inv_full["ttc"] or Decimal("0")

    # ── Payments — confirmed, period ──────────────────────────────────── #
    payments_total = Payment.objects.filter(
        status=Payment.Status.CONFIRMED,
        date__range=[date_from, date_to],
    ).aggregate(total=Sum("amount"))["total"] or Decimal("0")

    # ── Résultat réel (factures PAYÉES HT − dépenses approuvées) ─────── #
    paid_ht = Invoice.objects.filter(
        phase=Invoice.Phase.FINALE,
        status=Invoice.Status.PAID,
        invoice_date__range=[date_from, date_to],
    ).aggregate(total=Sum("amount_ht"))["total"] or Decimal("0")

    real_result = paid_ht - expenses_year

    # ── Margins — HT base ─────────────────────────────────────────────── #
    # profit             : billed HT    − approved costs
    # current_margin     : cash received − approved costs
    # theoretical_margin : total HT     − all costs (approved + non-approved)
    profit = invoices_ht_total - expenses_year
    current_margin = payments_total - expenses_year
    theoretical_margin = invoices_ht_total - expenses_year_total

    # ── Margins — TTC base ────────────────────────────────────────────── #
    # payments are already TTC amounts, so current_margin_ttc == current_margin
    profit_ttc = invoices_ttc_total - expenses_year
    current_margin_ttc = payments_total - expenses_year
    theoretical_margin_ttc = invoices_ttc_total - expenses_year_total

    # TVA nette à reverser = TVA collectée (ventes) − TVA déductible (achats)
    tva_net = invoices_tva_total - expenses_tva_year

    # ── Timbre fiscal collecté — facture side (espèces uniquement) ────── #
    # Invoice.timbre_fiscal is a computed property (never persisted — it
    # only applies when mode_reglement == ESPECE, on a slab of amount_ttc),
    # so it can't be summed with a DB aggregate; sum it in Python over the
    # same finale/non-voided/period invoice set used for the HT/TVA/TTC
    # breakdown above.
    timbre_fiscal_invoices = sum(
        (
            inv.timbre_fiscal
            for inv in Invoice.objects.filter(
                phase=Invoice.Phase.FINALE,
                invoice_date__range=[date_from, date_to],
                mode_reglement=Invoice.PaymentMode.ESPECE,
            )
            .exclude(status=Invoice.Status.VOIDED)
            .only("amount_ttc", "mode_reglement")
        ),
        Decimal("0"),
    )

    return {
        # Revenue
        "ca_ht": total_ht,
        "ca_formation_ht": inv_year["formation_ht"] or Decimal("0"),
        "ca_etude_ht": inv_year["etude_ht"] or Decimal("0"),
        "collected_year": collected_year,
        # Expenses
        "expenses_year": expenses_year,
        "expenses_approved_count": expenses_approved_count,
        "expenses_year_total": expenses_year_total,
        "expenses_total_count": expenses_total_count,
        "expenses_year_non_approved": expenses_year_non_approved,
        "expenses_non_approved_count": expenses_non_approved_count,
        "expenses_need_action": expenses_action,
        "expenses_need_action_total": expenses_action_total,
        # Invoices full breakdown
        "invoices_ht_total": invoices_ht_total,
        "invoices_tva_total": invoices_tva_total,
        "invoices_ttc_total": invoices_ttc_total,
        # TVA
        "expenses_tva_year": expenses_tva_year,
        "tva_net": tva_net,
        # Timbre fiscal — both sides shown separately, same pairing as TVA
        # collectée/déductible above (not netted against each other: one is
        # stamp duty added to cash invoices, the other is stamp duty already
        # embedded in cash expense purchases — different fiscal flows).
        "timbre_fiscal_invoices": timbre_fiscal_invoices,
        "timbre_fiscal_expenses": expenses_timbre_fiscal,
        # Payments
        "payments_total": payments_total,
        # Margins — HT base
        "gross_margin": total_ht - expenses_year,  # legacy alias
        "profit": profit,
        "current_margin": current_margin,
        "theoretical_margin": theoretical_margin,
        # Margins — TTC base
        "profit_ttc": profit_ttc,
        "current_margin_ttc": current_margin_ttc,
        "theoretical_margin_ttc": theoretical_margin_ttc,
        # Outstanding
        "outstanding_count": outstanding["count"] or 0,
        "outstanding_total": outstanding["total"] or Decimal("0"),
        "overdue_count": outstanding["overdue_count"] or 0,
        "overdue_total": outstanding["overdue_total"] or Decimal("0"),
        # Operations
        "active_formations_count": active_formations_count,
        "sessions_upcoming": sessions["upcoming"] or 0,
        "sessions_in_progress": sessions["in_progress"] or 0,
        "sessions_completed_year": sessions["completed_year"] or 0,
        "projects_active": projects["active"] or 0,
        "projects_overdue": projects["overdue"] or 0,
        # Résultat réel
        "paid_ht": paid_ht,
        "real_result": real_result,
    }


def session_fill_rate_report(date_from=None, date_to=None):
    """
    Return sessions annotated with fill_rate for the fill-rate report.
    """
    from formations.models import Session
    from django.db.models import F, FloatField, ExpressionWrapper

    qs = Session.objects.filter(
        status__in=[Session.STATUS_COMPLETED, Session.STATUS_IN_PROGRESS]
    ).select_related("formation", "trainer", "client")

    if date_from:
        qs = qs.filter(date_start__gte=date_from)
    if date_to:
        qs = qs.filter(date_end__lte=date_to)

    return qs.annotate(
        participants_ann=Count("participants"),
        fill_pct=ExpressionWrapper(
            Count("participants") * 100.0 / F("capacity"),
            output_field=FloatField(),
        ),
    ).order_by("-date_start")


def trainer_utilization_report(date_from=None, date_to=None):
    """
    Return trainers annotated with session_count and total_days for the period.
    """
    from formations.models import Session, Trainer
    from django.db.models import F

    qs = (
        Trainer.objects.filter(is_active=True)
        .annotate(
            period_sessions=Count(
                "sessions",
                filter=Q(
                    sessions__status__in=[
                        Session.STATUS_COMPLETED,
                        Session.STATUS_IN_PROGRESS,
                    ],
                    **({"sessions__date_start__gte": date_from} if date_from else {}),
                    **({"sessions__date_end__lte": date_to} if date_to else {}),
                ),
            )
        )
        .order_by("-period_sessions")
    )

    return qs


def equipment_utilization_report():
    """
    Return equipment list annotated with usage stats for the utilization report.
    """
    from resources.models import Equipment
    from django.conf import settings

    idle_threshold = getattr(settings, "EQUIPMENT_IDLE_THRESHOLD_DAYS", 90)
    today = date.today()

    qs = Equipment.objects.annotate(
        usage_count_ann=Count("usages"),
        total_hours_ann=Sum("usages__duration_hours"),
    ).order_by("status", "-usage_count_ann")

    return qs
