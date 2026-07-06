# clients/resources.py
# django-import-export resource definitions for the clients app.

from import_export import fields, resources
from import_export.widgets import BooleanWidget, ForeignKeyWidget

from clients.models import Client, ClientContact, FormeJuridique


# ---------------------------------------------------------------------------
# FormeJuridique
# ---------------------------------------------------------------------------


class FormeJuridiqueResource(resources.ModelResource):
    class Meta:
        model = FormeJuridique
        fields = ("id", "name", "description", "is_active")
        export_order = fields
        import_id_fields = ("name",)
        skip_unchanged = True
        report_skipped = False


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ClientResource(resources.ModelResource):
    forme_juridique = fields.Field(
        column_name="forme_juridique",
        attribute="forme_juridique",
        widget=ForeignKeyWidget(FormeJuridique, field="name"),
    )

    class Meta:
        model = Client
        fields = (
            "id",
            "client_type",
            "name",
            "forme_juridique",
            # Contact
            "address",
            "postal_code",
            "city",
            "phone",
            "email",
            "website",
            "activity_sector",
            # Legacy contact
            "contact_name",
            "contact_phone",
            "contact_email",
            # Legal / fiscal
            "nin",
            "nif",
            "article_imposition",
            "nis",
            "rc",
            "rib",
            "tin",
            "carte_auto_entrepreneur",
            # Startup
            "label_startup_number",
            "label_startup_date",
            "programme_accompagnement",
            # Flags
            "is_tva_exempt",
            "is_active",
            "notes",
        )
        export_order = fields
        import_id_fields = ("id",)
        skip_unchanged = True
        report_skipped = False

    def before_import_row(self, row, row_number=None, **kwargs):
        """Normalise client_type to lowercase before import."""
        if "client_type" in row and row["client_type"]:
            row["client_type"] = str(row["client_type"]).lower().strip()

    def after_save_instance(self, instance, new, row, **kwargs):
        """Re-trigger save() so is_tva_exempt is auto-derived from client_type."""
        instance.save()


# ---------------------------------------------------------------------------
# ClientContact
# ---------------------------------------------------------------------------


class ClientContactResource(resources.ModelResource):
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
        model = ClientContact
        fields = (
            "id",
            "client_id",
            "client",
            "first_name",
            "last_name",
            "job_title",
            "phone",
            "email",
            "is_primary",
            "notes",
        )
        export_order = (
            "id",
            "client_id",
            "client",
            "first_name",
            "last_name",
            "job_title",
            "phone",
            "email",
            "is_primary",
            "notes",
        )
        import_id_fields = ("id",)
        skip_unchanged = True
        report_skipped = False
