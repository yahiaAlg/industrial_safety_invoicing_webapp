# clients/admin.py  —  v3.1
# Changes: FormeJuridique registered; Client admin updated for FK field.

from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from clients.models import Client, ClientContact, FormeJuridique
from clients.resources import (
    ClientContactResource,
    ClientResource,
    FormeJuridiqueResource,
)

# ---------------------------------------------------------------------------
# FormeJuridique
# ---------------------------------------------------------------------------


@admin.register(FormeJuridique)
class FormeJuridiqueAdmin(ImportExportModelAdmin):
    resource_class = FormeJuridiqueResource

    list_display = ["name", "description", "is_active", "client_count"]
    list_editable = ["is_active"]
    search_fields = ["name", "description"]
    list_filter = ["is_active"]

    @admin.display(description="Clients liés")
    def client_count(self, obj):
        return obj.clients.count()

    def get_readonly_fields(self, request, obj=None):
        # Prevent renaming the system default
        if obj and obj.name == "Autre":
            return ["name"]
        return []


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ClientContactInline(admin.TabularInline):
    model = ClientContact
    extra = 0
    fields = ["first_name", "last_name", "job_title", "phone", "email", "is_primary"]


@admin.register(Client)
class ClientAdmin(ImportExportModelAdmin):
    resource_class = ClientResource

    list_display = [
        "name",
        "client_type",
        "forme_juridique",
        "city",
        "phone",
        "email",
        "activity_sector",
        "is_tva_exempt",
        "is_invoice_ready_display",
        "is_active",
    ]
    list_filter = [
        "client_type",
        "is_active",
        "is_tva_exempt",
        "forme_juridique",
        "city",
    ]
    search_fields = ["name", "email", "phone", "rc", "nif", "nis", "nin"]
    list_editable = ["is_active"]
    readonly_fields = ["is_tva_exempt", "invoice_readiness"]
    autocomplete_fields = ["forme_juridique"]
    inlines = [ClientContactInline]

    fieldsets = [
        (
            "Identification",
            {
                "fields": [
                    "name",
                    "client_type",
                    "forme_juridique",
                    "activity_sector",
                    "is_active",
                ]
            },
        ),
        (
            "Coordonnées",
            {"fields": ["address", "postal_code", "city", "phone", "email", "website"]},
        ),
        (
            "Contact principal (héritage)",
            {
                "fields": ["contact_name", "contact_phone", "contact_email"],
                "classes": ["collapse"],
            },
        ),
        (
            "Identifiants fiscaux",
            {
                "fields": [
                    "nin",
                    "nif",
                    "nis",
                    "rc",
                    "article_imposition",
                    "rib",
                    "is_tva_exempt",
                ],
                "description": (
                    "NIN : particulier uniquement. "
                    "NIF / ART.I : AE, entreprise, startup. "
                    "NIS / RC : entreprise, startup."
                ),
            },
        ),
        (
            "Auto-Entrepreneur",
            {"fields": ["carte_auto_entrepreneur"], "classes": ["collapse"]},
        ),
        (
            "Startup",
            {
                "fields": [
                    "label_startup_number",
                    "label_startup_date",
                    "programme_accompagnement",
                ],
                "classes": ["collapse"],
            },
        ),
        ("Statut facturation", {"fields": ["invoice_readiness"]}),
        ("Notes", {"fields": ["notes"]}),
    ]

    @admin.display(description="Prêt facturation", boolean=True)
    def is_invoice_ready_display(self, obj):
        return obj.is_invoice_ready

    @admin.display(description="Statut facturation")
    def invoice_readiness(self, obj):
        missing = obj.missing_fields_for_invoice()
        if not missing:
            return "✔ Complet — prêt pour facturation"
        return "✘ Manquant : " + ", ".join(missing)


# ---------------------------------------------------------------------------
# ClientContact
# ---------------------------------------------------------------------------


@admin.register(ClientContact)
class ClientContactAdmin(ImportExportModelAdmin):
    resource_class = ClientContactResource

    list_display = ["full_name", "client", "job_title", "phone", "email", "is_primary"]
    list_filter = ["is_primary"]
    search_fields = ["first_name", "last_name", "client__name", "email"]
    raw_id_fields = ["client"]
