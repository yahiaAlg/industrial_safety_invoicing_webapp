# =============================================================================
# formations/admin.py
# =============================================================================

from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from formations.models import (
    Attestation,
    Formation,
    FormationCategory,
    Participant,
    Session,
)
from formations.resources import (
    AttestationResource,
    FormationCategoryResource,
    FormationResource,
    ParticipantResource,
    SessionResource,
)


@admin.register(FormationCategory)
class FormationCategoryAdmin(ImportExportModelAdmin):
    resource_class = FormationCategoryResource

    list_display = ["code", "name", "color"]
    search_fields = ["code", "name"]


class SessionInline(admin.TabularInline):
    model = Session
    extra = 0
    fields = ["date_start", "date_end", "trainer", "room", "status", "capacity"]
    show_change_link = True
    readonly_fields = ["status"]


@admin.register(Formation)
class FormationAdmin(ImportExportModelAdmin):
    resource_class = FormationResource

    list_display = [
        "title",
        "category",
        "duration_days",
        "duration_hours",
        "base_price",
        "max_participants",
        "is_active",
    ]
    list_filter = ["category", "is_active"]
    search_fields = ["title", "description"]
    prepopulated_fields = {"slug": ["title"]}
    inlines = [SessionInline]
    fieldsets = [
        (
            "Catalogue",
            {"fields": ["category", "title", "slug", "description", "is_active"]},
        ),
        (
            "Contenu pédagogique",
            {"fields": ["objectives", "target_audience", "prerequisites"]},
        ),
        (
            "Logistique",
            {
                "fields": [
                    "duration_days",
                    "duration_hours",
                    "base_price",
                    "max_participants",
                    "min_participants",
                ]
            },
        ),
        (
            "Accréditation",
            {"fields": ["accreditation_body", "accreditation_reference"]},
        ),
    ]


class ParticipantInline(admin.TabularInline):
    model = Participant
    extra = 0
    fields = ["first_name", "last_name", "employer", "email", "attended"]


@admin.register(Session)
class SessionAdmin(ImportExportModelAdmin):
    resource_class = SessionResource

    list_display = [
        "formation",
        "client",
        "date_start",
        "date_end",
        "trainer",
        "room",
        "participant_count",
        "capacity",
        "status",
    ]
    list_filter = ["status", "formation__category", "date_start"]
    search_fields = ["formation__title", "client__name", "trainer__last_name"]
    raw_id_fields = ["client", "formation"]
    inlines = [ParticipantInline]
    readonly_fields = ["participant_count", "fill_rate", "attendance_rate"]
    fieldsets = [
        ("Session", {"fields": ["formation", "client", "status"]}),
        (
            "Planification",
            {
                "fields": [
                    "date_start",
                    "date_end",
                    "trainer",
                    "room",
                    "external_location",
                    "capacity",
                    "session_hours",
                ]
            },
        ),
        ("Tarification", {"fields": ["price_per_participant"]}),
        (
            "Statistiques",
            {
                "fields": ["participant_count", "fill_rate", "attendance_rate"],
                "classes": ["collapse"],
            },
        ),
        ("Notes", {"fields": ["notes", "cancellation_reason"]}),
    ]

    @admin.display(description="Participants")
    def participant_count(self, obj):
        return obj.participant_count


@admin.register(Participant)
class ParticipantAdmin(ImportExportModelAdmin):
    resource_class = ParticipantResource

    list_display = ["full_name", "employer", "session", "attended", "has_attestation"]
    list_filter = ["attended", "session__status"]
    search_fields = ["first_name", "last_name", "email", "employer"]
    raw_id_fields = ["session", "employer_client"]

    @admin.display(description="Attestation", boolean=True)
    def has_attestation(self, obj):
        return obj.has_attestation


@admin.register(Attestation)
class AttestationAdmin(ImportExportModelAdmin):
    resource_class = AttestationResource

    list_display = [
        "reference",
        "participant",
        "session",
        "issue_date",
        "valid_until",
        "is_valid",
    ]
    list_filter = ["is_issued"]
    search_fields = ["reference", "participant__first_name", "participant__last_name"]
    readonly_fields = ["reference", "is_valid", "days_until_expiry"]
    raw_id_fields = ["participant", "session"]
