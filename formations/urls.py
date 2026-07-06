# ============================================================
# formations/urls.py
# ============================================================

from django.urls import path
from formations import views

app_name = "formations"

urlpatterns = [
    # --- Formation catalog ---
    path("catalog/", views.formation_list, name="formation_list"),
    path("catalog/create/", views.formation_create, name="formation_create"),
    path("catalog/<int:pk>/", views.formation_detail, name="formation_detail"),
    path("catalog/<int:pk>/edit/", views.formation_edit, name="formation_edit"),
    path(
        "catalog/<int:pk>/deactivate/",
        views.formation_deactivate,
        name="formation_deactivate",
    ),
    path(
        "catalog/<int:pk>/sync-capacities/",
        views.formation_sync_capacities,
        name="formation_sync_capacities",
    ),
    # Categories
    path("categories/", views.category_list, name="category_list"),
    path("categories/create/", views.category_create, name="category_create"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category_delete"),
    # --- Sessions ---
    path("sessions/", views.session_list, name="session_list"),
    path("sessions/create/", views.session_create, name="session_create"),
    path("sessions/<int:pk>/", views.session_detail, name="session_detail"),
    path("sessions/<int:pk>/edit/", views.session_edit, name="session_edit"),
    path(
        "sessions/<int:pk>/status/",
        views.session_update_status,
        name="session_update_status",
    ),
    path("sessions/<int:pk>/cancel/", views.session_cancel, name="session_cancel"),
    # --- Participants ---
    path(
        "sessions/<int:session_pk>/participants/add/",
        views.participant_add,
        name="participant_add",
    ),
    path(
        "sessions/<int:session_pk>/participants/<int:pk>/edit/",
        views.participant_edit,
        name="participant_edit",
    ),
    path(
        "sessions/<int:session_pk>/participants/<int:pk>/delete/",
        views.participant_delete,
        name="participant_delete",
    ),
    path(
        "sessions/<int:session_pk>/participants/<int:pk>/attendance/",
        views.participant_toggle_attendance,
        name="participant_toggle_attendance",
    ),
    # --- Attestations ---
    path(
        "sessions/<int:session_pk>/attestations/issue/",
        views.attestation_issue_bulk,
        name="attestation_issue_bulk",
    ),
    path("attestations/<int:pk>/", views.attestation_detail, name="attestation_detail"),
    path(
        "attestations/<int:pk>/print/",
        views.attestation_print,
        name="attestation_print",
    ),
    path(
        "attestations/<int:pk>/revoke/",
        views.attestation_revoke,
        name="attestation_revoke",
    ),
    # --- Analytics ---
    path("analytics/", views.formation_analytics, name="analytics"),
    path("analytics/fill-rates/", views.session_fill_rates, name="fill_rates"),
    path(
        "analytics/trainer-utilization/",
        views.trainer_utilization,
        name="trainer_utilization",
    ),
    # AJAX
    path("sessions/calendar-feed/", views.sessions_calendar_feed, name="calendar_feed"),
    path(
        "sessions/<int:session_pk>/participants/import/",
        views.participant_import,
        name="participant_import",
    ),
    # ── API (AJAX for invoice line-item prepopulation) ────────────────── #
    path("api/formations/", views.api_formation_list, name="api_formation_list"),
    path(
        "api/formations/<int:pk>/",
        views.api_formation_detail,
        name="api_formation_detail",
    ),
]
