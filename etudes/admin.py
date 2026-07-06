# =============================================================================
# etudes/admin.py
# =============================================================================

from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from etudes.models import ProjectDeliverable, ProjectPhase, StudyProject
from etudes.resources import (
    ProjectDeliverableResource,
    ProjectPhaseResource,
    StudyProjectResource,
)


class ProjectPhaseInline(admin.TabularInline):
    model = ProjectPhase
    extra = 0
    fields = ["order", "name", "status", "due_date", "deliverable"]
    ordering = ["order"]
    show_change_link = True


@admin.register(StudyProject)
class StudyProjectAdmin(ImportExportModelAdmin):
    resource_class = StudyProjectResource

    list_display = [
        "title",
        "client",
        "project_type",
        "start_date",
        "end_date",
        "budget",
        "status",
        "priority",
        "progress_percentage",
    ]
    list_filter = ["status", "priority"]
    search_fields = ["title", "client__name", "project_type", "reference"]
    raw_id_fields = ["client"]
    readonly_fields = [
        "progress_percentage",
        "total_expenses",
        "margin",
        "margin_rate",
        "is_overdue",
    ]
    inlines = [ProjectPhaseInline]
    fieldsets = [
        (
            "Projet",
            {"fields": ["client", "title", "reference", "project_type", "description"]},
        ),
        ("Site", {"fields": ["site_address"]}),
        (
            "Planification",
            {
                "fields": [
                    "start_date",
                    "end_date",
                    "actual_end_date",
                    "status",
                    "priority",
                ]
            },
        ),
        ("Finance", {"fields": ["budget", "total_expenses", "margin", "margin_rate"]}),
        ("Notes", {"fields": ["notes"]}),
    ]


class ProjectDeliverableInline(admin.TabularInline):
    model = ProjectDeliverable
    extra = 0
    fields = ["title", "version", "document", "submission_date", "client_approved"]


@admin.register(ProjectPhase)
class ProjectPhaseAdmin(ImportExportModelAdmin):
    resource_class = ProjectPhaseResource

    list_display = [
        "name",
        "project",
        "order",
        "status",
        "start_date",
        "due_date",
        "is_overdue",
    ]
    list_filter = ["status"]
    search_fields = ["name", "project__title"]
    raw_id_fields = ["project"]
    inlines = [ProjectDeliverableInline]
    readonly_fields = ["is_overdue"]


@admin.register(ProjectDeliverable)
class ProjectDeliverableAdmin(ImportExportModelAdmin):
    resource_class = ProjectDeliverableResource

    list_display = ["title", "phase", "version", "submission_date", "client_approved"]
    list_filter = ["client_approved"]
    search_fields = ["title", "phase__project__title"]
    raw_id_fields = ["phase"]
