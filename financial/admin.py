# =============================================================================
# financial/admin.py  —  v3.1
# =============================================================================
# Changes in v3.1:
# * Invoice: mode_reglement field added to Règlement fieldset.
# * Invoice: timbre_fiscal, timbre_rate_display, amount_net_a_payer added
#   as readonly computed display fields.
# * Invoice: mode_reglement added to list_display.
# =============================================================================

from django.contrib import admin
from django.utils.html import format_html
from import_export.admin import ImportExportModelAdmin

from financial.models import (
    Beneficiary,
    BeneficiaryType,
    CreditNote,
    Expense,
    ExpenseCategory,
    FinancialPeriod,
    Invoice,
    InvoiceItem,
    InvoiceSequence,
    Payment,
    PaymentAccount,
    ProformaSnapshot,
)
from financial.resources import (
    BeneficiaryResource,
    BeneficiaryTypeResource,
    CreditNoteResource,
    ExpenseCategoryResource,
    ExpenseResource,
    FinancialPeriodResource,
    InvoiceItemResource,
    InvoiceResource,
    InvoiceSequenceResource,
    PaymentResource,
    PaymentAccountResource,
    ProformaSnapshotResource,
)

# ---------------------------------------------------------------------------
# Inlines
# ---------------------------------------------------------------------------


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 1
    fields = [
        "order",
        "description",
        "pricing_mode",
        "nb_persons",
        "nb_days",
        "unit_price_ht",
        "discount_percent",
        "total_ht",
    ]
    readonly_fields = ["total_ht"]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_locked:
            return [f.name for f in InvoiceItem._meta.fields]
        return self.readonly_fields


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ["date", "amount", "method", "status", "reference"]

    def has_add_permission(self, request, obj=None):
        if obj and not obj.is_payable:
            return False
        return super().has_add_permission(request, obj)


# ---------------------------------------------------------------------------
# Invoice
# ---------------------------------------------------------------------------


@admin.register(Invoice)
class InvoiceAdmin(ImportExportModelAdmin):
    resource_class = InvoiceResource

    list_display = [
        "display_reference",
        "phase",
        "client",
        "invoice_type",
        "invoice_date",
        "amount_ttc",
        "mode_reglement",
        "amount_paid",
        "amount_remaining",
        "status",
        "has_bc_display",
        "is_overdue_display",
    ]
    list_filter = ["phase", "invoice_type", "status", "mode_reglement", "invoice_date"]
    search_fields = ["proforma_reference", "reference", "client__name"]
    raw_id_fields = ["client", "session", "study_project"]
    inlines = [InvoiceItemInline, PaymentInline]

    readonly_fields = [
        "proforma_reference",
        "reference",
        "phase",
        "finalized_at",
        "amount_ht",
        "amount_tva",
        "amount_ttc",
        "amount_paid",
        "amount_remaining",
        "amount_in_words",
        # v3.1 computed
        "timbre_fiscal",
        "timbre_rate_display",
        "amount_net_a_payer",
        # helpers
        "is_overdue_display",
        "days_overdue",
        "payment_completion_percent",
        "has_bc_display",
        "can_be_finalized",
        # client snapshots
        "client_name_snapshot",
        "client_address_snapshot",
        "client_type_snapshot",
        "client_nif_snapshot",
        "client_nis_snapshot",
        "client_rc_snapshot",
        "client_ai_snapshot",
        "client_nin_snapshot",
        "client_rib_snapshot",
        "client_tin_snapshot",
    ]

    fieldsets = [
        (
            "Identification",
            {
                "fields": [
                    "proforma_reference",
                    "reference",
                    "page_ref",
                    "invoice_type",
                    "phase",
                    "status",
                    "client",
                ]
            },
        ),
        (
            "Dates",
            {
                "fields": [
                    "invoice_date",
                    "validity_date",
                    "due_date",
                    "finalized_at",
                ]
            },
        ),
        (
            "Bon de Commande",
            {
                "fields": [
                    "bon_commande_number",
                    "bon_commande_date",
                    "bon_commande_amount",
                    "bon_commande_scan",
                    "has_bc_display",
                    "can_be_finalized",
                ]
            },
        ),
        ("Liens (traçabilité)", {"fields": ["session", "study_project"]}),
        (
            "Montants",
            {
                "fields": [
                    "tva_rate",
                    "amount_ht",
                    "amount_tva",
                    "amount_ttc",
                    "amount_paid",
                    "amount_remaining",
                    "amount_in_words",
                    "payment_completion_percent",
                ]
            },
        ),
        (
            "Règlement & timbre fiscal (v3.1)",
            {
                "fields": [
                    "mode_reglement",
                    "timbre_rate_display",
                    "timbre_fiscal",
                    "amount_net_a_payer",
                ]
            },
        ),
        (
            "Snapshot client (figé à la finalisation)",
            {
                "fields": [
                    "client_name_snapshot",
                    "client_address_snapshot",
                    "client_type_snapshot",
                    "client_nif_snapshot",
                    "client_nis_snapshot",
                    "client_rc_snapshot",
                    "client_ai_snapshot",
                    "client_nin_snapshot",
                    "client_rib_snapshot",
                    "client_tin_snapshot",
                ],
                "classes": ["collapse"],
            },
        ),
        ("Textes", {"fields": ["notes", "footer_text"]}),
    ]

    @admin.display(description="Référence")
    def display_reference(self, obj):
        return obj.reference or obj.proforma_reference

    @admin.display(description="BC reçu", boolean=True)
    def has_bc_display(self, obj):
        return obj.has_bon_commande

    @admin.display(description="En retard", boolean=True)
    def is_overdue_display(self, obj):
        return obj.is_overdue

    @admin.display(description="Timbre fiscal (DA)")
    def timbre_fiscal(self, obj):
        value = obj.timbre_fiscal
        if value:
            return format_html("<strong>{} DA</strong>", value)
        return "—"

    @admin.display(description="Taux timbre")
    def timbre_rate_display(self, obj):
        return obj.timbre_rate_display or "—"

    @admin.display(description="Net à payer TTC (DA)")
    def amount_net_a_payer(self, obj):
        return obj.amount_net_a_payer

    @admin.display(description="Avancement paiement (%)")
    def payment_completion_percent(self, obj):
        return f"{obj.payment_completion_percent} %"

    @admin.display(description="Peut être finalisée", boolean=True)
    def can_be_finalized(self, obj):
        return obj.can_be_finalized

    @admin.display(description="Jours de retard")
    def days_overdue(self, obj):
        return obj.days_overdue or "—"


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------


