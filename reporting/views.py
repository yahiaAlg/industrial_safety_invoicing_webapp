# reporting/views.py

import csv
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import (
    Avg,
    Count,
    F,
    FloatField,
    Max,
    Min,
    Q,
    Sum,
    ExpressionWrapper,
)
from django.db.models.functions import TruncMonth
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render

from core.utils import admin_required, login_and_active_required
from reporting.utils import (
    dashboard_kpis,
    equipment_utilization_report,
    session_fill_rate_report,
    trainer_utilization_report as _trainer_util_qs,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _current_year_range():
    today = date.today()
    return date(today.year, 1, 1), date(today.year, 12, 31)


def _parse_date_range(request):
    year_start, year_end = _current_year_range()
    try:
        df = request.GET.get("date_from")
        dt = request.GET.get("date_to")
        date_from = date.fromisoformat(df) if df else year_start
        date_to = date.fromisoformat(dt) if dt else year_end
    except ValueError:
        date_from, date_to = year_start, year_end
    return date_from, date_to


def _float(val):
    """Safely cast Decimal/None → float for JSON serialisation."""
    return float(val) if val is not None else 0.0


def _csv_response(filename):
    resp = HttpResponse(content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp.write("\ufeff")  # UTF-8 BOM for Excel
    return resp


def _monthly_revenue(date_from, date_to):
    from financial.utils import revenue_by_month as _fn

    return _fn(date_from, date_to)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@login_and_active_required
def dashboard(request):
    is_admin = hasattr(request.user, "profile") and request.user.profile.is_admin
    today = date.today()

    from formations.models import Session
    from etudes.models import StudyProject

    # ── Date-range filter (admin only) ──────────────────────────────── #
    date_from, date_to = _parse_date_range(request) if is_admin else (None, None)

    ctx = {
        "is_admin": is_admin,
        "upcoming_sessions": (
            Session.objects.filter(status=Session.STATUS_PLANNED, date_start__gte=today)
            .select_related("formation", "trainer", "room")
            .order_by("date_start")[:8]
        ),
        "sessions_in_progress": Session.objects.filter(
            status=Session.STATUS_IN_PROGRESS
        ).select_related("formation", "trainer"),
        "active_projects": (
            StudyProject.objects.filter(status=StudyProject.STATUS_IN_PROGRESS)
            .select_related("client")
            .order_by("end_date")[:8]
        ),
    }

    if is_admin:
        from financial.models import Invoice
        from resources.models import Equipment

        ctx["kpis"] = dashboard_kpis(date_from=date_from, date_to=date_to)
        ctx["date_from"] = date_from
        ctx["date_to"] = date_to
        ctx["unpaid_invoices"] = (
            Invoice.objects.filter(
                status__in=[Invoice.Status.UNPAID, Invoice.Status.PARTIALLY_PAID]
            )
            .select_related("client")
            .order_by("invoice_date")[:8]
        )
        ctx["overdue_invoices_count"] = Invoice.objects.filter(
            status__in=[Invoice.Status.UNPAID, Invoice.Status.PARTIALLY_PAID],
            due_date__lt=today,
        ).count()
        ctx["overdue_projects"] = StudyProject.objects.filter(
            status=StudyProject.STATUS_IN_PROGRESS, end_date__lt=today
        ).select_related("client")[:5]
        ctx["maintenance_due_count"] = sum(
            1
            for e in Equipment.objects.prefetch_related("maintenance_logs")
            if e.is_maintenance_due
        )

    return render(request, "reporting/dashboard.html", ctx)


# ---------------------------------------------------------------------------
# Revenue
# ---------------------------------------------------------------------------


@admin_required
def revenue_summary(request):
    from financial.utils import revenue_summary as _rev

    date_from, date_to = _parse_date_range(request)
    return render(
        request,
        "reporting/revenue_summary.html",
        {
            "summary": _rev(date_from, date_to),
            "summary_formation": _rev(date_from, date_to, invoice_type="formation"),
            "summary_etude": _rev(date_from, date_to, invoice_type="etude"),
            "monthly": _monthly_revenue(date_from, date_to),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def revenue_by_month(request):
    date_from, date_to = _parse_date_range(request)
    return render(
        request,
        "reporting/revenue_by_month.html",
        {
            "monthly": _monthly_revenue(date_from, date_to),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def revenue_by_client(request):
    from financial.utils import top_clients_by_revenue

    date_from, date_to = _parse_date_range(request)
    return render(
        request,
        "reporting/revenue_by_client.html",
        {
            "clients": top_clients_by_revenue(
                limit=20, date_from=date_from, date_to=date_to
            ),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def revenue_by_business_line(request):
    from financial.utils import revenue_summary as _rev

    date_from, date_to = _parse_date_range(request)
    return render(
        request,
        "reporting/revenue_by_business_line.html",
        {
            "summary_formation": _rev(date_from, date_to, invoice_type="formation"),
            "summary_etude": _rev(date_from, date_to, invoice_type="etude"),
            "summary_all": _rev(date_from, date_to),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def cash_flow_report(request):
    """Month-by-month cash collected vs expenses paid, with running balance."""
    from financial.models import Expense, Payment

    date_from, date_to = _parse_date_range(request)

    c_by_month = (
        Payment.objects.filter(
            date__range=[date_from, date_to], status=Payment.Status.CONFIRMED
        )
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("amount"))
    )
    e_by_month = (
        Expense.objects.filter(
            date__range=[date_from, date_to],
            approval_status=Expense.ApprovalStatus.APPROVED,
        )
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("amount"))
    )
    c_map = {r["month"].strftime("%Y-%m"): r["total"] for r in c_by_month}
    e_map = {r["month"].strftime("%Y-%m"): r["total"] for r in e_by_month}
    months = sorted(set(c_map) | set(e_map))

    rows, running = [], Decimal("0")
    for m in months:
        c = c_map.get(m, Decimal("0"))
        e = e_map.get(m, Decimal("0"))
        net = c - e
        running += net
        rows.append(
            {
                "month": m,
                "collected": c,
                "expenses": e,
                "net": net,
                "running_balance": running,
            }
        )

    return render(
        request,
        "reporting/cash_flow.html",
        {
            "rows": rows,
            "total_collected": sum(r["collected"] for r in rows),
            "total_expenses": sum(r["expenses"] for r in rows),
            "net": sum(r["net"] for r in rows),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def collections_report(request):
    """Payments received grouped by method and month."""
    from financial.models import Payment

    date_from, date_to = _parse_date_range(request)
    payments = (
        Payment.objects.filter(
            date__range=[date_from, date_to], status=Payment.Status.CONFIRMED
        )
        .select_related("invoice__client")
        .order_by("-date")
    )
    return render(
        request,
        "reporting/collections.html",
        {
            "payments": payments[:50],
            "by_method": payments.values("method")
            .annotate(count=Count("pk"), total=Sum("amount"))
            .order_by("-total"),
            "by_month": payments.annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(total=Sum("amount"))
            .order_by("month"),
            "grand_total": payments.aggregate(t=Sum("amount"))["t"] or Decimal("0"),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def tva_report(request):
    """TVA collected per business line per period — for tax declarations."""
    from financial.models import Invoice

    date_from, date_to = _parse_date_range(request)
    qs = Invoice.objects.filter(
        invoice_date__range=[date_from, date_to],
        status__in=[
            Invoice.Status.UNPAID,
            Invoice.Status.PARTIALLY_PAID,
            Invoice.Status.PAID,
        ],
    )
    return render(
        request,
        "reporting/tva_report.html",
        {
            "totals": qs.aggregate(
                total_ht=Sum("amount_ht"),
                total_tva=Sum("amount_tva"),
                total_ttc=Sum("amount_ttc"),
                formation_ht=Sum(
                    "amount_ht", filter=Q(invoice_type=Invoice.InvoiceType.FORMATION)
                ),
                formation_tva=Sum(
                    "amount_tva", filter=Q(invoice_type=Invoice.InvoiceType.FORMATION)
                ),
                etude_ht=Sum(
                    "amount_ht", filter=Q(invoice_type=Invoice.InvoiceType.ETUDE)
                ),
                etude_tva=Sum(
                    "amount_tva", filter=Q(invoice_type=Invoice.InvoiceType.ETUDE)
                ),
            ),
            "by_month": qs.annotate(month=TruncMonth("invoice_date"))
            .values("month", "invoice_type")
            .annotate(ht=Sum("amount_ht"), tva=Sum("amount_tva"), ttc=Sum("amount_ttc"))
            .order_by("month"),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


# ---------------------------------------------------------------------------
# Outstanding & aging
# ---------------------------------------------------------------------------


@admin_required
def outstanding_receivables(request):
    from financial.utils import outstanding_invoices
    from financial.models import Invoice

    today = date.today()
    invoices = outstanding_invoices()
    overdue = invoices.filter(due_date__lt=today)

    return render(
        request,
        "reporting/outstanding_receivables.html",
        {
            "invoices": invoices,
            "total_outstanding": invoices.aggregate(t=Sum("amount_remaining"))["t"]
            or Decimal("0"),
            "total_formation": invoices.filter(
                invoice_type=Invoice.InvoiceType.FORMATION
            ).aggregate(t=Sum("amount_remaining"))["t"]
            or Decimal("0"),
            "total_etude": invoices.filter(
                invoice_type=Invoice.InvoiceType.ETUDE
            ).aggregate(t=Sum("amount_remaining"))["t"]
            or Decimal("0"),
            "overdue_invoices": overdue,
            "overdue_total": overdue.aggregate(t=Sum("amount_remaining"))["t"]
            or Decimal("0"),
        },
    )


@admin_required
def invoice_aging_report(request):
    """Classic 0-30 / 31-60 / 61-90 / 90+ day aging buckets."""
    from financial.models import Invoice

    today = date.today()
    unpaid = Invoice.objects.filter(
        status__in=[Invoice.Status.UNPAID, Invoice.Status.PARTIALLY_PAID]
    ).select_related("client")

    buckets = {"current": [], "1_30": [], "31_60": [], "61_90": [], "over_90": []}
    totals = {k: Decimal("0") for k in buckets}

    for inv in unpaid:
        if not inv.due_date or inv.due_date >= today:
            key = "current"
        else:
            days = (today - inv.due_date).days
            key = (
                "1_30"
                if days <= 30
                else "31_60" if days <= 60 else "61_90" if days <= 90 else "over_90"
            )
        buckets[key].append(inv)
        totals[key] += inv.amount_remaining

    return render(
        request,
        "reporting/invoice_aging.html",
        {
            "buckets": buckets,
            "totals": totals,
            "grand_total": sum(totals.values()),
            "today": today,
        },
    )


# ---------------------------------------------------------------------------
# Margins
# ---------------------------------------------------------------------------


@admin_required
def session_margins(request):
    from formations.models import Session
    from financial.utils import session_margin

    date_from, date_to = _parse_date_range(request)
    sessions = (
        Session.objects.filter(
            status=Session.STATUS_COMPLETED,
            date_start__gte=date_from,
            date_end__lte=date_to,
        )
        .select_related("formation", "client", "trainer")
        .order_by("-date_start")
    )
    data = [{"session": s, **session_margin(s)} for s in sessions]
    total_revenue = sum(r["revenue"] for r in data)
    total_expenses = sum(r["expenses"] for r in data)

    return render(
        request,
        "reporting/session_margins.html",
        {
            "data": data,
            "total_revenue": total_revenue,
            "total_expenses": total_expenses,
            "total_margin": total_revenue - total_expenses,
            "avg_margin_rate": (
                round(sum(r["margin_rate"] for r in data) / len(data), 1) if data else 0
            ),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def project_margins(request):
    from etudes.models import StudyProject

    date_from, date_to = _parse_date_range(request)
    projects = (
        StudyProject.objects.filter(
            status=StudyProject.STATUS_COMPLETED,
            actual_end_date__range=[date_from, date_to],
        )
        .select_related("client")
        .order_by("-actual_end_date")
    )
    data = [
        {
            "project": p,
            "budget": p.budget,
            "expenses": p.total_expenses,
            "margin": p.margin,
            "margin_rate": p.margin_rate,
        }
        for p in projects
    ]
    total_budget = sum(r["budget"] for r in data)
    total_expenses = sum(r["expenses"] for r in data)

    return render(
        request,
        "reporting/project_margins.html",
        {
            "data": data,
            "total_budget": total_budget,
            "total_expenses": total_expenses,
            "total_margin": total_budget - total_expenses,
            "avg_margin_rate": (
                round(sum(r["margin_rate"] for r in data) / len(data), 1) if data else 0
            ),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def combined_margin_report(request):
    """Side-by-side Formations vs Études margin for the period."""
    from financial.models import Expense
    from formations.models import Session
    from etudes.models import StudyProject

    date_from, date_to = _parse_date_range(request)

    completed_sessions = Session.objects.filter(
        status=Session.STATUS_COMPLETED, date_start__range=[date_from, date_to]
    )
    formation_revenue = sum(s.total_revenue for s in completed_sessions)
    formation_expenses = Expense.objects.filter(
        date__range=[date_from, date_to],
        allocated_to_session__isnull=False,
        approval_status=Expense.ApprovalStatus.APPROVED,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    completed_projects = StudyProject.objects.filter(
        status=StudyProject.STATUS_COMPLETED,
        actual_end_date__range=[date_from, date_to],
    )
    etude_budget = completed_projects.aggregate(t=Sum("budget"))["t"] or Decimal("0")
    etude_expenses = Expense.objects.filter(
        date__range=[date_from, date_to],
        allocated_to_project__isnull=False,
        approval_status=Expense.ApprovalStatus.APPROVED,
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    fm = formation_revenue - formation_expenses
    em = etude_budget - etude_expenses

    return render(
        request,
        "reporting/combined_margins.html",
        {
            "formation_revenue": formation_revenue,
            "formation_expenses": formation_expenses,
            "formation_margin": fm,
            "formation_margin_rate": (
                round(fm / formation_revenue * 100, 1) if formation_revenue else 0
            ),
            "etude_budget": etude_budget,
            "etude_expenses": etude_expenses,
            "etude_margin": em,
            "etude_margin_rate": (
                round(em / etude_budget * 100, 1) if etude_budget else 0
            ),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------


@admin_required
def expense_breakdown_report(request):
    from financial.models import Expense

    date_from, date_to = _parse_date_range(request)
    allocation_filter = request.GET.get("allocation", "")

    qs = Expense.objects.filter(
        date__range=[date_from, date_to],
        approval_status=Expense.ApprovalStatus.APPROVED,
    ).select_related(
        "category", "allocated_to_session__formation", "allocated_to_project__client"
    )

    # Optional allocation filter
    if allocation_filter == "session":
        qs = qs.filter(allocated_to_session__isnull=False)
    elif allocation_filter == "project":
        qs = qs.filter(allocated_to_project__isnull=False)
    elif allocation_filter == "overhead":
        qs = qs.filter(
            allocated_to_session__isnull=True, allocated_to_project__isnull=True
        )

    # ── Totals ──────────────────────────────────────────────────── #
    totals_raw = qs.aggregate(
        total=Sum("amount"),
        session_total=Sum("amount", filter=Q(allocated_to_session__isnull=False)),
        session_count=Count("pk", filter=Q(allocated_to_session__isnull=False)),
        project_total=Sum("amount", filter=Q(allocated_to_project__isnull=False)),
        project_count=Count("pk", filter=Q(allocated_to_project__isnull=False)),
        overhead_total=Sum(
            "amount",
            filter=Q(
                allocated_to_session__isnull=True,
                allocated_to_project__isnull=True,
            ),
        ),
        overhead_count=Count(
            "pk",
            filter=Q(
                allocated_to_session__isnull=True,
                allocated_to_project__isnull=True,
            ),
        ),
        grand_count=Count("pk"),
    )
    # Coerce Decimal → float for JS serialisation
    for key in ("total", "session_total", "project_total", "overhead_total"):
        totals_raw[key] = float(totals_raw[key] or 0)

    def _safe_avg(total_key, count_key):
        c = totals_raw.get(count_key) or 0
        return round(totals_raw[total_key] / c, 2) if c else 0.0

    totals = {
        **totals_raw,
        "session_avg": _safe_avg("session_total", "session_count"),
        "project_avg": _safe_avg("project_total", "project_count"),
        "overhead_avg": _safe_avg("overhead_total", "overhead_count"),
        "avg": _safe_avg("total", "grand_count"),
    }

    # ── Per-allocation monthly breakdown ────────────────────────── #
    # Build three separate month→total maps, then merge
    def _month_map(extra_filter):
        return {
            r["month"].strftime("%m/%Y"): float(r["total"] or 0)
            for r in qs.filter(extra_filter)
            .annotate(month=TruncMonth("date"))
            .values("month")
            .annotate(total=Sum("amount"))
        }

    s_map = _month_map(Q(allocated_to_session__isnull=False))
    p_map = _month_map(Q(allocated_to_project__isnull=False))
    oh_map = _month_map(
        Q(allocated_to_session__isnull=True, allocated_to_project__isnull=True)
    )

    all_months = sorted(set(s_map) | set(p_map) | set(oh_map))
    by_month = [
        {
            "m": m,
            "s": s_map.get(m, 0.0),
            "p": p_map.get(m, 0.0),
            "oh": oh_map.get(m, 0.0),
            "t": s_map.get(m, 0.0) + p_map.get(m, 0.0) + oh_map.get(m, 0.0),
        }
        for m in all_months
    ]

    # ── Per-allocation summary for the table ────────────────────── #
    grand = totals["total"] or 1  # avoid division by zero
    allocation_summary = [
        {
            "label": "Sessions",
            "color": "#f59e0b",
            "total": totals["session_total"],
            "pct": round(totals["session_total"] / grand * 100),
        },
        {
            "label": "Projets d'étude",
            "color": "#3b82f6",
            "total": totals["project_total"],
            "pct": round(totals["project_total"] / grand * 100),
        },
        {
            "label": "Frais généraux",
            "color": "#94a3b8",
            "total": totals["overhead_total"],
            "pct": round(totals["overhead_total"] / grand * 100),
        },
    ]

    return render(
        request,
        "reporting/expense_breakdown.html",
        {
            "expenses": qs.order_by("-date")[:100],
            "totals": totals,
            "by_month": by_month,
            "allocation_summary": allocation_summary,
            "date_from": date_from,
            "date_to": date_to,
            "allocation_filter": allocation_filter,
            "expense_count": qs.count(),
        },
    )


@admin_required
def expense_by_category(request):
    from financial.models import Expense

    date_from, date_to = _parse_date_range(request)
    base_qs = Expense.objects.filter(
        date__range=[date_from, date_to],
        approval_status=Expense.ApprovalStatus.APPROVED,
    )

    by_cat = (
        base_qs.values("category__name")
        .annotate(count=Count("pk"), total=Sum("amount"), avg=Avg("amount"))
        .order_by("-total")
    )
    grand_total = sum(r["total"] for r in by_cat)
    rows = [
        {**r, "pct": round(r["total"] / grand_total * 100, 1) if grand_total else 0}
        for r in by_cat
    ]

    # ── Monthly trend (top 5 categories) ──────────────────────────── #
    top5_cats = [r["category__name"] for r in rows[:5]]
    monthly_raw = (
        base_qs.filter(category__name__in=top5_cats)
        .annotate(month=TruncMonth("date"))
        .values("month", "category__name")
        .annotate(total=Sum("amount"))
        .order_by("month")
    )

    months_set = sorted({r["month"] for r in monthly_raw})
    pivot = {cat: {} for cat in top5_cats}
    for r in monthly_raw:
        m = r["month"].strftime("%Y-%m")
        cat = r["category__name"]
        if cat in pivot:
            pivot[cat][m] = float(r["total"] or 0)

    trend_months = [m.strftime("%Y-%m") for m in months_set]
    trend_series = [
        {
            "label": cat,
            "values": [pivot[cat].get(m, 0.0) for m in trend_months],
        }
        for cat in top5_cats
    ]

    return render(
        request,
        "reporting/expense_by_category.html",
        {
            "rows": rows,
            "grand_total": grand_total,
            "date_from": date_from,
            "date_to": date_to,
            "trend_months": trend_months,
            "trend_series": trend_series,
        },
    )


@admin_required
def pending_expenses_report(request):
    from datetime import date
    from financial.models import Expense

    pending_qs = Expense.objects.filter(
        Q(approval_status=Expense.ApprovalStatus.PENDING) | Q(receipt_missing=True)
    )

    expenses = pending_qs.select_related(
        "category",
        "beneficiary",
        "allocated_to_session__formation",
        "allocated_to_project",
    ).order_by("-date")

    # ── KPI counts ──────────────────────────────────────────────── #
    agg = pending_qs.aggregate(
        total=Sum("amount"),
        pending_approval_count=Count(
            "pk", filter=Q(approval_status=Expense.ApprovalStatus.PENDING)
        ),
        pending_approval_total=Sum(
            "amount", filter=Q(approval_status=Expense.ApprovalStatus.PENDING)
        ),
        missing_receipt_count=Count("pk", filter=Q(receipt_missing=True)),
        missing_receipt_total=Sum("amount", filter=Q(receipt_missing=True)),
        both_issues_count=Count(
            "pk",
            filter=Q(
                approval_status=Expense.ApprovalStatus.PENDING, receipt_missing=True
            ),
        ),
    )

    # ── By category ──────────────────────────────────────────────── #
    pending_by_category = (
        pending_qs.values("category__name")
        .annotate(count=Count("pk"), total=Sum("amount"))
        .order_by("-total")
    )

    # ── By allocation ────────────────────────────────────────────── #
    alloc = pending_qs.aggregate(
        session=Sum("amount", filter=Q(allocated_to_session__isnull=False)),
        project=Sum("amount", filter=Q(allocated_to_project__isnull=False)),
        overhead=Sum(
            "amount",
            filter=Q(
                allocated_to_session__isnull=True, allocated_to_project__isnull=True
            ),
        ),
    )

    # ── Aging buckets ────────────────────────────────────────────── #
    today = date.today()
    from datetime import timedelta

    buckets_def = [
        ("< 7 jours", today - timedelta(days=7), today),
        ("7–14 jours", today - timedelta(days=14), today - timedelta(days=7)),
        ("15–30 jours", today - timedelta(days=30), today - timedelta(days=14)),
        ("31–60 jours", today - timedelta(days=60), today - timedelta(days=30)),
        ("> 60 jours", date(2000, 1, 1), today - timedelta(days=60)),
    ]
    aging_buckets = []
    for label, d_from, d_to in buckets_def:
        r = pending_qs.filter(date__gte=d_from, date__lte=d_to).aggregate(
            count=Count("pk"), total=Sum("amount")
        )
        if r["count"]:
            aging_buckets.append(
                {
                    "label": label,
                    "count": r["count"],
                    "total": r["total"] or Decimal("0"),
                }
            )

    return render(
        request,
        "reporting/pending_expenses.html",
        {
            "expenses": expenses,
            "total_pending": agg["total"] or Decimal("0"),
            "pending_approval_count": agg["pending_approval_count"] or 0,
            "pending_approval_total": agg["pending_approval_total"] or Decimal("0"),
            "missing_receipt_count": agg["missing_receipt_count"] or 0,
            "missing_receipt_total": agg["missing_receipt_total"] or Decimal("0"),
            "both_issues_count": agg["both_issues_count"] or 0,
            "pending_by_category": pending_by_category,
            "alloc_session_total": alloc["session"] or Decimal("0"),
            "alloc_project_total": alloc["project"] or Decimal("0"),
            "alloc_overhead_total": alloc["overhead"] or Decimal("0"),
            "aging_buckets": aging_buckets,
        },
    )


# ---------------------------------------------------------------------------
# Formations
# ---------------------------------------------------------------------------


@admin_required
def sessions_report(request):
    from formations.models import Session

    date_from, date_to = _parse_date_range(request)
    sessions = (
        Session.objects.filter(date_start__gte=date_from, date_end__lte=date_to)
        .select_related("formation", "client", "trainer")
        .annotate(participants_ann=Count("participants"))
        .order_by("-date_start")
    )
    return render(
        request,
        "reporting/sessions_report.html",
        {
            "sessions": sessions,
            "by_status": sessions.values("status").annotate(count=Count("pk")),
            "total": sessions.count(),
            "total_participants": sum(s.participants_ann for s in sessions),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def fill_rate_report(request):
    date_from, date_to = _parse_date_range(request)
    sessions = session_fill_rate_report(date_from=date_from, date_to=date_to)
    count = sessions.count()
    avg_fill = round(sum(s.fill_pct or 0 for s in sessions) / count, 1) if count else 0

    return render(
        request,
        "reporting/fill_rate_report.html",
        {
            "sessions": sessions,
            "avg_fill": avg_fill,
            "under_filled_count": sum(1 for s in sessions if (s.fill_pct or 0) < 50),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def catalog_performance(request):
    """Per-formation: sessions, participants, revenue, avg fill rate."""
    from formations.models import Formation, Session

    date_from, date_to = _parse_date_range(request)
    formations = Formation.objects.annotate(
        session_count_ann=Count(
            "sessions",
            filter=Q(
                sessions__date_start__gte=date_from, sessions__date_end__lte=date_to
            ),
        ),
        total_participants=Count(
            "sessions__participants",
            filter=Q(
                sessions__date_start__gte=date_from,
                sessions__date_end__lte=date_to,
                sessions__status=Session.STATUS_COMPLETED,
            ),
        ),
    ).order_by("-session_count_ann")

    data = []
    for f in formations:
        completed = f.sessions.filter(
            status=Session.STATUS_COMPLETED,
            date_start__gte=date_from,
            date_end__lte=date_to,
        )
        cnt = completed.count()
        data.append(
            {
                "formation": f,
                "session_count": f.session_count_ann,
                "total_participants": f.total_participants,
                "revenue": sum(s.total_revenue for s in completed),
                "avg_fill": (
                    round(sum(s.fill_rate for s in completed) / cnt, 1) if cnt else 0
                ),
            }
        )
    data.sort(key=lambda x: x["revenue"], reverse=True)

    return render(
        request,
        "reporting/catalog_performance.html",
        {
            "data": data,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def completion_rate_report(request):
    """Enrolled vs present vs attestation issued per completed session."""
    from formations.models import Session

    date_from, date_to = _parse_date_range(request)
    sessions = (
        Session.objects.filter(
            status=Session.STATUS_COMPLETED,
            date_start__gte=date_from,
            date_end__lte=date_to,
        )
        .select_related("formation")
        .annotate(
            enrolled=Count("participants"),
            attended=Count("participants", filter=Q(participants__attended=True)),
            with_attestation=Count(
                "attestations", filter=Q(attestations__is_issued=True)
            ),
        )
        .order_by("-date_start")
    )
    te, ta, tatt = (
        sum(s.enrolled for s in sessions),
        sum(s.attended for s in sessions),
        sum(s.with_attestation for s in sessions),
    )

    return render(
        request,
        "reporting/completion_rates.html",
        {
            "sessions": sessions,
            "total_enrolled": te,
            "total_attended": ta,
            "total_attested": tatt,
            "attendance_rate": round(ta / te * 100, 1) if te else 0,
            "attestation_rate": round(tatt / ta * 100, 1) if ta else 0,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def attestation_report(request):
    from formations.models import Attestation

    date_from, date_to = _parse_date_range(request)
    today = date.today()
    attestations = (
        Attestation.objects.filter(
            issue_date__range=[date_from, date_to], is_issued=True
        )
        .select_related(
            "participant__session__formation", "participant__session__client"
        )
        .order_by("-issue_date")
    )
    return render(
        request,
        "reporting/attestation_report.html",
        {
            "attestations": attestations,
            "total": attestations.count(),
            "expiring_soon": Attestation.objects.filter(
                is_issued=True, valid_until__range=[today, today + timedelta(days=90)]
            ).select_related("participant__session__formation"),
            "expired_count": Attestation.objects.filter(
                is_issued=True, valid_until__lt=today
            ).count(),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def formation_category_breakdown(request):
    from formations.models import FormationCategory, Session

    date_from, date_to = _parse_date_range(request)
    categories = FormationCategory.objects.annotate(
        session_count=Count(
            "formations__sessions",
            filter=Q(
                formations__sessions__date_start__gte=date_from,
                formations__sessions__date_end__lte=date_to,
            ),
        ),
        participant_count=Count(
            "formations__sessions__participants",
            filter=Q(
                formations__sessions__date_start__gte=date_from,
                formations__sessions__date_end__lte=date_to,
                formations__sessions__status=Session.STATUS_COMPLETED,
            ),
        ),
        formation_count=Count("formations", distinct=True),
    ).order_by("-session_count")

    return render(
        request,
        "reporting/category_breakdown.html",
        {
            "categories": categories,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def formation_monthly_volume(request):
    from formations.models import Session

    date_from, date_to = _parse_date_range(request)
    by_month = (
        Session.objects.filter(
            date_start__range=[date_from, date_to],
            status__in=[Session.STATUS_COMPLETED, Session.STATUS_IN_PROGRESS],
        )
        .annotate(month=TruncMonth("date_start"))
        .values("month")
        .annotate(session_count=Count("pk"), participant_count=Count("participants"))
        .order_by("month")
    )
    return render(
        request,
        "reporting/formation_monthly_volume.html",
        {
            "by_month": by_month,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


# ---------------------------------------------------------------------------
# Trainers
# ---------------------------------------------------------------------------


@admin_required
def trainer_utilization_report(request):
    date_from, date_to = _parse_date_range(request)
    return render(
        request,
        "reporting/trainer_utilization.html",
        {
            "trainers": _trainer_util_qs(date_from=date_from, date_to=date_to),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def trainer_cost_analysis(request):
    """Trainer fees vs revenue generated — contribution per trainer."""
    from formations.models import Trainer, Session

    date_from, date_to = _parse_date_range(request)
    trainers = Trainer.objects.filter(is_active=True).prefetch_related("sessions")

    data = []
    for t in trainers:
        period_sessions = t.sessions.filter(
            date_start__gte=date_from,
            date_end__lte=date_to,
            status=Session.STATUS_COMPLETED,
        )
        total_days = sum((s.date_end - s.date_start).days + 1 for s in period_sessions)
        gross_cost = total_days * t.daily_rate
        # IRG is an additional org charge paid to the State on top of trainer fee
        irg_rate = Decimal("0")
        try:
            irg_rate = t.beneficiary.irg_rate
        except Exception:
            pass
        irg_amount = (gross_cost * irg_rate).quantize(Decimal("0.01"))
        cost = gross_cost + irg_amount  # true total cost to the organization
        revenue = sum(s.total_revenue for s in period_sessions)
        data.append(
            {
                "trainer": t,
                "sessions": period_sessions.count(),
                "total_days": total_days,
                "gross_cost": gross_cost,
                "irg_amount": irg_amount,
                "cost": cost,
                "revenue": revenue,
                "contribution": revenue - cost,
            }
        )
    data.sort(key=lambda x: x["contribution"], reverse=True)

    return render(
        request,
        "reporting/trainer_cost_analysis.html",
        {
            "data": data,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------


@admin_required
def top_clients_report(request):
    from financial.utils import top_clients_by_revenue

    date_from, date_to = _parse_date_range(request)
    return render(
        request,
        "reporting/top_clients.html",
        {
            "clients": top_clients_by_revenue(
                limit=int(request.GET.get("limit", 10)),
                date_from=date_from,
                date_to=date_to,
            ),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def client_activity_report(request):
    """All active clients with last activity and service mix."""
    from clients.models import Client

    clients = (
        Client.objects.filter(is_active=True)
        .annotate(
            session_count=Count("sessions", distinct=True),
            project_count=Count("study_projects", distinct=True),
            invoice_count=Count("invoices", distinct=True),
            last_session=Max("sessions__date_start"),
            last_project=Max("study_projects__start_date"),
            last_invoice=Max("invoices__invoice_date"),
        )
        .order_by("name")
    )

    return render(request, "reporting/client_activity.html", {"clients": clients})


@admin_required
def client_retention_report(request):
    """YoY retention: identifies churned, new, and retained clients."""
    from clients.models import Client

    today = date.today()
    curr_start = date(today.year, 1, 1)
    prev_start = date(today.year - 1, 1, 1)
    prev_end = date(today.year - 1, 12, 31)

    last_year_ids = set(
        Client.objects.filter(
            Q(sessions__date_start__range=[prev_start, prev_end])
            | Q(study_projects__start_date__range=[prev_start, prev_end])
        ).values_list("pk", flat=True)
    )

    this_year_ids = set(
        Client.objects.filter(
            Q(sessions__date_start__gte=curr_start)
            | Q(study_projects__start_date__gte=curr_start)
        ).values_list("pk", flat=True)
    )

    churned_ids = last_year_ids - this_year_ids
    retained_ids = last_year_ids & this_year_ids

    return render(
        request,
        "reporting/client_retention.html",
        {
            "churned": Client.objects.filter(pk__in=churned_ids),
            "new_clients": Client.objects.filter(pk__in=this_year_ids - last_year_ids),
            "retained": Client.objects.filter(pk__in=retained_ids),
            "retention_rate": (
                round(len(retained_ids) / len(last_year_ids) * 100, 1)
                if last_year_ids
                else 0
            ),
            "current_year": today.year,
        },
    )


@admin_required
def inactive_clients_report(request):
    """Active clients with no activity in the last N months."""
    from clients.models import Client

    months = int(request.GET.get("months", 12))
    cutoff = date.today() - timedelta(days=months * 30)

    inactive = (
        Client.objects.filter(is_active=True)
        .exclude(
            Q(sessions__date_start__gte=cutoff)
            | Q(study_projects__start_date__gte=cutoff)
            | Q(invoices__invoice_date__gte=cutoff)
        )
        .annotate(
            last_session=Max("sessions__date_start"),
            last_project=Max("study_projects__start_date"),
            last_invoice=Max("invoices__invoice_date"),
        )
        .distinct()
        .order_by("name")
    )

    return render(
        request,
        "reporting/inactive_clients.html",
        {
            "clients": inactive,
            "months": months,
            "cutoff": cutoff,
        },
    )


# ---------------------------------------------------------------------------
# Projects (Études)
# ---------------------------------------------------------------------------


@admin_required
def project_overview_report(request):
    from etudes.models import StudyProject

    date_from, date_to = _parse_date_range(request)
    projects = (
        StudyProject.objects.filter(start_date__gte=date_from)
        .select_related("client")
        .order_by("status", "end_date")
    )

    return render(
        request,
        "reporting/project_overview.html",
        {
            "projects": projects,
            "by_status": projects.values("status").annotate(
                count=Count("pk"), total_budget=Sum("budget")
            ),
            "total_budget": projects.aggregate(t=Sum("budget"))["t"] or Decimal("0"),
            "overdue": [p for p in projects if p.is_overdue],
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def project_delivery_report(request):
    """On-time vs late delivery analysis for completed projects."""
    from etudes.models import StudyProject

    date_from, date_to = _parse_date_range(request)
    completed = StudyProject.objects.filter(
        status=StudyProject.STATUS_COMPLETED,
        actual_end_date__range=[date_from, date_to],
    ).select_related("client")

    on_time, late = [], []
    for p in completed:
        if p.end_date and p.actual_end_date:
            if p.actual_end_date <= p.end_date:
                on_time.append(p)
            else:
                late.append(
                    {"project": p, "days_late": (p.actual_end_date - p.end_date).days}
                )

    total = len(on_time) + len(late)
    return render(
        request,
        "reporting/project_delivery.html",
        {
            "on_time": on_time,
            "late": late,
            "on_time_rate": round(len(on_time) / total * 100, 1) if total else 0,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def project_phase_report(request):
    """Phase completion stats across all active projects."""
    from etudes.models import ProjectPhase

    phases = ProjectPhase.objects.select_related("project__client").all()
    return render(
        request,
        "reporting/project_phases.html",
        {
            "by_status": phases.values("status").annotate(count=Count("pk")),
            "overdue_phases": [ph for ph in phases if ph.is_overdue],
            "blocked_phases": phases.filter(status=ProjectPhase.STATUS_BLOCKED),
            "total_phases": phases.count(),
        },
    )


# ---------------------------------------------------------------------------
# Equipment & Rooms
# ---------------------------------------------------------------------------


@admin_required
def equipment_report(request):
    from resources.utils import equipment_maintenance_due_list, equipment_idle_list

    return render(
        request,
        "reporting/equipment_report.html",
        {
            "equipment_list": equipment_utilization_report(),
            "maintenance_due": equipment_maintenance_due_list(),
            "idle_equipment": equipment_idle_list(),
        },
    )


@admin_required
def equipment_roi_report(request):
    from resources.utils import compute_cost_per_use_ranking

    ranked = compute_cost_per_use_ranking()
    return render(
        request,
        "reporting/equipment_roi.html",
        {
            "equipment_list": ranked,
            "total_purchase": sum(e.purchase_cost for e in ranked),
            "total_maintenance": sum(e.total_maintenance_cost for e in ranked),
            "total_cost": sum(e.total_cost_of_ownership for e in ranked),
        },
    )


@admin_required
def maintenance_cost_report(request):
    from resources.models import MaintenanceLog

    date_from, date_to = _parse_date_range(request)
    logs = (
        MaintenanceLog.objects.filter(date__range=[date_from, date_to])
        .select_related("equipment")
        .order_by("-date")
    )

    return render(
        request,
        "reporting/maintenance_costs.html",
        {
            "logs": logs[:50],
            "by_type": logs.values("maintenance_type").annotate(
                count=Count("pk"), total=Sum("cost")
            ),
            "by_equipment": logs.values("equipment__name", "equipment__category")
            .annotate(count=Count("pk"), total=Sum("cost"))
            .order_by("-total"),
            "grand_total": logs.aggregate(t=Sum("cost"))["t"] or Decimal("0"),
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@admin_required
def room_occupancy_report(request):
    from formations.models import TrainingRoom

    date_from, date_to = _parse_date_range(request)
    period_days = (date_to - date_from).days + 1
    rooms = (
        TrainingRoom.objects.filter(is_active=True)
        .annotate(
            period_sessions=Count(
                "sessions",
                filter=Q(
                    sessions__date_start__gte=date_from, sessions__date_end__lte=date_to
                ),
            )
        )
        .order_by("-period_sessions")
    )

    data = []
    for room in rooms:
        sessions = room.sessions.filter(
            date_start__gte=date_from, date_end__lte=date_to
        )
        booked_days = sum((s.date_end - s.date_start).days + 1 for s in sessions)
        data.append(
            {
                "room": room,
                "session_count": room.period_sessions,
                "booked_days": booked_days,
                "occupancy_rate": round(booked_days / period_days * 100, 1),
            }
        )

    return render(
        request,
        "reporting/room_occupancy.html",
        {
            "data": data,
            "period_days": period_days,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


# ---------------------------------------------------------------------------
# CSV Exports
# ---------------------------------------------------------------------------


@admin_required
def export_invoices_csv(request):
    from financial.models import Invoice

    date_from, date_to = _parse_date_range(request)
    resp = _csv_response(f"factures_{date_from}_{date_to}.csv")
    w = csv.writer(resp)
    w.writerow(
        [
            "Référence",
            "Date",
            "Client",
            "Type",
            "Statut",
            "Montant HT",
            "TVA",
            "Montant TTC",
            "Reste à payer",
        ]
    )
    for inv in (
        Invoice.objects.filter(invoice_date__range=[date_from, date_to])
        .select_related("client")
        .order_by("-invoice_date")
    ):
        w.writerow(
            [
                inv.reference,
                inv.invoice_date,
                inv.client.name,
                inv.get_invoice_type_display(),
                inv.get_status_display(),
                inv.amount_ht,
                inv.amount_tva,
                inv.amount_ttc,
                inv.amount_remaining,
            ]
        )
    return resp


@admin_required
def export_payments_csv(request):
    from financial.models import Payment

    date_from, date_to = _parse_date_range(request)
    resp = _csv_response(f"paiements_{date_from}_{date_to}.csv")
    w = csv.writer(resp)
    w.writerow(["Date", "Facture", "Client", "Montant", "Méthode", "Statut"])
    for p in (
        Payment.objects.filter(date__range=[date_from, date_to])
        .select_related("invoice__client")
        .order_by("-date")
    ):
        w.writerow(
            [
                p.date,
                p.invoice.reference,
                p.invoice.client.name,
                p.amount,
                p.get_payment_method_display(),
                p.get_status_display(),
            ]
        )
    return resp


@admin_required
def export_expenses_csv(request):
    from financial.models import Expense

    date_from, date_to = _parse_date_range(request)
    resp = _csv_response(f"depenses_{date_from}_{date_to}.csv")
    w = csv.writer(resp)
    w.writerow(
        [
            "Date",
            "Catégorie",
            "Montant prestataire (DA)",
            "Taux IRG",
            "IRG versé à l'État (DA)",
            "Coût total organisme (DA)",
            "Description",
            "Affectation",
            "Statut",
            "Justificatif manquant",
        ]
    )
    for e in (
        Expense.objects.filter(date__range=[date_from, date_to])
        .select_related("category")
        .order_by("-date")
    ):
        aff = (
            f"Session: {e.allocated_to_session}"
            if e.allocated_to_session
            else (
                f"Projet: {e.allocated_to_project}"
                if e.allocated_to_project
                else "Frais généraux"
            )
        )
        w.writerow(
            [
                e.date,
                e.category.name if e.category else "",
                e.gross_amount or e.amount,
                f"{float(e.irg_rate) * 100:.0f}%" if e.irg_rate else "0%",
                e.irg_amount,
                e.amount,
                e.description,
                aff,
                e.get_approval_status_display(),
                "Oui" if e.receipt_missing else "Non",
            ]
        )
    return resp


@admin_required
def export_participants_csv(request):
    from formations.models import Participant

    date_from, date_to = _parse_date_range(request)
    resp = _csv_response(f"participants_{date_from}_{date_to}.csv")
    w = csv.writer(resp)
    w.writerow(
        [
            "Session",
            "Formation",
            "Date début",
            "Date fin",
            "Prénom",
            "Nom",
            "Employeur",
            "Email",
            "Téléphone",
            "Fonction",
            "Présent",
            "Attestation",
        ]
    )
    for p in (
        Participant.objects.filter(session__date_start__range=[date_from, date_to])
        .select_related("session__formation")
        .order_by("session__date_start", "last_name")
    ):
        w.writerow(
            [
                str(p.session),
                p.session.formation.title,
                p.session.date_start,
                p.session.date_end,
                p.first_name,
                p.last_name,
                p.employer,
                p.email,
                p.phone,
                p.job_title,
                "Oui" if p.attended else "Non",
                "Oui" if p.has_attestation else "Non",
            ]
        )
    return resp


@admin_required
def export_attestations_csv(request):
    from formations.models import Attestation

    date_from, date_to = _parse_date_range(request)
    resp = _csv_response(f"attestations_{date_from}_{date_to}.csv")
    w = csv.writer(resp)
    w.writerow(
        [
            "Référence",
            "Formation",
            "Participant",
            "Employeur",
            "Date d'émission",
            "Valide jusqu'au",
            "Expirée",
        ]
    )
    for a in (
        Attestation.objects.filter(
            issue_date__range=[date_from, date_to], is_issued=True
        )
        .select_related("participant", "session__formation")
        .order_by("-issue_date")
    ):
        w.writerow(
            [
                a.reference,
                a.session.formation.title,
                a.participant.full_name,
                a.participant.employer,
                a.issue_date,
                a.valid_until,
                "Oui" if a.is_expired else "Non",
            ]
        )
    return resp


@admin_required
def export_clients_csv(request):
    from clients.models import Client

    resp = _csv_response("clients.csv")
    w = csv.writer(resp)
    w.writerow(
        [
            "Nom",
            "Type",
            "Ville",
            "Secteur",
            "Téléphone",
            "Email",
            "RC",
            "NIF",
            "NIS",
            "Actif",
            "Solde impayé",
        ]
    )
    for c in Client.objects.all().order_by("name"):
        w.writerow(
            [
                c.name,
                c.get_client_type_display(),
                c.city,
                c.activity_sector,
                c.phone,
                c.email,
                c.registration_number,
                c.nif,
                c.nis,
                "Oui" if c.is_active else "Non",
                c.outstanding_balance,
            ]
        )
    return resp


# ---------------------------------------------------------------------------
# Chart / AJAX data feeds
# ---------------------------------------------------------------------------


@admin_required
def chart_revenue_trend(request):
    date_from, date_to = _parse_date_range(request)
    monthly = _monthly_revenue(date_from, date_to)
    return JsonResponse(
        {
            "data": [
                {
                    "month": r["month"],
                    "formation_ht": _float(r["formation_ht"]),
                    "etude_ht": _float(r["etude_ht"]),
                    "total_ht": _float(r["total_ht"]),
                }
                for r in monthly
            ]
        }
    )


@admin_required
def chart_business_line_split(request):
    from financial.utils import revenue_summary as _rev

    date_from, date_to = _parse_date_range(request)
    return JsonResponse(
        {
            "formation_ht": _float(
                _rev(date_from, date_to, invoice_type="formation")["invoiced_ht"]
            ),
            "etude_ht": _float(
                _rev(date_from, date_to, invoice_type="etude")["invoiced_ht"]
            ),
        }
    )


@admin_required
def chart_payment_status(request):
    from financial.models import Invoice

    data = (
        Invoice.objects.values("status")
        .annotate(count=Count("pk"), total=Sum("amount_ttc"))
        .order_by("status")
    )
    return JsonResponse(
        {
            "data": [
                {
                    "status": r["status"],
                    "count": r["count"],
                    "total": _float(r["total"]),
                }
                for r in data
            ]
        }
    )


@admin_required
def chart_session_fill_rates(request):
    from formations.models import Session

    sessions = (
        Session.objects.filter(
            status__in=[Session.STATUS_COMPLETED, Session.STATUS_PLANNED]
        )
        .select_related("formation")
        .annotate(
            p_count=Count("participants"),
            fill_pct=ExpressionWrapper(
                Count("participants") * 100.0 / F("capacity"), output_field=FloatField()
            ),
        )
        .order_by("-date_start")[:20]
    )
    return JsonResponse(
        {
            "data": [
                {
                    "label": f"{s.formation.title[:25]} ({s.date_start})",
                    "fill_pct": round(s.fill_pct or 0, 1),
                    "capacity": s.capacity,
                    "enrolled": s.p_count,
                }
                for s in sessions
            ]
        }
    )


@admin_required
def chart_expense_by_category(request):
    from financial.models import Expense

    date_from, date_to = _parse_date_range(request)
    data = (
        Expense.objects.filter(
            date__range=[date_from, date_to],
            approval_status=Expense.ApprovalStatus.APPROVED,
        )
        .values("category__name")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )
    return JsonResponse(
        {
            "data": [
                {"category": r["category__name"] or "—", "total": _float(r["total"])}
                for r in data
            ]
        }
    )


@admin_required
def chart_top_clients(request):
    from financial.utils import top_clients_by_revenue

    date_from, date_to = _parse_date_range(request)
    clients = top_clients_by_revenue(limit=10, date_from=date_from, date_to=date_to)
    return JsonResponse(
        {
            "data": [
                {"name": c.name, "total_paid": _float(c.total_paid)} for c in clients
            ]
        }
    )


@admin_required
def chart_project_status(request):
    from etudes.models import StudyProject

    data = StudyProject.objects.values("status").annotate(count=Count("pk"))
    return JsonResponse(
        {"data": [{"status": r["status"], "count": r["count"]} for r in data]}
    )


@admin_required
def chart_monthly_participants(request):
    from formations.models import Participant

    date_from, date_to = _parse_date_range(request)
    data = (
        Participant.objects.filter(
            session__date_start__range=[date_from, date_to], session__status="completed"
        )
        .annotate(month=TruncMonth("session__date_start"))
        .values("month")
        .annotate(total=Count("pk"), attended=Count("pk", filter=Q(attended=True)))
        .order_by("month")
    )
    return JsonResponse(
        {
            "data": [
                {
                    "month": r["month"].strftime("%Y-%m"),
                    "total": r["total"],
                    "attended": r["attended"],
                }
                for r in data
            ]
        }
    )


@admin_required
def chart_equipment_status(request):
    from resources.models import Equipment

    data = Equipment.objects.values("status").annotate(count=Count("pk"))
    return JsonResponse(
        {"data": [{"status": r["status"], "count": r["count"]} for r in data]}
    )


@admin_required
def chart_trainer_workload(request):
    from formations.models import Trainer, Session

    date_from, date_to = _parse_date_range(request)
    trainers = (
        Trainer.objects.filter(is_active=True)
        .annotate(
            period_sessions=Count(
                "sessions",
                filter=Q(
                    sessions__date_start__gte=date_from,
                    sessions__date_end__lte=date_to,
                    sessions__status=Session.STATUS_COMPLETED,
                ),
            )
        )
        .order_by("-period_sessions")[:10]
    )
    return JsonResponse(
        {
            "data": [
                {"name": t.full_name, "sessions": t.period_sessions} for t in trainers
            ]
        }
    )


@admin_required
def chart_cash_flow(request):
    from financial.models import Expense, Payment

    date_from, date_to = _parse_date_range(request)
    c_map = {
        r["month"].strftime("%Y-%m"): _float(r["total"])
        for r in Payment.objects.filter(
            date__range=[date_from, date_to], status=Payment.Status.CONFIRMED
        )
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("amount"))
    }
    e_map = {
        r["month"].strftime("%Y-%m"): _float(r["total"])
        for r in Expense.objects.filter(
            date__range=[date_from, date_to],
            approval_status=Expense.ApprovalStatus.APPROVED,
        )
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(total=Sum("amount"))
    }
    months = sorted(set(c_map) | set(e_map))
    return JsonResponse(
        {
            "data": [
                {
                    "month": m,
                    "collected": c_map.get(m, 0),
                    "expenses": e_map.get(m, 0),
                    "net": c_map.get(m, 0) - e_map.get(m, 0),
                }
                for m in months
            ]
        }
    )


@admin_required
def chart_formation_category_split(request):
    from formations.models import FormationCategory, Session

    date_from, date_to = _parse_date_range(request)
    cats = FormationCategory.objects.annotate(
        session_count=Count(
            "formations__sessions",
            filter=Q(
                formations__sessions__date_start__gte=date_from,
                formations__sessions__date_end__lte=date_to,
                formations__sessions__status=Session.STATUS_COMPLETED,
            ),
        )
    ).order_by("-session_count")
    return JsonResponse(
        {"data": [{"category": c.name, "sessions": c.session_count} for c in cats]}
    )
