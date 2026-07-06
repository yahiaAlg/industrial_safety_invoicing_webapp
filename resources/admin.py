# =============================================================================
# resources/admin.py
# =============================================================================

from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from formations.models import (
    Trainer,
    TrainingRoom,
)
from formations.resources import TrainerResource, TrainingRoomResource
from resources.models import (
    Equipment,
    EquipmentBooking,
    EquipmentUsage,
    MaintenanceLog,
)
from resources.resources import (
    EquipmentBookingResource,
    EquipmentResource,
    EquipmentUsageResource,
    MaintenanceLogResource,
)


@admin.register(Trainer)
class TrainerAdmin(ImportExportModelAdmin):
    resource_class = TrainerResource

    list_display = [
        "full_name",
        "trainer_type",
        "specialty",
        "daily_rate",
        "monthly_rate",
        "phone",
        "email",
        "session_count",
        "is_active",
    ]
    list_filter = ["is_active", "trainer_type"]
    search_fields = ["first_name", "last_name", "email", "specialty"]
    list_editable = ["is_active"]
    readonly_fields = ["session_count", "total_earnings"]
    fieldsets = [
        (
            "Identité",
            {
                "fields": [
                    "first_name",
                    "last_name",
                    "specialty",
                    "trainer_type",
                    "is_active",
                ]
            },
        ),
        ("Contact", {"fields": ["phone", "email"]}),
        (
            "Tarifs & fiscal",
            {"fields": ["daily_rate", "monthly_rate", "nif", "rib"]},
        ),
        ("Qualifications", {"fields": ["certifications", "cv"]}),
        (
            "Statistiques",
            {"fields": ["session_count", "total_earnings"], "classes": ["collapse"]},
        ),
        ("Notes", {"fields": ["notes"]}),
    ]


@admin.register(TrainingRoom)
class TrainingRoomAdmin(ImportExportModelAdmin):
    resource_class = TrainingRoomResource

    list_display = [
        "name",
        "capacity",
        "location",
        "has_projector",
        "has_whiteboard",
        "has_ac",
        "is_active",
    ]
    list_filter = ["has_projector", "has_ac", "is_active"]
    search_fields = ["name", "location"]
    list_editable = ["is_active"]


class EquipmentUsageInline(admin.TabularInline):
    model = EquipmentUsage
    extra = 0
    fields = [
        "date",
        "assigned_to_session",
        "assigned_to_project",
        "duration_hours",
        "context",
    ]
    ordering = ["-date"]
    show_change_link = False


class MaintenanceLogInline(admin.TabularInline):
    model = MaintenanceLog
    extra = 0
    fields = ["date", "maintenance_type", "cost", "performed_by", "next_due_date"]
    ordering = ["-date"]
    show_change_link = True


class EquipmentBookingInline(admin.TabularInline):
    model = EquipmentBooking
    extra = 0
    fields = [
        "date_from",
        "date_to",
        "reserved_for_session",
        "reserved_for_project",
        "notes",
    ]
    ordering = ["date_from"]


@admin.register(Equipment)
class EquipmentAdmin(ImportExportModelAdmin):
    resource_class = EquipmentResource

    list_display = [
        "name",
        "category",
        "serial_number",
        "condition",
        "status",
        "location",
        "usage_count",
        "is_maintenance_due",
        "is_idle",
    ]
    list_filter = ["status", "condition", "category"]
    search_fields = ["name", "serial_number", "model_number", "category"]
    list_editable = ["status", "condition"]
    readonly_fields = [
        "usage_count",
        "total_usage_hours",
        "last_used_date",
        "days_since_last_use",
        "is_idle",
        "total_maintenance_cost",
        "total_cost_of_ownership",
        "cost_per_use",
        "depreciation_rate",
        "age_years",
        "next_maintenance_due",
        "is_maintenance_due",
        "is_under_warranty",
    ]
    inlines = [EquipmentBookingInline, EquipmentUsageInline, MaintenanceLogInline]
    fieldsets = [
        (
            "Équipement",
            {
                "fields": [
                    "name",
                    "category",
                    "serial_number",
                    "model_number",
                    "supplier",
                ]
            },
        ),
        ("État & localisation", {"fields": ["condition", "status", "location"]}),
        (
            "Acquisition",
            {
                "fields": [
                    "purchase_date",
                    "purchase_cost",
                    "current_value",
                    "useful_life_years",
                    "warranty_expiry",
                ]
            },
        ),
        (
            "Maintenance",
            {
                "fields": [
                    "maintenance_interval_days",
                    "next_maintenance_due",
                    "is_maintenance_due",
                ]
            },
        ),
        (
            "Statistiques usage",
            {
                "fields": [
                    "usage_count",
                    "total_usage_hours",
                    "last_used_date",
                    "days_since_last_use",
                    "is_idle",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Statistiques financières",
            {
                "fields": [
                    "total_maintenance_cost",
                    "total_cost_of_ownership",
                    "cost_per_use",
                    "depreciation_rate",
                    "age_years",
                ],
                "classes": ["collapse"],
            },
        ),
        ("Notes", {"fields": ["notes"]}),
    ]

    @admin.display(description="Maintenance due", boolean=True)
    def is_maintenance_due(self, obj):
        return obj.is_maintenance_due

    @admin.display(description="Inactif", boolean=True)
    def is_idle(self, obj):
        return obj.is_idle


@admin.register(EquipmentUsage)
class EquipmentUsageAdmin(ImportExportModelAdmin):
    resource_class = EquipmentUsageResource

    list_display = [
        "equipment",
        "date",
        "duration_hours",
        "assigned_to_session",
        "assigned_to_project",
    ]
    list_filter = ["date"]
    search_fields = ["equipment__name", "context"]
    raw_id_fields = ["equipment", "assigned_to_session", "assigned_to_project"]


@admin.register(EquipmentBooking)
class EquipmentBookingAdmin(ImportExportModelAdmin):
    resource_class = EquipmentBookingResource

    list_display = [
        "equipment",
        "date_from",
        "date_to",
        "reserved_for_session",
        "reserved_for_project",
    ]
    list_filter = ["date_from"]
    search_fields = ["equipment__name"]
    raw_id_fields = ["equipment", "reserved_for_session", "reserved_for_project"]


@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(ImportExportModelAdmin):
    resource_class = MaintenanceLogResource

    list_display = [
        "equipment",
        "date",
        "maintenance_type",
        "cost",
        "performed_by",
        "next_due_date",
    ]
    list_filter = ["maintenance_type", "date"]
    search_fields = ["equipment__name", "performed_by", "description"]
    raw_id_fields = ["equipment"]