@admin.register(Payment)
class PaymentAdmin(ImportExportModelAdmin):
    resource_class = PaymentResource

    list_display = ["invoice", "date", "amount", "method", "status", "reference"]
    list_filter = ["status", "method", "date"]
    search_fields = ["invoice__reference", "invoice__proforma_reference", "reference"]
    raw_id_fields = ["invoice"]


# ---------------------------------------------------------------------------
# Credit note
# ---------------------------------------------------------------------------


@admin.register(CreditNote)
class CreditNoteAdmin(ImportExportModelAdmin):
    resource_class = CreditNoteResource

    list_display = [
        "reference",
        "original_invoice",
        "date",
        "amount_ttc",
        "is_full_reversal",
    ]
    search_fields = ["reference", "original_invoice__reference"]
    readonly_fields = ["reference", "amount_tva", "amount_ttc", "coverage_percent"]
    raw_id_fields = ["original_invoice"]

    @admin.display(description="Couverture (%)")
    def coverage_percent(self, obj):
        return f"{obj.coverage_percent} %"


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(ImportExportModelAdmin):
    resource_class = ExpenseCategoryResource

    list_display = ["name", "is_direct_cost", "color"]
    list_filter = ["is_direct_cost"]


@admin.register(Expense)
class ExpenseAdmin(ImportExportModelAdmin):
    resource_class = ExpenseResource
    actions = ["approve_selected", "reject_selected", "reset_to_pending"]

    @admin.action(description="✔ Approuver les dépenses sélectionnées")
    def approve_selected(self, request, queryset):
        updated = queryset.exclude(
            approval_status=Expense.ApprovalStatus.APPROVED
        ).update(approval_status=Expense.ApprovalStatus.APPROVED)
        self.message_user(request, f"{updated} dépense(s) approuvée(s).")

    @admin.action(description="✘ Refuser les dépenses sélectionnées")
    def reject_selected(self, request, queryset):
        updated = queryset.exclude(
            approval_status=Expense.ApprovalStatus.REJECTED
        ).update(approval_status=Expense.ApprovalStatus.REJECTED)
        self.message_user(request, f"{updated} dépense(s) refusée(s).", level="warning")

    @admin.action(description="⟳ Remettre en attente les dépenses sélectionnées")
    def reset_to_pending(self, request, queryset):
        updated = queryset.exclude(
            approval_status=Expense.ApprovalStatus.PENDING
        ).update(approval_status=Expense.ApprovalStatus.PENDING)
        self.message_user(request, f"{updated} dépense(s) remise(s) en attente.")

    list_display = [
        "date",
        "description",
        "category",
        "payee_display",
        "gross_amount",
        "irg_amount",
        "amount",
        "payment_date",
        "cost_centre_label",
        "g50_month",
        "approval_status",
        "receipt_missing",
        "needs_action",
    ]
    list_filter = [
        "approval_status",
        "category",
        "receipt_missing",
        "fiscal_year",
        "quarter",
        "g50_month",
    ]
    search_fields = ["description", "supplier", "beneficiary__name"]
    raw_id_fields = [
        "allocated_to_session",
        "allocated_to_project",
        "beneficiary",
        "payment_account",
        "linked_formation",
    ]
    readonly_fields = [
        "cost_centre_label",
        "needs_action",
        "is_approved",
        "payee_display",
        "irg_amount",
        "fiscal_year",
        "quarter",
        "created_at",
        "updated_at",
    ]
    fieldsets = [
        (
            "Dépense",
            {
                "fields": [
                    "date",
                    "category",
                    "description",
                    "supplier",
                ]
            },
        ),
        (
            "Bénéficiaire",
            {
                "fields": [
                    "beneficiary",
                    "payment_account",
                    "payee_display",
                ]
            },
        ),
        (
            "Montants & IRG",
            {
                "fields": [
                    "gross_amount",
                    "irg_rate",
                    "irg_amount",
                    "amount",
                    "payment_reference",
                    "payment_date",
                ]
            },
        ),
        (
            "Formateur (si applicable)",
            {
                "fields": [
                    "trainer_payment_mode",
                    "linked_formation",
                    "training_period_label",
                    "daily_rate_snapshot",
                    "monthly_rate_snapshot",
                ],
                "classes": ["collapse"],
            },
        ),
        (
            "Imputation",
            {
                "fields": [
                    "allocated_to_session",
                    "allocated_to_project",
                    "is_overhead",
                    "cost_centre_label",
                ]
            },
        ),
        (
            "Période fiscale",
            {
                "fields": ["fiscal_year", "quarter", "g50_month"],
                "classes": ["collapse"],
            },
        ),
        ("Justificatif", {"fields": ["receipt", "receipt_missing"]}),
        (
            "Approbation",
            {"fields": ["approval_status", "approval_notes", "is_approved"]},
        ),
        ("Notes", {"fields": ["notes"]}),
        (
            "Dates de saisie (système)",
            {
                "fields": ["created_at", "updated_at"],
                "classes": ["collapse"],
                "description": "Dates gérées automatiquement par le système — non modifiables.",
            },
        ),
    ]

    @admin.display(description="Bénéficiaire")
    def payee_display(self, obj):
        return obj.payee_display


