# resources/resources.py
# django-import-export resource definitions for the resources app.

from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget

from etudes.models import StudyProject
from formations.models import Session
from resources.models import (
    Equipment,
    EquipmentBooking,
    EquipmentUsage,
    MaintenanceLog,
)


# ---------------------------------------------------------------------------
# Equipment
# ---------------------------------------------------------------------------


class EquipmentResource(resources.ModelResource):
    class Meta:
        model = Equipment
        fields = (
            "id",
            "name",
            "category",
            "serial_number",
            "model_number",
            "supplier",
            "warranty_expiry",
            "purchase_date",
            "purchase_cost",
            "current_value",
            "useful_life_years",
            "condition",
            "status",
            "location",
            "maintenance_interval_days",
            "notes",
        )
        export_order = fields
        import_id_fields = ("serial_number",)
        skip_unchanged = True
        report_skipped = False

    def before_import_row(self, row, row_number=None, **kwargs):
        for col in ("condition", "status"):
            if col in row and row[col]:
                row[col] = str(row[col]).lower().strip()


# ---------------------------------------------------------------------------
# EquipmentUsage
# ---------------------------------------------------------------------------


class EquipmentUsageResource(resources.ModelResource):
    equipment = fields.Field(
        column_name="equipment_id",
        attribute="equipment",
        widget=ForeignKeyWidget(Equipment, field="id"),
    )
    assigned_to_session = fields.Field(
        column_name="session_id",
        attribute="assigned_to_session",
        widget=ForeignKeyWidget(Session, field="id"),
    )
    assigned_to_project = fields.Field(
        column_name="project_id",
        attribute="assigned_to_project",
        widget=ForeignKeyWidget(StudyProject, field="id"),
    )

    class Meta:
        model = EquipmentUsage
        fields = (
            "id",
            "equipment",
            "assigned_to_session",
            "assigned_to_project",
            "date",
            "duration_hours",
            "context",
        )
        export_order = fields
        import_id_fields = ("id",)
        skip_unchanged = True
        report_skipped = False


# ---------------------------------------------------------------------------
# EquipmentBooking
# ---------------------------------------------------------------------------


class EquipmentBookingResource(resources.ModelResource):
    equipment = fields.Field(
        column_name="equipment_id",
        attribute="equipment",
        widget=ForeignKeyWidget(Equipment, field="id"),
    )
    reserved_for_session = fields.Field(
        column_name="session_id",
        attribute="reserved_for_session",
        widget=ForeignKeyWidget(Session, field="id"),
    )
    reserved_for_project = fields.Field(
        column_name="project_id",
        attribute="reserved_for_project",
        widget=ForeignKeyWidget(StudyProject, field="id"),
    )

    class Meta:
        model = EquipmentBooking
        fields = (
            "id",
            "equipment",
            "reserved_for_session",
            "reserved_for_project",
            "date_from",
            "date_to",
            "notes",
        )
        export_order = fields
        import_id_fields = ("id",)
        skip_unchanged = True
        report_skipped = False


# ---------------------------------------------------------------------------
# MaintenanceLog
# ---------------------------------------------------------------------------


class MaintenanceLogResource(resources.ModelResource):
    equipment = fields.Field(
        column_name="equipment_id",
        attribute="equipment",
        widget=ForeignKeyWidget(Equipment, field="id"),
    )

    class Meta:
        model = MaintenanceLog
        fields = (
            "id",
            "equipment",
            "date",
            "maintenance_type",
            "cost",
            "performed_by",
            "description",
            "resolution",
            "next_due_date",
        )
        export_order = fields
        import_id_fields = ("id",)
        skip_unchanged = True
        report_skipped = False

    def before_import_row(self, row, row_number=None, **kwargs):
        if "maintenance_type" in row and row["maintenance_type"]:
            row["maintenance_type"] = str(row["maintenance_type"]).lower().strip()
