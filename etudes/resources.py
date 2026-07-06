# etudes/resources.py
# django-import-export resource definitions for the etudes app.

from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget

from clients.models import Client
from etudes.models import ProjectDeliverable, ProjectPhase, StudyProject


# ---------------------------------------------------------------------------
# StudyProject
# ---------------------------------------------------------------------------


class StudyProjectResource(resources.ModelResource):
    client = fields.Field(
        column_name="client",
        attribute="client",
        widget=ForeignKeyWidget(Client, field="name"),
    )
    client_id = fields.Field(
        column_name="client_id",
        attribute="client",
        widget=ForeignKeyWidget(Client, field="id"),
    )

    class Meta:
        model = StudyProject
        fields = (
            "id",
            "client_id",
            "client",
            "title",
            "reference",
            "description",
            "project_type",
            "site_address",
            "start_date",
            "end_date",
            "actual_end_date",
            "budget",
            "status",
            "priority",
            "notes",
        )
        export_order = fields
        import_id_fields = ("id",)
        skip_unchanged = True
        report_skipped = False

    def before_import_row(self, row, row_number=None, **kwargs):
        for col in ("status", "priority"):
            if col in row and row[col]:
                row[col] = str(row[col]).lower().strip()


# ---------------------------------------------------------------------------
# ProjectPhase
# ---------------------------------------------------------------------------


class ProjectPhaseResource(resources.ModelResource):
    project = fields.Field(
        column_name="project",
        attribute="project",
        widget=ForeignKeyWidget(StudyProject, field="title"),
    )
    project_id = fields.Field(
        column_name="project_id",
        attribute="project",
        widget=ForeignKeyWidget(StudyProject, field="id"),
    )

    class Meta:
        model = ProjectPhase
        fields = (
            "id",
            "project_id",
            "project",
            "name",
            "description",
            "order",
            "status",
            "start_date",
            "due_date",
            "completion_date",
            "estimated_hours",
            "actual_hours",
            "deliverable",
            "notes",
        )
        export_order = fields
        import_id_fields = ("id",)
        skip_unchanged = True
        report_skipped = False


# ---------------------------------------------------------------------------
# ProjectDeliverable
# ---------------------------------------------------------------------------


class ProjectDeliverableResource(resources.ModelResource):
    phase = fields.Field(
        column_name="phase_id",
        attribute="phase",
        widget=ForeignKeyWidget(ProjectPhase, field="id"),
    )

    class Meta:
        model = ProjectDeliverable
        # Note: `document` (FileField) is intentionally excluded from import
        # to avoid file-path conflicts; it can still be exported as a path string.
        fields = (
            "id",
            "phase",
            "title",
            "description",
            "version",
            "submitted_to",
            "submission_date",
            "client_approved",
            "notes",
        )
        export_order = fields
        import_id_fields = ("id",)
        skip_unchanged = True
        report_skipped = False
        exclude = ("document",)
