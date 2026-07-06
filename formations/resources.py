# formations/resources.py
# django-import-export resource definitions for the formations app.

from import_export import fields, resources
from import_export.widgets import BooleanWidget, ForeignKeyWidget

from clients.models import Client
from formations.models import (
    Attestation,
    Formation,
    FormationCategory,
    Participant,
    Session,
    Trainer,
    TrainingRoom,
)

# ---------------------------------------------------------------------------
# FormationCategory
# ---------------------------------------------------------------------------


class FormationCategoryResource(resources.ModelResource):
    class Meta:
        model = FormationCategory
        fields = ("id", "code", "name", "description", "color")
        export_order = fields
        import_id_fields = ("code",)
        skip_unchanged = True
        report_skipped = False


# ---------------------------------------------------------------------------
# Formation
# ---------------------------------------------------------------------------


class FormationResource(resources.ModelResource):
    category = fields.Field(
        column_name="category",
        attribute="category",
        widget=ForeignKeyWidget(FormationCategory, field="code"),
    )

    class Meta:
        model = Formation
        fields = (
            "id",
            "category",
            "title",
            "slug",
            "description",
            "objectives",
            "target_audience",
            "prerequisites",
            "duration_days",
            "duration_hours",
            "base_price",
            "max_participants",
            "min_participants",
            "is_active",
            "accreditation_body",
            "accreditation_reference",
        )
        export_order = fields
        import_id_fields = ("slug",)
        skip_unchanged = True
        report_skipped = False


# ---------------------------------------------------------------------------
# Trainer
# ---------------------------------------------------------------------------


class TrainerResource(resources.ModelResource):
    class Meta:
        model = Trainer
        # CV (FileField) excluded from import to avoid path conflicts.
        fields = (
            "id",
            "first_name",
            "last_name",
            "specialty",
            "trainer_type",
            "daily_rate",
            "monthly_rate",
            "nif",
            "rib",
            "phone",
            "email",
            "certifications",
            "notes",
            "is_active",
        )
        export_order = fields
        import_id_fields = ("id",)
        skip_unchanged = True
        report_skipped = False
        exclude = ("cv",)

    def before_import_row(self, row, row_number=None, **kwargs):
        if "trainer_type" in row and row["trainer_type"]:
            row["trainer_type"] = str(row["trainer_type"]).lower().strip()


# ---------------------------------------------------------------------------
# TrainingRoom
# ---------------------------------------------------------------------------


class TrainingRoomResource(resources.ModelResource):
    class Meta:
        model = TrainingRoom
        fields = (
            "id",
            "name",
            "capacity",
            "location",
            "description",
            "has_projector",
            "has_whiteboard",
            "has_ac",
            "is_active",
        )
        export_order = fields
        import_id_fields = ("name",)
        skip_unchanged = True
        report_skipped = False


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class SessionResource(resources.ModelResource):
    formation = fields.Field(
        column_name="formation",
        attribute="formation",
        widget=ForeignKeyWidget(Formation, field="slug"),
    )
    formation_id = fields.Field(
        column_name="formation_id",
        attribute="formation",
        widget=ForeignKeyWidget(Formation, field="id"),
    )
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
    trainer = fields.Field(
        column_name="trainer_id",
        attribute="trainer",
        widget=ForeignKeyWidget(Trainer, field="id"),
    )
    room = fields.Field(
        column_name="room",
        attribute="room",
        widget=ForeignKeyWidget(TrainingRoom, field="name"),
    )

    class Meta:
        model = Session
        fields = (
            "id",
            "formation_id",
            "formation",
            "client_id",
            "client",
            "date_start",
            "date_end",
            "trainer",
            "room",
            "external_location",
            "capacity",
            "session_hours",
            "price_per_participant",
            "status",
            "notes",
            "cancellation_reason",
        )
        export_order = fields
        import_id_fields = ("id",)
        skip_unchanged = True
        report_skipped = False

    def before_import_row(self, row, row_number=None, **kwargs):
        if "status" in row and row["status"]:
            row["status"] = str(row["status"]).lower().strip()


# ---------------------------------------------------------------------------
# Participant
# ---------------------------------------------------------------------------


class ParticipantResource(resources.ModelResource):
    session = fields.Field(
        column_name="session_id",
        attribute="session",
        widget=ForeignKeyWidget(Session, field="id"),
    )
    employer_client = fields.Field(
        column_name="employer_client_id",
        attribute="employer_client",
        widget=ForeignKeyWidget(Client, field="id"),
    )

    class Meta:
        model = Participant
        fields = (
            "id",
            "session",
            "first_name",
            "last_name",
            "employer",
            "employer_client",
            "phone",
            "email",
            "job_title",
            "attended",
            "notes",
        )
        export_order = fields
        import_id_fields = ("id",)
        skip_unchanged = True
        report_skipped = False


# ---------------------------------------------------------------------------
# Attestation
# ---------------------------------------------------------------------------


class AttestationResource(resources.ModelResource):
    participant = fields.Field(
        column_name="participant_id",
        attribute="participant",
        widget=ForeignKeyWidget(Participant, field="id"),
    )
    session = fields.Field(
        column_name="session_id",
        attribute="session",
        widget=ForeignKeyWidget(Session, field="id"),
    )

    class Meta:
        model = Attestation
        fields = (
            "id",
            "participant",
            "session",
            "reference",
            "issue_date",
            "valid_until",
            "is_issued",
        )
        export_order = fields
        import_id_fields = ("reference",)
        skip_unchanged = True
        report_skipped = False