# ---------------------------------------------------------------------------
# Financial period
# ---------------------------------------------------------------------------


@admin.register(FinancialPeriod)
class FinancialPeriodAdmin(ImportExportModelAdmin):
    resource_class = FinancialPeriodResource

    list_display = [
        "name",
        "period_type",
        "date_start",
        "date_end",
        "is_closed",
        "total_invoiced_ht",
        "total_collected",
        "gross_margin",
    ]
    list_filter = ["period_type", "is_closed"]
    readonly_fields = [
        "total_invoiced_ht",
        "total_collected",
        "total_expenses",
        "gross_margin",
        "formation_revenue_ht",
        "etude_revenue_ht",
    ]


# ---------------------------------------------------------------------------
# Invoice sequence (counter override)
# ---------------------------------------------------------------------------


@admin.register(InvoiceSequence)
class InvoiceSequenceAdmin(ImportExportModelAdmin):
    """
    Allows operators to inspect and override the proforma / finale counters.
    Set `last_number` to N-1 so that the next invoice gets number N.
    Example: last_number = 4  →  next invoice = FP-005-2026.
    """

    resource_class = InvoiceSequenceResource

    list_display = [
        "__str__",
        "invoice_type",
        "phase",
        "year",
        "last_number",
        "next_number_display",
    ]
    list_editable = ["last_number"]
    list_filter = ["year", "invoice_type", "phase"]
    ordering = ["-year", "invoice_type", "phase"]

    @admin.display(description="Prochain n°")
    def next_number_display(self, obj):
        return format_html("<strong>{}</strong>", f"{int(obj.next_number):03d}")


