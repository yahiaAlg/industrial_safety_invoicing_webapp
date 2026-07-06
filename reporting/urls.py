# reporting/urls.py

from django.urls import path
from reporting import views

app_name = "reporting"

urlpatterns = [
    # ── Dashboard ────────────────────────────────────────────────────────── #
    path("", views.dashboard, name="dashboard"),
    # ── Revenue & financial KPIs ─────────────────────────────────────────── #
    path("reports/revenue/", views.revenue_summary, name="revenue_summary"),
    path("reports/revenue/by-month/", views.revenue_by_month, name="revenue_by_month"),
    path(
        "reports/revenue/by-client/", views.revenue_by_client, name="revenue_by_client"
    ),
    path(
        "reports/revenue/by-business-line/",
        views.revenue_by_business_line,
        name="revenue_by_business_line",
    ),
    # Cash flow & collections
    path("reports/cash-flow/", views.cash_flow_report, name="cash_flow_report"),
    path("reports/collections/", views.collections_report, name="collections_report"),
    # TVA
    path("reports/tva/", views.tva_report, name="tva_report"),
    # ── Outstanding & aging ──────────────────────────────────────────────── #
    path(
        "reports/outstanding/",
        views.outstanding_receivables,
        name="outstanding_receivables",
    ),
    path("reports/aging/", views.invoice_aging_report, name="invoice_aging_report"),
    # ── Margins ──────────────────────────────────────────────────────────── #
    path("reports/margins/sessions/", views.session_margins, name="session_margins"),
    path("reports/margins/projects/", views.project_margins, name="project_margins"),
    path(
        "reports/margins/combined/",
        views.combined_margin_report,
        name="combined_margin_report",
    ),
    # ── Expenses ─────────────────────────────────────────────────────────── #
    path(
        "reports/expenses/",
        views.expense_breakdown_report,
        name="expense_breakdown_report",
    ),
    path(
        "reports/expenses/by-category/",
        views.expense_by_category,
        name="expense_by_category",
    ),
    path(
        "reports/expenses/pending/",
        views.pending_expenses_report,
        name="pending_expenses_report",
    ),
    # ── Formations ───────────────────────────────────────────────────────── #
    path("reports/sessions/", views.sessions_report, name="sessions_report"),
    path("reports/fill-rates/", views.fill_rate_report, name="fill_rate_report"),
    path(
        "reports/formations/catalog-performance/",
        views.catalog_performance,
        name="catalog_performance",
    ),
    path(
        "reports/formations/completion-rates/",
        views.completion_rate_report,
        name="completion_rate_report",
    ),
    path(
        "reports/formations/attestations/",
        views.attestation_report,
        name="attestation_report",
    ),
    path(
        "reports/formations/category-breakdown/",
        views.formation_category_breakdown,
        name="formation_category_breakdown",
    ),
    path(
        "reports/formations/monthly-volume/",
        views.formation_monthly_volume,
        name="formation_monthly_volume",
    ),
    # ── Trainers ─────────────────────────────────────────────────────────── #
    path(
        "reports/trainer-utilization/",
        views.trainer_utilization_report,
        name="trainer_utilization_report",
    ),
    path(
        "reports/trainers/cost-analysis/",
        views.trainer_cost_analysis,
        name="trainer_cost_analysis",
    ),
    # ── Clients ──────────────────────────────────────────────────────────── #
    path("reports/top-clients/", views.top_clients_report, name="top_clients_report"),
    path(
        "reports/clients/activity/",
        views.client_activity_report,
        name="client_activity_report",
    ),
    path(
        "reports/clients/retention/",
        views.client_retention_report,
        name="client_retention_report",
    ),
    path(
        "reports/clients/inactive/",
        views.inactive_clients_report,
        name="inactive_clients_report",
    ),
    # ── Projects (Études) ────────────────────────────────────────────────── #
    path(
        "reports/projects/overview/",
        views.project_overview_report,
        name="project_overview_report",
    ),
    path(
        "reports/projects/on-time-delivery/",
        views.project_delivery_report,
        name="project_delivery_report",
    ),
    path(
        "reports/projects/phases/",
        views.project_phase_report,
        name="project_phase_report",
    ),
    # ── Equipment & resources ─────────────────────────────────────────────── #
    path("reports/equipment/", views.equipment_report, name="equipment_report"),
    path(
        "reports/equipment/roi/",
        views.equipment_roi_report,
        name="equipment_roi_report",
    ),
    path(
        "reports/equipment/maintenance-costs/",
        views.maintenance_cost_report,
        name="maintenance_cost_report",
    ),
    path(
        "reports/rooms/occupancy/",
        views.room_occupancy_report,
        name="room_occupancy_report",
    ),
    # ── Exports (CSV) ────────────────────────────────────────────────────── #
    path("export/invoices/", views.export_invoices_csv, name="export_invoices_csv"),
    path("export/payments/", views.export_payments_csv, name="export_payments_csv"),
    path("export/expenses/", views.export_expenses_csv, name="export_expenses_csv"),
    path(
        "export/participants/",
        views.export_participants_csv,
        name="export_participants_csv",
    ),
    path(
        "export/attestations/",
        views.export_attestations_csv,
        name="export_attestations_csv",
    ),
    path("export/clients/", views.export_clients_csv, name="export_clients_csv"),
    # ── Chart / AJAX data feeds ───────────────────────────────────────────── #
    path(
        "api/chart/revenue-trend/",
        views.chart_revenue_trend,
        name="chart_revenue_trend",
    ),
    path(
        "api/chart/business-line-split/",
        views.chart_business_line_split,
        name="chart_business_line_split",
    ),
    path(
        "api/chart/payment-status/",
        views.chart_payment_status,
        name="chart_payment_status",
    ),
    path(
        "api/chart/session-fill-rates/",
        views.chart_session_fill_rates,
        name="chart_session_fill_rates",
    ),
    path(
        "api/chart/expense-by-category/",
        views.chart_expense_by_category,
        name="chart_expense_by_category",
    ),
    path("api/chart/top-clients/", views.chart_top_clients, name="chart_top_clients"),
    path(
        "api/chart/project-status/",
        views.chart_project_status,
        name="chart_project_status",
    ),
    path(
        "api/chart/monthly-participants/",
        views.chart_monthly_participants,
        name="chart_monthly_participants",
    ),
    path(
        "api/chart/equipment-status/",
        views.chart_equipment_status,
        name="chart_equipment_status",
    ),
    path(
        "api/chart/trainer-workload/",
        views.chart_trainer_workload,
        name="chart_trainer_workload",
    ),
    path("api/chart/cash-flow/", views.chart_cash_flow, name="chart_cash_flow"),
    path(
        "api/chart/formation-category-split/",
        views.chart_formation_category_split,
        name="chart_formation_category_split",
    ),
]
