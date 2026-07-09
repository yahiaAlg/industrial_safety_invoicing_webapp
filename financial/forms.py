# =============================================================================
# financial/forms.py  —  v4.0
# =============================================================================
# Changes in v4.0:
# * Added BeneficiaryTypeForm  — quick-add modal for beneficiary types.
# * Added BeneficiaryForm      — quick-add modal for registered payees.
# * Added PaymentAccountForm   — quick-add modal for payment accounts.
# * ExpenseForm rewritten      — full new fields: beneficiary, payment_account,
#   gross_amount, irg_rate, trainer_payment_mode, linked_formation,
#   training_period_label, g50_month, rate snapshots.
# * ExpenseFilterForm extended — beneficiary, beneficiary_type, fiscal_year,
#   quarter, g50_month (fiscal period), trainer_payment_mode filters.
# =============================================================================

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError

from clients.models import Client
from core.form_mixins import ISIFormMixin
from financial.models import (
    Beneficiary,
    BeneficiaryType,
    CreditNote,
    Expense,
    ExpenseCategory,
    FinancialPeriod,
    Invoice,
    InvoiceItem,
    PaymentAccount,
    Payment,
)

# ---------------------------------------------------------------------------
# Proforma creation form
# ---------------------------------------------------------------------------


class ProformaCreateForm(ISIFormMixin, forms.ModelForm):
    """
    Used when creating a new proforma invoice.
    Only fields relevant to the PROFORMA phase are exposed.
    reference / proforma_reference are auto-generated; amounts are computed
    from line items.

    Manual numbering override (v4.1)
    ─────────────────────────────────
    * override_reference — free-text, not a model field. When filled, it is
      written verbatim into proforma_reference (draft/proforma phase) or
      reference (finale phase) instead of the auto-generated value. Use
      only for urgent corrections — uniqueness is still enforced.
    * sequence_year — not a model field. Only used on CREATION when
      override_reference is empty: forces the auto-generated proforma
      reference to consume the counter for that year instead of the year
      derived from invoice_date. Use when backfilling old invoices so they
      land in their correct historical sequence rather than the current one.
    """

    override_reference = forms.CharField(
        required=False,
        label="Numéro personnalisé",
        help_text=(
            "Laisser vide pour la numérotation automatique. Remplir pour "
            "forcer une valeur précise (ex. F-015-2025) — correction "
            "d'urgence uniquement."
        ),
    )
    sequence_year = forms.IntegerField(
        required=False,
        label="Année de séquence (numérotation auto)",
        help_text=(
            "Ne s'applique qu'à la création, sans numéro personnalisé. Par "
            "défaut : année de la date d'émission. À utiliser pour insérer "
            "d'anciennes factures dans la séquence de leur année réelle."
        ),
        min_value=2000,
        max_value=2100,
    )

    class Meta:
        model = Invoice
        fields = [
            "invoice_type",
            "client",
            "invoice_date",
            "validity_date",
            "tva_rate",
            "page_ref",
            "session",
            "study_project",
            "notes",
            "footer_text",
        ]
        labels = {
            "invoice_type": "Type de prestation",
            "client": "Client",
            "invoice_date": "Date d'émission",
            "validity_date": "Date de validité",
            "tva_rate": "Taux TVA",
            "page_ref": "Réf. interne (en-tête)",
            "session": "Session liée (optionnel)",
            "study_project": "Projet lié (optionnel)",
            "notes": "Notes internes",
            "footer_text": "Pied de page (personnalisé)",
        }
        widgets = {
            "invoice_date": forms.DateInput(attrs={"type": "date"}),
            "validity_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "footer_text": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.filter(is_active=True).order_by(
            "name"
        )
        for f in (
            "validity_date",
            "page_ref",
            "session",
            "study_project",
            "notes",
            "footer_text",
            "override_reference",
            "sequence_year",
        ):
            self.fields[f].required = False

    def clean(self):
        cleaned = super().clean()
        inv_type = cleaned.get("invoice_type")
        client = cleaned.get("client")
        session = cleaned.get("session")
        project = cleaned.get("study_project")

        if client and client.is_tva_exempt:
            cleaned["tva_rate"] = Decimal("0.00")

        if inv_type == Invoice.InvoiceType.FORMATION and project:
            self.add_error(
                "study_project",
                "Une facture Formation ne devrait pas être liée à un projet d'étude.",
            )
        if inv_type == Invoice.InvoiceType.ETUDE and session:
            self.add_error(
                "session",
                "Une facture Étude ne devrait pas être liée à une session.",
            )

        # ── Manual reference override — uniqueness check ────────────── #
        override = (cleaned.get("override_reference") or "").strip()
        if override:
            cleaned["override_reference"] = override
            existing = Invoice.objects.filter(proforma_reference=override) | (
                Invoice.objects.filter(reference=override)
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                self.add_error(
                    "override_reference",
                    "Ce numéro est déjà utilisé par une autre facture.",
                )

        return cleaned

    def save(self, commit=True):
        invoice = super().save(commit=False)

        override = (self.cleaned_data.get("override_reference") or "").strip()
        seq_year = self.cleaned_data.get("sequence_year")
        is_new = invoice.pk is None

        if override:
            # Correction d'urgence — écrase la numérotation automatique.
            if invoice.phase == Invoice.Phase.FINALE:
                invoice.reference = override
            else:
                invoice.proforma_reference = override
        elif is_new and seq_year:
            # Force la séquence d'une année précise (backfill de factures
            # antérieures) au lieu de l'année déduite de invoice_date.
            invoice.proforma_reference = Invoice._next_proforma_reference(
                invoice.invoice_type, seq_year
            )

        if commit:
            invoice.save()
        return invoice


# Backward-compatible alias used by generic edit views
InvoiceForm = ProformaCreateForm


# ---------------------------------------------------------------------------
# Bon de Commande recording form
# ---------------------------------------------------------------------------


class BonCommandeForm(ISIFormMixin, forms.ModelForm):
    """Records the client's purchase order against an existing proforma."""

    class Meta:
        model = Invoice
        fields = [
            "bon_commande_number",
            "bon_commande_date",
            "bon_commande_amount",
            "bon_commande_scan",
        ]
        labels = {
            "bon_commande_number": "N° Bon de Commande",
            "bon_commande_date": "Date du BC",
            "bon_commande_amount": "Montant BC (DA) — vérification",
            "bon_commande_scan": "Scan / document BC",
        }
        widgets = {
            "bon_commande_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("bon_commande_date", "bon_commande_amount", "bon_commande_scan"):
            self.fields[f].required = False

    def clean_bon_commande_number(self):
        number = self.cleaned_data.get("bon_commande_number", "").strip()
        if not number:
            raise ValidationError("Le numéro de Bon de Commande est obligatoire.")
        return number


# ---------------------------------------------------------------------------
# Invoice finalization confirmation form  (v3.1)
# ---------------------------------------------------------------------------


class FinalizeInvoiceForm(ISIFormMixin, forms.Form):
    """
    Shown on the finalization confirmation page (GET).

    v3.1 additions:
      * mode_reglement — required; espèce selection triggers timbre fiscal
        preview in the JS sidebar.
      * due_date        — optional; helper text clarifies it is not required.
      * amount_in_words — pre-filled textarea, editable before submit.
    """

    mode_reglement = forms.ChoiceField(
        label="Mode de règlement",
        choices=[("", "— Sélectionner —")] + Invoice.PaymentMode.choices,
        required=True,
        widget=forms.Select(),
    )
    amount_in_words = forms.CharField(
        label="Montant en lettres",
        required=False,
        widget=forms.Textarea(
            attrs={
                "rows": 2,
                "placeholder": "Généré automatiquement — vérifiez si nécessaire",
            }
        ),
    )
    due_date = forms.DateField(
        label="Date d'échéance",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Optionnel — si vide, n'apparaît pas sur la facture imprimée.",
    )
    reference_year = forms.IntegerField(
        label="Année de séquence (numéro final)",
        required=False,
        min_value=2000,
        max_value=2100,
        help_text=(
            "Par défaut : année de la date d'émission. Forcer une autre "
            "année pour insérer cette facture dans la séquence historique "
            "correcte (utile lors d'un rattrapage de factures anciennes)."
        ),
    )

    def clean_mode_reglement(self):
        value = self.cleaned_data.get("mode_reglement", "").strip()
        if not value:
            raise ValidationError("Veuillez sélectionner un mode de règlement.")
        valid = [choice[0] for choice in Invoice.PaymentMode.choices]
        if value not in valid:
            raise ValidationError("Mode de règlement invalide.")
        return value


# ---------------------------------------------------------------------------
# Invoice filter form
# ---------------------------------------------------------------------------


class InvoiceFilterForm(ISIFormMixin, forms.Form):
    q = forms.CharField(
        label="Recherche",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Référence, client…"}),
    )
    phase = forms.ChoiceField(
        label="Phase",
        required=False,
        choices=[("", "Toutes")] + Invoice.Phase.choices,
    )
    status = forms.ChoiceField(
        label="Statut",
        required=False,
        choices=[("", "Tous")] + Invoice.Status.choices,
    )
    invoice_type = forms.ChoiceField(
        label="Type",
        required=False,
        choices=[("", "Tous")] + Invoice.InvoiceType.choices,
    )
    date_from = forms.DateField(
        label="Du",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    date_to = forms.DateField(
        label="Au",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    client = forms.ModelChoiceField(
        label="Client",
        required=False,
        queryset=Client.objects.filter(is_active=True).order_by("name"),
        empty_label="Tous les clients",
    )
    amount_min = forms.DecimalField(
        label="Montant min (DA)",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"placeholder": "0"}),
    )
    amount_max = forms.DecimalField(
        label="Montant max (DA)",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"placeholder": "ex. 100000"}),
    )