# ---------------------------------------------------------------------------
# InvoiceItem (standalone, for bulk import/export support)
# ---------------------------------------------------------------------------


@admin.register(InvoiceItem)
class InvoiceItemAdmin(ImportExportModelAdmin):
    resource_class = InvoiceItemResource

    list_display = ["invoice", "order", "description", "pricing_mode", "total_ht"]
    list_filter = ["pricing_mode"]
    search_fields = ["description", "invoice__reference", "invoice__proforma_reference"]
    raw_id_fields = ["invoice"]
    readonly_fields = ["total_ht"]


# ---------------------------------------------------------------------------
# Beneficiary system
# ---------------------------------------------------------------------------


@admin.register(BeneficiaryType)
class BeneficiaryTypeAdmin(ImportExportModelAdmin):
    resource_class = BeneficiaryTypeResource

    list_display = ["name", "slug", "color", "is_active", "is_seeded"]
    list_filter = ["is_active", "is_seeded"]
    search_fields = ["name", "slug"]
    list_editable = ["is_active"]
    readonly_fields = ["is_seeded"]

    def has_delete_permission(self, request, obj=None):
        if obj and obj.is_seeded:
            return False
        return super().has_delete_permission(request, obj)


class PaymentAccountInline(admin.TabularInline):
    model = PaymentAccount
    extra = 0
    fields = [
        "account_type",
        "label",
        "account_number",
        "bank_name",
        "is_default",
        "notes",
    ]
    ordering = ["-is_default", "account_type"]


@admin.register(Beneficiary)
class BeneficiaryAdmin(ImportExportModelAdmin):
    resource_class = BeneficiaryResource

    list_display = [
        "name",
        "beneficiary_type",
        "is_trainer",
        "is_employee",
        "irg_rate",
        "phone",
        "is_active",
    ]
    list_filter = ["beneficiary_type", "is_trainer", "is_employee", "is_active"]
    search_fields = ["name", "nif", "email", "phone"]
    list_editable = ["is_active"]
    raw_id_fields = ["trainer"]
    readonly_fields = ["trainer"]
    inlines = [PaymentAccountInline]
    fieldsets = [
        (
            "Identité",
            {
                "fields": [
                    "name",
                    "beneficiary_type",
                    "is_trainer",
                    "is_employee",
                    "trainer",
                    "is_active",
                ]
            },
        ),
        (
            "Contact & fiscal",
            {"fields": ["nif", "rib", "phone", "email", "address"]},
        ),
        (
            "Tarifs",
            {"fields": ["daily_rate", "monthly_rate"]},
        ),
        (
            "IRG",
            {
                "fields": ["irg_rate"],
                "description": "0 = aucune retenue ; 0.10 = 10% (prestataires externes).",
            },
        ),
        ("Notes", {"fields": ["notes"]}),
    ]


@admin.register(PaymentAccount)
class PaymentAccountAdmin(ImportExportModelAdmin):
    resource_class = PaymentAccountResource

    list_display = [
        "beneficiary",
        "account_type",
        "label",
        "account_number",
        "bank_name",
        "is_default",
    ]
    list_filter = ["account_type", "is_default"]
    search_fields = ["beneficiary__name", "account_number", "label", "bank_name"]
    raw_id_fields = ["beneficiary"]


# ---------------------------------------------------------------------------
# ProformaSnapshot (read-only archive)
# ---------------------------------------------------------------------------


@admin.register(ProformaSnapshot)
class ProformaSnapshotAdmin(ImportExportModelAdmin):
    resource_class = ProformaSnapshotResource

    list_display = [
        "proforma_reference",
        "invoice",
        "invoice_type",
        "invoice_date",
        "amount_ttc",
        "client_name",
    ]
    search_fields = ["proforma_reference", "client_name", "invoice__reference"]
    raw_id_fields = ["invoice"]
    readonly_fields = [f.name for f in ProformaSnapshot._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
