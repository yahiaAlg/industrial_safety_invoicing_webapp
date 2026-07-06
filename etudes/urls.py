# ============================================================
# etudes/urls.py
# ============================================================

from django.urls import path
from etudes import views

app_name = "etudes"

urlpatterns = [
    # --- Projects ---
    path("", views.project_list, name="project_list"),
    path("create/", views.project_create, name="project_create"),
    path("<int:pk>/", views.project_detail, name="project_detail"),
    path("<int:pk>/print/", views.project_print, name="project_print"),
    path("<int:pk>/edit/", views.project_edit, name="project_edit"),
    path("<int:pk>/close/", views.project_close, name="project_close"),
    path("<int:pk>/cancel/", views.project_cancel, name="project_cancel"),
    # --- Phases ---
    path("<int:project_pk>/phases/add/", views.phase_add, name="phase_add"),
    path("<int:project_pk>/phases/<int:pk>/edit/", views.phase_edit, name="phase_edit"),
    path(
        "<int:project_pk>/phases/<int:pk>/status/",
        views.phase_update_status,
        name="phase_update_status",
    ),
    path(
        "<int:project_pk>/phases/<int:pk>/delete/",
        views.phase_delete,
        name="phase_delete",
    ),
    path(
        "<int:project_pk>/phases/reorder/", views.phase_reorder, name="phase_reorder"
    ),  # JsonResponse POST
    # --- Deliverables ---
    path(
        "<int:project_pk>/phases/<int:phase_pk>/deliverables/add/",
        views.deliverable_add,
        name="deliverable_add",
    ),
    path(
        "<int:project_pk>/phases/<int:phase_pk>/deliverables/<int:pk>/edit/",
        views.deliverable_edit,
        name="deliverable_edit",
    ),
    path(
        "<int:project_pk>/phases/<int:phase_pk>/deliverables/<int:pk>/delete/",
        views.deliverable_delete,
        name="deliverable_delete",
    ),
    path(
        "<int:project_pk>/phases/<int:phase_pk>/deliverables/<int:pk>/approve/",
        views.deliverable_approve,
        name="deliverable_approve",
    ),
    # --- Analytics ---
    path("analytics/", views.etudes_analytics, name="analytics"),
    # ── API (AJAX for invoice line-item prepopulation) ────────────────── #
    path("api/projects/", views.api_project_list, name="api_project_list"),
    path("api/projects/<int:pk>/", views.api_project_detail, name="api_project_detail"),
]