# ---------------------------------------------------------------------------
# Invoice line-item form
# ---------------------------------------------------------------------------


class InvoiceItemForm(ISIFormMixin, forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = [
            "order",
            "description",
            "pricing_mode",
            "nb_persons",
            "nb_days",
            "unit_price_ht",
            "discount_percent",
        ]
        labels = {
            "order": "Ordre",
            "description": "Désignation",
            "pricing_mode": "Mode",
            "nb_persons": "Nb personnes",
            "nb_days": "Nb jours",
            "unit_price_ht": "P.U. HT (DA)",
            "discount_percent": "Remise (%)",
        }
        widgets = {
            "description": forms.TextInput(
                attrs={"placeholder": "Intitulé de la prestation"}
            ),
            "nb_persons": forms.NumberInput(attrs={"step": "1", "min": "1"}),
            "nb_days": forms.NumberInput(attrs={"step": "1", "min": "1"}),
        }

    def __init__(self, *args, invoice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["order"].required = False
        self.fields["discount_percent"].required = False
        if (
            invoice
            and not self.instance.pk
            and invoice.invoice_type == Invoice.InvoiceType.ETUDE
        ):
            self.fields["pricing_mode"].initial = InvoiceItem.PricingMode.PER_UNIT

    def clean(self):
        cleaned = super().clean()
        mode = cleaned.get("pricing_mode")
        nb_persons = cleaned.get("nb_persons") or Decimal("0")
        nb_days = cleaned.get("nb_days") or Decimal("0")

        if mode == InvoiceItem.PricingMode.PER_PERSON and nb_persons <= 0:
            self.add_error("nb_persons", "Indiquez le nombre de personnes.")
        if mode == InvoiceItem.PricingMode.PER_UNIT and nb_persons <= 0:
            self.add_error(
                "nb_persons", "Indiquez le nombre d'unités (études) réalisées."
            )
        if mode == InvoiceItem.PricingMode.PER_DAY and nb_days <= 0:
            self.add_error("nb_days", "Indiquez le nombre de jours.")
        if mode == InvoiceItem.PricingMode.PER_PERSON_PER_DAY:
            if nb_persons <= 0:
                self.add_error("nb_persons", "Indiquez le nombre de personnes.")
            if nb_days <= 0:
                self.add_error("nb_days", "Indiquez le nombre de jours.")
        return cleaned


# ---------------------------------------------------------------------------
# Payment form
# ---------------------------------------------------------------------------


class PaymentForm(ISIFormMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = [
            "date",
            "amount",
            "method",
            "status",
            "reference",
            "proof_document",
            "notes",
        ]
        labels = {
            "date": "Date",
            "amount": "Montant (DA)",
            "method": "Mode de paiement",
            "status": "Statut",
            "reference": "Référence",
            "proof_document": "Justificatif de paiement",
            "notes": "Notes",
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
        help_texts = {
            "proof_document": "Reçu, avis de virement, copie de chèque… (PDF, JPG, PNG).",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reference"].required = False
        self.fields["notes"].required = False
        self.fields["proof_document"].required = False


# ---------------------------------------------------------------------------
# Credit note form
# ---------------------------------------------------------------------------


class CreditNoteForm(ISIFormMixin, forms.ModelForm):
    class Meta:
        model = CreditNote
        fields = [
            "date",
            "reason",
            "amount_ht",
            "tva_rate",
            "is_full_reversal",
            "notes",
        ]
        labels = {
            "date": "Date",
            "reason": "Motif",
            "amount_ht": "Montant HT (DA)",
            "tva_rate": "Taux TVA",
            "is_full_reversal": "Annulation totale",
            "notes": "Notes",
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "reason": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["notes"].required = False
        self.fields["tva_rate"].initial = Decimal("0.09")

    def clean_amount_ht(self):
        amount = self.cleaned_data.get("amount_ht")
        if amount is not None and amount <= 0:
            raise ValidationError("Le montant doit être positif.")
        return amount

    def clean(self):
        cleaned = super().clean()
        tva_rate = cleaned.get("tva_rate") or Decimal("0")
        if tva_rate < 0 or tva_rate > 1:
            self.add_error(
                "tva_rate",
                "Le taux de TVA doit être compris entre 0 et 1 (ex. 0.09 pour 9%).",
            )
        return cleaned


# ---------------------------------------------------------------------------
# Beneficiary system forms  (v4.0 — quick-add modals)
# ---------------------------------------------------------------------------


class BeneficiaryTypeForm(ISIFormMixin, forms.ModelForm):
    """
    Quick-add modal form for creating a new BeneficiaryType on-the-fly
    from the expense entry screen.
    """

    class Meta:
        model = BeneficiaryType
        fields = ["name", "color"]
        labels = {
            "name": "Libellé",
            "color": "Couleur",
        }
        widgets = {
            "color": forms.TextInput(
                attrs={"type": "color", "style": "height:38px;padding:4px 6px;"}
            ),
        }

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise ValidationError("Le libellé est obligatoire.")
        qs = BeneficiaryType.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"« {name} » existe déjà.")
        return name


class BeneficiaryForm(ISIFormMixin, forms.ModelForm):
    """
    Quick-add modal form for creating / editing a Beneficiary record.
    Used from the expense entry screen when the payee is not yet registered.
    IRG rate is pre-filled (0% for employees, 10% for external trainers)
    but can be adjusted.
    """

    class Meta:
        model = Beneficiary
        fields = [
            "name",
            "beneficiary_type",
            "nif",
            "rib",
            "phone",
            "email",
            "address",
            "daily_rate",
            "monthly_rate",
            "irg_rate",
            "notes",
        ]
        labels = {
            "name": "Nom / Raison sociale",
            "beneficiary_type": "Type",
            "nif": "NIF",
            "rib": "RIB",
            "phone": "Téléphone",
            "email": "Email",
            "address": "Adresse",
            "daily_rate": "Tarif journalier (DA)",
            "monthly_rate": "Tarif mensuel (DA)",
            "irg_rate": "Taux IRG",
            "notes": "Notes",
        }
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
        help_texts = {
            "irg_rate": "Retenue IRG : 0 pour aucune, 0.10 pour 10% (prestataires externes).",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in (
            "nif",
            "rib",
            "phone",
            "email",
            "address",
            "daily_rate",
            "monthly_rate",
            "irg_rate",
            "notes",
        ):
            self.fields[f].required = False
        self.fields["beneficiary_type"].queryset = BeneficiaryType.objects.filter(
            is_active=True
        ).order_by("name")
        # irg_rate: show as percentage-friendly with 4 decimal places
        self.fields["irg_rate"].widget.attrs.update(
            {"step": "0.01", "min": "0", "max": "1"}
        )

    def clean_irg_rate(self):
        rate = self.cleaned_data.get("irg_rate")
        if rate is not None and not (Decimal("0") <= rate <= Decimal("1")):
            raise ValidationError(
                "Le taux IRG doit être compris entre 0 et 1 (ex. 0.10 pour 10%)."
            )
        return rate or Decimal("0")

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise ValidationError("Le nom est obligatoire.")
        return name


class PaymentAccountForm(ISIFormMixin, forms.ModelForm):
    """
    Quick-add modal form for adding a PaymentAccount to a Beneficiary.
    Shown from the expense entry screen when the required account doesn't
    exist yet. The `beneficiary` FK is injected from the view, not from
    user input, so it is not exposed in the form fields.
    """

    class Meta:
        model = PaymentAccount
        fields = [
            "account_type",
            "label",
            "account_number",
            "bank_name",
            "is_default",
            "notes",
        ]
        labels = {
            "account_type": "Type de compte",
            "label": "Libellé",
            "account_number": "Numéro / Code",
            "bank_name": "Banque / Établissement",
            "is_default": "Compte par défaut",
            "notes": "Notes",
        }
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, beneficiary=None, **kwargs):
        self.beneficiary = beneficiary
        super().__init__(*args, **kwargs)
        for f in ("label", "account_number", "bank_name", "notes"):
            self.fields[f].required = False

    def save(self, commit=True):
        account = super().save(commit=False)
        if self.beneficiary:
            account.beneficiary = self.beneficiary
        if commit:
            account.save()
        return account

    def clean(self):
        cleaned = super().clean()
        account_type = cleaned.get("account_type")
        account_number = (cleaned.get("account_number") or "").replace(" ", "")
        TYPES_REQUIRING_20 = {
            PaymentAccount.AccountType.BANK,  # virement bancaire
            PaymentAccount.AccountType.CCP,  # CCP
            PaymentAccount.AccountType.CHEQUE,  # chèque
        }
        if account_type in TYPES_REQUIRING_20 and account_number:
            if len(account_number) != 20:
                self.add_error(
                    "account_number",
                    f"Le numéro de compte doit comporter exactement 20 caractères "
                    f"pour ce type ({len(account_number)}/20).",
                )
        return cleaned


# ---------------------------------------------------------------------------
# Expense forms  (v4.0)
# ---------------------------------------------------------------------------


class ExpenseForm(ISIFormMixin, forms.ModelForm):
    """
    Full expense entry form — v4.0.

    Beneficiary & payment account
    ──────────────────────────────
    - beneficiary:       select from registered payees. JS auto-populates
                         irg_rate from Beneficiary.irg_rate and filters the
                         payment_account dropdown to that beneficiary's accounts.
    - payment_account:   select from the chosen beneficiary's accounts.
      Both can be left blank for unregistered / one-off payees; use
      `supplier` (legacy free-text) in that case.

    IRG
    ───
    gross_amount is the brut figure; irg_rate and irg_amount are computed
    in Expense.save(). The form exposes gross_amount and irg_rate so the
    user can verify them before saving.

    Trainer fields
    ──────────────
    trainer_payment_mode, linked_formation, training_period_label,
    daily_rate_snapshot, monthly_rate_snapshot are only relevant when the
    beneficiary is a trainer. The template uses JS to show/hide them.

    Cost centre
    ───────────
    Exactly one of allocated_to_session / allocated_to_project / is_overhead
    must be set. Enforced in Expense.clean().
    """

    class Meta:
        model = Expense
        fields = [
            # Core
            "date",
            "category",
            "description",
            # Beneficiary
            "beneficiary",
            "payment_account",
            "supplier",
            # Amounts & IRG
            "gross_amount",
            "irg_rate",
            "tva_rate",
            "timbre_fiscal",
            "payment_reference",
            "payment_date",
            # Trainer-specific
            "trainer_payment_mode",
            "linked_formation",
            "training_period_label",
            "daily_rate_snapshot",
            "monthly_rate_snapshot",
            # Cost centre
            "allocated_to_session",
            "allocated_to_project",
            "is_overhead",
            # Archiving / fiscal period
            "g50_month",
            "receipt",
            "receipt_missing",
            "approval_status",
            "approval_notes",
            "notes",
        ]
        labels = {
            "date": "Date",
            "category": "Catégorie",
            "description": "Description",
            "beneficiary": "Bénéficiaire",
            "payment_account": "Compte de paiement",
            "supplier": "Fournisseur libre (si non enregistré)",
            "gross_amount": "Montant brut (DA)",
            "irg_rate": "Taux IRG",
            "tva_rate": "Taux TVA",
            "timbre_fiscal": "Timbre fiscal (DA)",
            "payment_reference": "Réf. paiement",
            "payment_date": "Date de règlement",
            "trainer_payment_mode": "Mode de paiement formateur",
            "linked_formation": "Formation liée (forfait)",
            "training_period_label": "Période couverte",
            "g50_month": "Mois G50",
            "daily_rate_snapshot": "Tarif journalier (snapshot)",
            "monthly_rate_snapshot": "Tarif mensuel (snapshot)",
            "allocated_to_session": "Session",
            "allocated_to_project": "Projet",
            "is_overhead": "Frais généraux",
            "receipt": "Justificatif",
            "receipt_missing": "Justificatif manquant",
            "approval_status": "Statut d'approbation",
            "approval_notes": "Notes d'approbation",
            "notes": "Notes",
        }
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "g50_month": forms.DateInput(attrs={"type": "date"}),
            "payment_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "approval_notes": forms.Textarea(attrs={"rows": 2}),
            "irg_rate": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "max": "1"}
            ),
            "tva_rate": forms.NumberInput(
                attrs={"step": "0.01", "min": "0", "max": "1"}
            ),
            "timbre_fiscal": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }
        help_texts = {
            "gross_amount": "Montant avant retenue IRG. Si IRG = 0, identique au montant net.",
            "irg_rate": "0 = pas de retenue ; 0.10 = 10% (prestataires externes).",
            "tva_rate": "0 = exonere ou inconnu ; 0.09 = 9% ; 0.19 = 19%.",
            "timbre_fiscal": "Uniquement si réglée en espèces — sinon laissez à 0.",
            "g50_month": "Premier jour du mois de déclaration G50 (ex. 2026-01-01).",
            "training_period_label": "Ex. « 22-24/12/2023 » — description libre de la période.",
            "supplier": "Utilisez ce champ uniquement si le bénéficiaire n'est pas enregistré.",
        }

    # Extra non-model field — controls HT↔TTC interpretation
    amount_is_ttc = forms.BooleanField(
        required=False,
        initial=False,
        label="Montant saisi en TTC",
        help_text="Cochez si le montant entré est TTC. Décoché = montant HT (défaut).",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Optional fields
        optional = [
            "beneficiary",
            "payment_account",
            "supplier",
            "irg_rate",
            "tva_rate",
            "payment_reference",
            "payment_date",
            "trainer_payment_mode",
            "linked_formation",
            "training_period_label",
            "g50_month",
            "daily_rate_snapshot",
            "monthly_rate_snapshot",
            "allocated_to_session",
            "allocated_to_project",
            "receipt",
            "approval_status",
            "approval_notes",
            "notes",
        ]
        for f in optional:
            if f in self.fields:
                self.fields[f].required = False

        # On edit: gross_amount is already stored TTC → pre-tick the checkbox
        if self.instance and self.instance.pk:
            self.fields["amount_is_ttc"].initial = True

        # Beneficiary — active only
        self.fields["beneficiary"].queryset = (
            Beneficiary.objects.filter(is_active=True)
            .select_related("beneficiary_type")
            .order_by("name")
        )
        self.fields["beneficiary"].empty_label = "— Sélectionner ou ajouter —"

        # Payment account — filtered dynamically by JS; start with all or
        # filter by bound instance's beneficiary if editing.
        pa_qs = PaymentAccount.objects.select_related("beneficiary")
        if self.instance and self.instance.pk and self.instance.beneficiary_id:
            pa_qs = pa_qs.filter(beneficiary=self.instance.beneficiary)
        self.fields["payment_account"].queryset = pa_qs
        self.fields["payment_account"].empty_label = "— Sélectionner un compte —"

        # Trainer mode initial values from bound instance
        if self.instance and self.instance.pk:
            if self.instance.daily_rate_snapshot:
                self.fields["daily_rate_snapshot"].initial = (
                    self.instance.daily_rate_snapshot
                )
            if self.instance.monthly_rate_snapshot:
                self.fields["monthly_rate_snapshot"].initial = (
                    self.instance.monthly_rate_snapshot
                )

    def clean_irg_rate(self):
        rate = self.cleaned_data.get("irg_rate")
        if rate is None:
            return Decimal("0")
        if not (Decimal("0") <= rate <= Decimal("1")):
            raise ValidationError("Le taux IRG doit être compris entre 0 et 1.")
        return rate

    def clean_tva_rate(self):
        rate = self.cleaned_data.get("tva_rate")
        if rate is None:
            return Decimal("0")
        if not (Decimal("0") <= rate <= Decimal("1")):
            raise ValidationError("Le taux TVA doit être compris entre 0 et 1.")
        return rate

    def clean_gross_amount(self):
        amount = self.cleaned_data.get("gross_amount")
        if amount is not None and amount <= 0:
            raise ValidationError("Le montant brut doit être positif.")
        return amount

    def clean(self):
        cleaned = super().clean()

        # gross_amount is required — if omitted, treat amount field as gross
        gross = cleaned.get("gross_amount")
        if gross is None:
            raise ValidationError({"gross_amount": "Le montant brut est requis."})

        # HT → TTC conversion when amount_is_ttc is unchecked
        amount_is_ttc = cleaned.get("amount_is_ttc", False)
        tva_rate = cleaned.get("tva_rate") or Decimal("0")
        if not amount_is_ttc and tva_rate > 0 and gross is not None:
            # User entered HT — convert to TTC for storage in gross_amount
            cleaned["gross_amount"] = (gross * (1 + tva_rate)).quantize(Decimal("0.01"))

        # Payment account must belong to selected beneficiary
        beneficiary = cleaned.get("beneficiary")
        payment_account = cleaned.get("payment_account")
        if payment_account and beneficiary:
            if payment_account.beneficiary_id != beneficiary.pk:
                self.add_error(
                    "payment_account",
                    "Ce compte n'appartient pas au bénéficiaire sélectionné.",
                )

        # Trainer mode cross-checks
        tpm = cleaned.get("trainer_payment_mode")
        if tpm == Expense.TrainerPaymentMode.PER_FORMATION:
            if not cleaned.get("linked_formation"):
                self.add_error(
                    "linked_formation", "La formation liée est requise pour ce mode."
                )
        if tpm == Expense.TrainerPaymentMode.PER_SESSION:
            if not cleaned.get("allocated_to_session"):
                self.add_error(
                    "allocated_to_session",
                    "La session est requise pour le mode 'Par session'.",
                )

        return cleaned

    def save(self, commit=True):
        expense = super().save(commit=False)
        # Mirror gross_amount into Expense.amount (net computed in model.save())
        if expense.gross_amount is not None:
            expense.amount = expense.gross_amount  # model.save() will subtract IRG
        if commit:
            expense.save()
        return expense


class ExpenseFilterForm(ISIFormMixin, forms.Form):
    q = forms.CharField(
        label="Recherche",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Description, bénéficiaire…"}),
    )
    category = forms.ModelChoiceField(
        label="Catégorie",
        required=False,
        queryset=ExpenseCategory.objects.all(),
        empty_label="Toutes",
    )
    beneficiary = forms.ModelChoiceField(
        label="Bénéficiaire",
        required=False,
        queryset=Beneficiary.objects.filter(is_active=True).order_by("name"),
        empty_label="Tous",
    )
    beneficiary_type = forms.ModelChoiceField(
        label="Type de bénéficiaire",
        required=False,
        queryset=BeneficiaryType.objects.filter(is_active=True).order_by("name"),
        empty_label="Tous les types",
    )
    approval_status = forms.ChoiceField(
        label="Approbation",
        required=False,
        choices=[("", "Tous")] + Expense.ApprovalStatus.choices,
    )
    trainer_payment_mode = forms.ChoiceField(
        label="Mode formateur",
        required=False,
        choices=[("", "Tous")] + Expense.TrainerPaymentMode.choices,
    )
    date_from = forms.DateField(
        label="Du",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    date_to = forms.DateField(
        label="Au",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    fiscal_year = forms.IntegerField(
        label="Exercice",
        required=False,
        widget=forms.NumberInput(attrs={"placeholder": "ex. 2026"}),
    )
    quarter = forms.ChoiceField(
        label="Trimestre",
        required=False,
        choices=[("", "Tous"), ("1", "T1"), ("2", "T2"), ("3", "T3"), ("4", "T4")],
    )
    g50_month = forms.DateField(
        label="Mois G50",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        help_text="Filtre par mois G50 (date exacte du premier du mois).",
    )
    payment_date_from = forms.DateField(
        label="Réglé du",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    payment_date_to = forms.DateField(
        label="Réglé au",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    amount_min = forms.DecimalField(
        label="Montant min (DA)",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"placeholder": "0"}),
    )
    amount_max = forms.DecimalField(
        label="Montant max (DA)",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={"placeholder": "ex. 100000"}),
    )
    allocation = forms.ChoiceField(
        label="Affectation",
        required=False,
        choices=[
            ("", "Toutes"),
            ("session", "Session"),
            ("project", "Projet"),
            ("overhead", "Frais généraux"),
        ],
    )
    has_irg = forms.ChoiceField(
        label="IRG",
        required=False,
        choices=[("", "Tous"), ("yes", "Avec IRG"), ("no", "Sans IRG")],
    )


class ExpenseCategoryForm(ISIFormMixin, forms.ModelForm):
    class Meta:
        model = ExpenseCategory
        fields = ["name", "description", "is_direct_cost", "color"]
        labels = {
            "name": "Nom",
            "description": "Description",
            "is_direct_cost": "Coût direct",
            "color": "Couleur (hex)",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "color": forms.TextInput(
                attrs={"type": "color", "style": "height:38px;padding:4px 6px;"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = False


# ---------------------------------------------------------------------------
# Financial period form
# ---------------------------------------------------------------------------


class FinancialPeriodForm(ISIFormMixin, forms.ModelForm):
    class Meta:
        model = FinancialPeriod
        fields = ["name", "period_type", "date_start", "date_end", "notes"]
        labels = {
            "name": "Nom",
            "period_type": "Type",
            "date_start": "Début",
            "date_end": "Fin",
            "notes": "Notes",
        }
        widgets = {
            "date_start": forms.DateInput(attrs={"type": "date"}),
            "date_end": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["notes"].required = False

    def clean(self):
        cleaned = super().clean()
        date_start = cleaned.get("date_start")
        date_end = cleaned.get("date_end")
        if date_start and date_end and date_end < date_start:
            raise ValidationError(
                "La date de fin doit être postérieure à la date de début."
            )
        return cleaned


# ---------------------------------------------------------------------------
# Reporting filter form
# ---------------------------------------------------------------------------


class ReportFilterForm(ISIFormMixin, forms.Form):
    """
    Used by financial analytics views.
    Either select a named FinancialPeriod OR specify a manual date range.
    """

    period = forms.ModelChoiceField(
        label="Période",
        required=False,
        queryset=FinancialPeriod.objects.order_by("-date_start"),
        empty_label="— Période personnalisée —",
    )
    date_from = forms.DateField(
        label="Du",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    date_to = forms.DateField(
        label="Au",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    invoice_type = forms.ChoiceField(
        label="Type",
        required=False,
        choices=[("", "Formation + Étude")] + Invoice.InvoiceType.choices,
    )
    phase = forms.ChoiceField(
        label="Phase",
        required=False,
        choices=[("", "Toutes")] + Invoice.Phase.choices,
    )

    def clean(self):
        cleaned = super().clean()
        period = cleaned.get("period")
        date_from = cleaned.get("date_from")
        date_to = cleaned.get("date_to")
        if not period:
            if not date_from:
                self.add_error(
                    "date_from",
                    "Sélectionnez une période ou saisissez une date de début.",
                )
            if not date_to:
                self.add_error(
                    "date_to", "Sélectionnez une période ou saisissez une date de fin."
                )
            if date_from and date_to and date_to < date_from:
                raise ValidationError(
                    "La date de fin doit être postérieure à la date de début."
                )
        return cleaned
