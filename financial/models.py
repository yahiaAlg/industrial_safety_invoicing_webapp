"""
Financial models — v4.0
Invoices (3-stage lifecycle: proforma → BC → finale), line items with flexible
pricing modes, payments, credit notes, expenses.

Changes in v4.2
──────────────────────────
* Invoice.finalize() bugfix — reference_year now defaults to invoice_date's
  year instead of timezone.now().year. Finalizing a backfilled old invoice
  now correctly consumes THAT year's counter instead of the current year's.
  reference_year can still be passed explicitly to override.
* ProformaCreateForm — manual reference override (override_reference) and
  sequence_year (forces which year's counter a new proforma consumes) for
  urgent corrections / historical backfills. See financial/forms.py.

Changes in v4.1
──────────────────────────
* Expense.timbre_fiscal — new PERSISTED field, computed in Expense.save()
  from gross_amount (HT+TVA), same tiered slabs as the live form preview.
  Stored for reporting/stats; does not feed into `amount`.
* Payment.proof_document — file upload (receipt / virement / chèque scan)
  attached to a payment as documentary proof.

Changes in v3.2 over v3.1
──────────────────────────
* Invoice.client_tin_snapshot — snapshots Client.tin at finalization.
* Invoice.finalize() — copies client.tin into the snapshot.

Changes in v3.1 over v3.0
──────────────────────────
* Invoice.PaymentMode TextChoices added (ESPECE, VIREMENT, CHEQUE, TRAITE, AUTRE).
* Invoice.mode_reglement field — set at finalization, drives timbre fiscal.
* Invoice.timbre_fiscal property — cash stamp tax per Algerian fiscal slabs.
* Invoice.amount_net_a_payer property — TTC + timbre (espèce only).
* Invoice.timbre_rate_display property — human-readable slab label for templates.
* Proforma reference format changed:
    OLD  {prefix}-{YEAR}-{NNN}   →   PF-F-2026-001
    NEW  {prefix}-{NNN}-{YEAR}   →   FP-001-2026
  Finale reference format UNCHANGED: {prefix}-{YEAR}-{NNN}.
* due_date remains nullable/optional.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Sum
from django.utils import timezone

from clients.models import Client
from core.base_models import TimeStampedModel

# ======================================================================= #
# Invoice
# ======================================================================= #


class Invoice(TimeStampedModel):
    """
    A proforma or final tax invoice issued to a client.

    Lifecycle
    ---------
    PROFORMA phase
        status = draft  → (mark as sent) → sent
        Once a Bon de Commande number is recorded, the proforma may be finalized.

    FINALE phase
        status = unpaid → partially_paid → paid
               unpaid   → voided
               paid     → [issue CreditNote; cannot void directly]

    Sequential numbers
        proforma_reference  FP-{NNN}-{YEAR} / FP-E-{NNN}-{YEAR}  — set on create
        reference           F-{NNN}-{YEAR}    / E-{NNN}-{YEAR}      — set on finalize

    Business rules enforced here
        * Line items cannot be edited after finalization (enforced in item.save()).
        * TVA rate is snapshotted; auto-set to 0 when client.is_tva_exempt is True.
        * amount_paid / amount_remaining are denormalized columns kept in sync by
          Payment.save() / delete() so Client aggregate queries need no joins.
        * timbre_fiscal is a computed property — never persisted.
        * mode_reglement must be set before or during finalize(); espèce triggers
          timbre fiscal display on the printed invoice.
    """

    class InvoiceType(models.TextChoices):
        FORMATION = "formation", "Formation"
        ETUDE = "etude", "Étude"

    class Phase(models.TextChoices):
        PROFORMA = "proforma", "Facture Proforma"
        FINALE = "finale", "Facture Finale"

    class Status(models.TextChoices):
        DRAFT = "draft", "Brouillon"
        SENT = "sent", "Envoyée au client"
        UNPAID = "unpaid", "Non payée"
        PARTIALLY_PAID = "partially_paid", "Partiellement payée"
        PAID = "paid", "Payée"
        VOIDED = "voided", "Annulée"
        CREDIT_NOTE = "credit_note", "Avoir émis"

    class PaymentMode(models.TextChoices):
        ESPECE = "espece", "Espèces"
        VIREMENT = "virement", "Virement bancaire"
        CHEQUE = "cheque", "Chèque"
        TRAITE = "traite", "Traite"
        AUTRE = "autre", "Autre"

    # ---- Identity ---------------------------------------------------- #
    invoice_type = models.CharField(
        max_length=20, choices=InvoiceType.choices, verbose_name="Type", db_index=True
    )
    phase = models.CharField(
        max_length=10,
        choices=Phase.choices,
        default=Phase.PROFORMA,
        verbose_name="Phase",
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Statut",
        db_index=True,
    )

    # ---- References -------------------------------------------------- #
    proforma_reference = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="N° Proforma",
        help_text="Généré automatiquement à la création. Format : {prefix}-{NNN}-{YEAR}.",
    )
    reference = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True,
        verbose_name="N° Facture finale",
        help_text="Généré automatiquement à la finalisation — séquence indépendante.",
    )
    page_ref = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Réf. interne (en-tête)",
        help_text="Ex. GSCOM — affiché en haut à droite du document imprimé.",
    )

    # ---- Parties ----------------------------------------------------- #
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT, related_name="invoices", verbose_name="Client"
    )
    session = models.ForeignKey(
        "formations.Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name="Session (traçabilité)",
    )
    study_project = models.ForeignKey(
        "etudes.StudyProject",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
        verbose_name="Projet d'étude (traçabilité)",
    )

    # ---- Client snapshot — frozen at finalization -------------------- #
    client_name_snapshot = models.CharField(
        max_length=255, blank=True, verbose_name="Nom client (snapshot)"
    )
    client_address_snapshot = models.TextField(
        blank=True, verbose_name="Adresse client (snapshot)"
    )
    client_type_snapshot = models.CharField(
        max_length=20, blank=True, verbose_name="Type client (snapshot)"
    )
    client_nif_snapshot = models.CharField(
        max_length=100, blank=True, verbose_name="NIF client (snapshot)"
    )
    client_nis_snapshot = models.CharField(
        max_length=100, blank=True, verbose_name="NIS client (snapshot)"
    )
    client_rc_snapshot = models.CharField(
        max_length=100, blank=True, verbose_name="RC client (snapshot)"
    )
    client_ai_snapshot = models.CharField(
        max_length=100, blank=True, verbose_name="ART.I client (snapshot)"
    )
    client_nin_snapshot = models.CharField(
        max_length=20, blank=True, verbose_name="NIN client (snapshot)"
    )
    client_rib_snapshot = models.CharField(
        max_length=255, blank=True, verbose_name="RIB client (snapshot)"
    )
    # v3.2: TIN snapshot
    client_tin_snapshot = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="TIN (snapshot)",
        help_text="Frozen at finalization.",
    )

    # ---- Dates ------------------------------------------------------- #
    invoice_date = models.DateField(
        verbose_name="Date d'émission",
        help_text="Date de la proforma; conservée sur la finale.",
    )
    validity_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de validité (proforma)",
        help_text="Défaut : 30 jours après la date d'émission.",
    )
    due_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date d'échéance (finale)",
        help_text="Optionnel — si non renseignée, n'apparaît pas sur la facture imprimée.",
    )
    finalized_at = models.DateTimeField(
        null=True, blank=True, verbose_name="Date de finalisation"
    )

    # ---- Bon de Commande --------------------------------------------- #
    bon_commande_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="N° Bon de Commande client",
        help_text="Requis pour finaliser la facture.",
    )
    bon_commande_date = models.DateField(
        null=True, blank=True, verbose_name="Date du BC"
    )
    bon_commande_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Montant BC (vérification)",
        help_text="Optionnel — pour cross-check avec le montant de la facture.",
    )
    bon_commande_scan = models.FileField(
        upload_to="bons_commande/%Y/%m/", blank=True, verbose_name="Scan BC (optionnel)"
    )

    # ---- Amounts (DA) ------------------------------------------------ #
    amount_ht = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant HT (DA)",
    )
    tva_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.09"),
        verbose_name="Taux TVA",
        help_text="9% pour les formations ; 19% pour les études. 0 si client exonéré.",
    )
    amount_tva = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant TVA (DA)",
    )
    amount_ttc = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant TTC (DA)",
    )
    amount_paid = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Montant payé (DA)",
    )
    amount_remaining = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Reste à payer (DA)",
    )
    amount_in_words = models.CharField(
        max_length=500,
        blank=True,
        verbose_name="Montant en lettres",
        help_text="Généré automatiquement lors de la finalisation.",
    )

    # ---- Mode de règlement (v3.1) ------------------------------------ #
    mode_reglement = models.CharField(
        max_length=20,
        choices=PaymentMode.choices,
        blank=True,
        default="",
        verbose_name="Mode de règlement",
        help_text="Choisi à la finalisation. Espèces déclenche le calcul du timbre fiscal.",
    )

    # ---- Notes & footer ---------------------------------------------- #
    notes = models.TextField(blank=True, verbose_name="Notes internes")
    footer_text = models.TextField(
        blank=True,
        verbose_name="Pied de page (personnalisé)",
        help_text="Conditions de paiement, RIB, etc. Écrase le pied de page par défaut.",
    )

    class Meta:
        verbose_name = "Facture"
        verbose_name_plural = "Factures"
        ordering = ["-invoice_date", "-proforma_reference"]
        indexes = [
            models.Index(fields=["phase", "status"]),
            models.Index(fields=["client", "phase", "status"]),
            models.Index(fields=["invoice_type", "invoice_date"]),
        ]

    def __str__(self):
        ref = self.reference or self.proforma_reference
        return f"{ref} — {self.client.name}"

    # ------------------------------------------------------------------ #
    # Reference generation
    # ------------------------------------------------------------------ #

    @classmethod
    def _next_proforma_reference(cls, invoice_type: str, year: int) -> str:
        """
        v3.1 format: {prefix}-{NNN}-{YEAR}   e.g.  FP-001-2026
        Sequence stored in InvoiceSequence; can be overridden via admin/view.
        """
        from core.models import BureauEtudeInfo, FormationInfo

        if invoice_type == cls.InvoiceType.FORMATION:
            prefix = FormationInfo.get_instance().proforma_prefix or "FP"
        else:
            prefix = BureauEtudeInfo.get_instance().proforma_prefix or "FP-E"

        with transaction.atomic():
            seq, _ = InvoiceSequence.objects.select_for_update().get_or_create(
                invoice_type=invoice_type,
                year=year,
                phase=InvoiceSequence.Phase.PROFORMA,
                defaults={"last_number": 0},
            )
            seq.last_number += 1
            seq.save(update_fields=["last_number"])
            count = seq.last_number

        return f"{prefix}-{count:03d}-{year}"

    @classmethod
    def _next_final_reference(cls, invoice_type: str, year: int) -> str:
        """F-NNN-YYYY / E-NNN-YYYY — gapless sequence, assigned at finalization.
        INCREMENTS the counter — call only during actual finalization."""
        from core.models import BureauEtudeInfo, FormationInfo

        if invoice_type == cls.InvoiceType.FORMATION:
            prefix = FormationInfo.get_instance().invoice_prefix or "F"
        else:
            prefix = BureauEtudeInfo.get_instance().invoice_prefix or "E"

        with transaction.atomic():
            seq, _ = InvoiceSequence.objects.select_for_update().get_or_create(
                invoice_type=invoice_type,
                year=year,
                phase=InvoiceSequence.Phase.FINALE,
                defaults={"last_number": 0},
            )
            seq.last_number += 1
            seq.save(update_fields=["last_number"])
            count = seq.last_number

        return f"{prefix}-{count:03d}-{year}"

    @classmethod
    def _peek_final_reference(cls, invoice_type: str, year: int) -> str:
        """Return what the next final reference WOULD be without incrementing the counter.
        Use this for UI previews only — never during actual finalization."""
        from core.models import BureauEtudeInfo, FormationInfo

        if invoice_type == cls.InvoiceType.FORMATION:
            prefix = FormationInfo.get_instance().invoice_prefix or "F"
        else:
            prefix = BureauEtudeInfo.get_instance().invoice_prefix or "E"

        seq = InvoiceSequence.objects.filter(
            invoice_type=invoice_type,
            year=year,
            phase=InvoiceSequence.Phase.FINALE,
        ).first()
        count = (seq.last_number if seq else 0) + 1
        return f"{prefix}-{count:03d}-{year}"

    # ------------------------------------------------------------------ #
    # Timbre fiscal — v3.1 (espèce only, never persisted)
    # ------------------------------------------------------------------ #

    @property
    def timbre_fiscal(self) -> Decimal:
        """
        Stamp duty applicable ONLY when mode_reglement == 'espece'.
        Base = amount_ttc (HT + TVA).

        Algerian fiscal slabs (Article 254 du Code des Timbres):
            TTC <      300 DA  →  0      (exempt)
            300 ≤ TTC ≤  30 000 DA  →  1.0 %
         30 001 ≤ TTC ≤ 100 000 DA  →  1.5 %
                 TTC >  100 000 DA  →  2.0 %
        """
        if self.mode_reglement != self.PaymentMode.ESPECE:
            return Decimal("0")
        base = self.amount_ttc
        if base < Decimal("300"):
            return Decimal("0")
        elif base <= Decimal("30000"):
            rate = Decimal("0.010")
        elif base <= Decimal("100000"):
            rate = Decimal("0.015")
        else:
            rate = Decimal("0.020")
        return (base * rate).quantize(Decimal("0.01"))

    @property
    def amount_net_a_payer(self) -> Decimal:
        """Total due including timbre fiscal (equals amount_ttc when mode ≠ espèce)."""
        return self.amount_ttc + self.timbre_fiscal

    @property
    def timbre_rate_display(self) -> str:
        """Human-readable slab label for template / admin use."""
        if self.mode_reglement != self.PaymentMode.ESPECE:
            return ""
        base = self.amount_ttc
        if base < Decimal("300"):
            return ""
        elif base <= Decimal("30000"):
            return "1 %"
        elif base <= Decimal("100000"):
            return "1,5 %"
        return "2 %"

    # ------------------------------------------------------------------ #
    # Finalization
    # ------------------------------------------------------------------ #

    def finalize(self, amount_in_words: str = "", reference_year: int = None) -> None:
        """
        Promote a proforma to a finalized invoice.

        Validates BC number presence and client profile completeness.
        Snapshots client fields; auto-zeroes TVA for exempt clients.
        Assigns the final sequential reference; sets status → UNPAID.

        The caller should set mode_reglement before calling finalize() when
        the payment mode is known at that point.

        reference_year defaults to invoice_date's year (NOT today's date —
        finalizing an old backfilled invoice must consume that year's
        counter, not the current one). Pass reference_year explicitly to
        override, e.g. when deliberately filing under the finalization year
        instead.
        """
        if self.phase == self.Phase.FINALE:
            raise ValidationError("Cette facture est déjà finalisée.")

        if not self.bon_commande_number:
            raise ValidationError(
                "Impossible de finaliser sans numéro de Bon de Commande."
            )

        missing = self.client.missing_fields_for_invoice()
        if missing:
            raise ValidationError(
                f"Profil client incomplet. Champs manquants : {', '.join(missing)}."
            )

        c = self.client

        # ── Freeze proforma state before any mutations ─────────────────
        ProformaSnapshot.objects.update_or_create(
            invoice=self,
            defaults=dict(
                proforma_reference=self.proforma_reference,
                invoice_type=self.invoice_type,
                invoice_date=self.invoice_date,
                validity_date=self.validity_date,
                page_ref=self.page_ref,
                amount_ht=self.amount_ht,
                tva_rate=self.tva_rate,
                amount_tva=self.amount_tva,
                amount_ttc=self.amount_ttc,
                bon_commande_number=self.bon_commande_number,
                bon_commande_date=self.bon_commande_date,
                bon_commande_amount=self.bon_commande_amount,
                notes=self.notes,
                footer_text=self.footer_text,
                client_name=c.name,
                client_address=c.address,
                client_type=c.client_type,
                client_nif=c.nif,
                client_nis=c.nis,
                client_rc=c.rc,
                client_ai=c.article_imposition,
                client_nin=c.nin,
                client_rib=c.rib,
                client_tin=c.tin,
            ),
        )

        self.client_name_snapshot = c.name
        self.client_address_snapshot = c.address
        self.client_type_snapshot = c.client_type
        self.client_nif_snapshot = c.nif
        self.client_nis_snapshot = c.nis
        self.client_rc_snapshot = c.rc
        self.client_ai_snapshot = c.article_imposition
        self.client_nin_snapshot = c.nin
        self.client_rib_snapshot = c.rib
        self.client_tin_snapshot = c.tin  # v3.2

        if c.is_tva_exempt:
            self.tva_rate = Decimal("0.00")
            self.amount_tva = Decimal("0.00")
            self.amount_ttc = self.amount_ht

        year = reference_year or self.invoice_date.year
        self.reference = self._next_final_reference(self.invoice_type, year)
        self.phase = self.Phase.FINALE
        self.status = self.Status.UNPAID
        self.finalized_at = timezone.now()
        self.amount_remaining = self.amount_ttc
        if amount_in_words:
            self.amount_in_words = amount_in_words

        self.save()

    # ------------------------------------------------------------------ #
    # Amount calculation
    # ------------------------------------------------------------------ #

    def recalculate_amounts(self) -> None:
        """
        Recompute totals from line items.
        Called by InvoiceItem.save() and InvoiceItem.delete().
        No-op on finalized invoices (line items are locked).
        """
        if self.phase == self.Phase.FINALE:
            return

        total_ht = self.items.aggregate(total=Sum("total_ht"))["total"] or Decimal("0")
        self.amount_ht = total_ht
        self.amount_tva = (total_ht * self.tva_rate).quantize(Decimal("0.01"))
        self.amount_ttc = self.amount_ht + self.amount_tva
        self.amount_remaining = self.amount_ttc - self.amount_paid
        self.save(
            update_fields=["amount_ht", "amount_tva", "amount_ttc", "amount_remaining"]
        )

    def refresh_payment_totals(self) -> None:
        """Recompute amount_paid / amount_remaining from confirmed payments."""
        paid = self.payments.filter(status=Payment.Status.CONFIRMED).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0")
        self.amount_paid = paid
        self.amount_remaining = max(self.amount_ttc - paid, Decimal("0"))

        if self.phase == self.Phase.FINALE and self.status not in [
            self.Status.VOIDED,
            self.Status.CREDIT_NOTE,
        ]:
            if self.amount_remaining <= 0:
                self.status = self.Status.PAID
            elif self.amount_paid > 0:
                self.status = self.Status.PARTIALLY_PAID
            else:
                self.status = self.Status.UNPAID

        self.save(update_fields=["amount_paid", "amount_remaining", "status"])

    # ------------------------------------------------------------------ #
    # Save
    # ------------------------------------------------------------------ #

    def save(self, *args, **kwargs):
        if not self.pk:
            if not self.proforma_reference:
                year = (self.invoice_date or timezone.now().date()).year
                self.proforma_reference = self._next_proforma_reference(
                    self.invoice_type, year
                )
            if not self.validity_date and self.invoice_date:
                from datetime import timedelta

                self.validity_date = self.invoice_date + timedelta(days=30)
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------ #
    # Status helpers
    # ------------------------------------------------------------------ #

    @property
    def is_locked(self) -> bool:
        return self.phase == self.Phase.FINALE

    @property
    def is_payable(self) -> bool:
        return self.phase == self.Phase.FINALE and self.status in [
            self.Status.UNPAID,
            self.Status.PARTIALLY_PAID,
        ]

    @property
    def has_bon_commande(self) -> bool:
        return bool(self.bon_commande_number)

    @property
    def can_be_finalized(self) -> bool:
        return (
            self.phase == self.Phase.PROFORMA
            and self.has_bon_commande
            and self.client.is_invoice_ready
        )

    @property
    def is_overdue(self) -> bool:
        return (
            self.due_date is not None
            and self.due_date < timezone.now().date()
            and self.status in [self.Status.UNPAID, self.Status.PARTIALLY_PAID]
        )

    @property
    def days_overdue(self) -> int:
        if not self.is_overdue:
            return 0
        return (timezone.now().date() - self.due_date).days

    @property
    def payment_completion_percent(self) -> float:
        if not self.amount_ttc:
            return 0.0
        return round(float(self.amount_paid / self.amount_ttc) * 100, 1)

    def void(self, reason: str = "") -> None:
        if self.phase != self.Phase.FINALE:
            raise ValidationError("Seule une facture finale peut être annulée.")
        if self.status == self.Status.PAID:
            raise ValidationError(
                "Impossible d'annuler une facture déjà payée. Émettez un avoir."
            )
        self.status = self.Status.VOIDED
        if reason:
            self.notes = f"[ANNULÉ] {reason}\n\n{self.notes}".strip()
        self.save(update_fields=["status", "notes"])


# ======================================================================= #
# Invoice line items
# ======================================================================= #


class InvoiceItem(TimeStampedModel):
    """
    A single line on an invoice.

    PricingMode determines how total_ht is computed:
        per_person           → unit_price_ht × nb_persons
        per_day              → unit_price_ht × nb_days
        per_person_per_day   → unit_price_ht × nb_persons × nb_days
        per_unit             → unit_price_ht × nb_persons (nb_persons = nombre d'unités/études réalisées)
        forfait              → unit_price_ht (fixed)

    Editing is blocked when the parent invoice is finalized (phase=FINALE).
    """

    class PricingMode(models.TextChoices):
        PER_PERSON = "per_person", "Par personne"
        PER_DAY = "per_day", "Par jour"
        PER_PERSON_PER_DAY = "per_person_per_day", "Par personne × par jour"
        PER_UNIT = "per_unit", "Par unité (étude)"
        FORFAIT = "forfait", "Forfait"

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="items", verbose_name="Facture"
    )
    order = models.PositiveIntegerField(default=1, verbose_name="Ordre")
    description = models.CharField(
        max_length=500,
        verbose_name="Désignation",
        help_text="Titre de la formation ou du livrable d'étude.",
    )
    pricing_mode = models.CharField(
        max_length=20,
        choices=PricingMode.choices,
        default=PricingMode.PER_PERSON,
        verbose_name="Mode de tarification",
    )
    nb_persons = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("1.00"),
        verbose_name="Nombre de personnes",
        help_text="Utilisé pour per_person, per_person_per_day et per_unit (= nombre d'unités).",
    )
    nb_days = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("1.00"),
        verbose_name="Nombre de jours",
        help_text="Utilisé pour per_day et per_person_per_day.",
    )
    unit_price_ht = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Prix unitaire HT (DA)"
    )
    discount_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Remise (%)",
    )
    total_ht = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Total HT (DA)",
        help_text="Calculé automatiquement selon le mode de tarification.",
    )

    class Meta:
        verbose_name = "Ligne de facture"
        verbose_name_plural = "Lignes de facture"
        ordering = ["invoice", "order"]

    def __str__(self):
        return f"{self.invoice.proforma_reference} — {self.description}"

    def _compute_total_ht(self) -> Decimal:
        mode = self.pricing_mode
        if mode == self.PricingMode.PER_PERSON:
            base = self.unit_price_ht * self.nb_persons
        elif mode == self.PricingMode.PER_DAY:
            base = self.unit_price_ht * self.nb_days
        elif mode == self.PricingMode.PER_PERSON_PER_DAY:
            # unit_price_ht = total group price for the full duration
            # → prorate: divide by nb_persons to get per-person daily rate,
            #   then multiply by nb_days actually delivered.
            base = (self.unit_price_ht / self.nb_persons) * self.nb_days
        elif mode == self.PricingMode.PER_UNIT:
            # nb_persons holds the number of units (études) performed.
            base = self.unit_price_ht * self.nb_persons
        else:  # forfait
            base = self.unit_price_ht
        discount = base * (self.discount_percent / Decimal("100"))
        return (base - discount).quantize(Decimal("0.01"))

    def save(self, *args, **kwargs):
        if self.invoice.is_locked:
            raise ValidationError(
                "Les lignes d'une facture finalisée ne peuvent pas être modifiées. "
                "Émettez un avoir si nécessaire."
            )
        self.total_ht = self._compute_total_ht()
        super().save(*args, **kwargs)
        self.invoice.recalculate_amounts()

    def delete(self, *args, **kwargs):
        if self.invoice.is_locked:
            raise ValidationError(
                "Les lignes d'une facture finalisée ne peuvent pas être supprimées."
            )
        invoice = self.invoice
        super().delete(*args, **kwargs)
        invoice.recalculate_amounts()


# ======================================================================= #
# Payments
# ======================================================================= #


class Payment(TimeStampedModel):
    """
    A single payment instalment against a finalized invoice.
    Multiple Payment records per Invoice are allowed (partial payments).

    Note: Payment.method records how money was physically received.
    Invoice.mode_reglement is the agreed settlement method and determines
    whether timbre fiscal is applicable.
    """

    class Method(models.TextChoices):
        VIREMENT = "virement", "Virement bancaire"
        CHEQUE = "cheque", "Chèque"
        ESPECES = "especes", "Espèces"
        OTHER = "autre", "Autre"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente de confirmation"
        CONFIRMED = "confirmed", "Confirmé"
        REVERSED = "reversed", "Annulé / retourné"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="payments",
        verbose_name="Facture",
    )
    date = models.DateField(verbose_name="Date de paiement")
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Montant (DA)"
    )
    method = models.CharField(
        max_length=10,
        choices=Method.choices,
        default=Method.VIREMENT,
        verbose_name="Mode de paiement",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.CONFIRMED,
        verbose_name="Statut",
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Référence",
        help_text="N° virement, n° chèque, etc.",
    )
    proof_document = models.FileField(
        upload_to="payment_proofs/%Y/%m/",
        blank=True,
        null=True,
        verbose_name="Justificatif de paiement",
        help_text="Reçu, avis de virement, copie de chèque, etc. (PDF, JPG, PNG).",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Paiement"
        verbose_name_plural = "Paiements"
        ordering = ["-date"]

    def __str__(self):
        return f"Paiement {self.amount} DA — {self.invoice.reference} ({self.date})"

    def clean(self):
        if not self.invoice_id:
            return
        if self.invoice.phase != Invoice.Phase.FINALE:
            raise ValidationError(
                "Les paiements ne sont acceptés que sur les factures finalisées."
            )
        if self.pk is None and not self.invoice.is_payable:
            raise ValidationError(
                f"La facture {self.invoice.reference} n'est pas en attente de paiement."
            )
        if self.amount and self.amount <= 0:
            raise ValidationError("Le montant doit être positif.")

        already_paid = self.invoice.amount_paid
        if self.pk:
            existing_amount = (
                Payment.objects.filter(pk=self.pk)
                .values_list("amount", flat=True)
                .first()
                or 0
            )
            already_paid -= Decimal(str(existing_amount))

        if self.amount and (already_paid + self.amount) > self.invoice.amount_ttc:
            raise ValidationError(
                f"Ce paiement ({self.amount} DA) dépasserait le montant total "
                f"de la facture ({self.invoice.amount_ttc} DA)."
            )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.invoice.refresh_payment_totals()

    def delete(self, *args, **kwargs):
        invoice = self.invoice
        super().delete(*args, **kwargs)
        invoice.refresh_payment_totals()

    @property
    def is_confirmed(self) -> bool:
        return self.status == self.Status.CONFIRMED


# ======================================================================= #
# Credit notes
# ======================================================================= #


class CreditNote(TimeStampedModel):
    """
    A credit note (avoir) that partially or fully reverses a finalized invoice.
    When is_full_reversal is True, the original invoice's status → CREDIT_NOTE.
    """

    original_invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="credit_notes",
        verbose_name="Facture d'origine",
    )
    reference = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="N° Avoir",
        help_text="Généré automatiquement — ex. AV-2026-001.",
    )
    date = models.DateField(verbose_name="Date")
    reason = models.TextField(verbose_name="Motif")
    amount_ht = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Montant HT (DA)"
    )
    tva_rate = models.DecimalField(
        max_digits=5, decimal_places=4, default=Decimal("0.09"), verbose_name="Taux TVA"
    )
    amount_tva = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Montant TVA (DA)"
    )
    amount_ttc = models.DecimalField(
        max_digits=14, decimal_places=2, verbose_name="Montant TTC (DA)"
    )
    is_full_reversal = models.BooleanField(
        default=False, verbose_name="Annulation totale"
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Avoir"
        verbose_name_plural = "Avoirs"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.reference} — avoir sur {self.original_invoice.reference}"

    @classmethod
    def _next_reference(cls, year: int) -> str:
        with transaction.atomic():
            count = (
                cls.objects.select_for_update().filter(date__year=year).count()
            ) + 1
        return f"AV-{year}-{count:03d}"

    def save(self, *args, **kwargs):
        if not self.reference:
            year = (self.date or timezone.now().date()).year
            self.reference = self._next_reference(year)
        self.amount_tva = (self.amount_ht * self.tva_rate).quantize(Decimal("0.01"))
        self.amount_ttc = self.amount_ht + self.amount_tva
        super().save(*args, **kwargs)
        if self.is_full_reversal:
            Invoice.objects.filter(pk=self.original_invoice_id).update(
                status=Invoice.Status.CREDIT_NOTE
            )

    @property
    def coverage_percent(self) -> float:
        if not self.original_invoice.amount_ttc:
            return 0.0
        return round(float(self.amount_ttc / self.original_invoice.amount_ttc) * 100, 1)


# ======================================================================= #
# Beneficiary system — dealers / partners directory
# ======================================================================= #


class BeneficiaryType(TimeStampedModel):
    """
    Type / category of a beneficiary (e.g. Formateur, Hôtel, Commerçant).
    Seeded entries cannot be deleted; users can add their own.
    """

    slug = models.SlugField(
        max_length=50,
        unique=True,
        verbose_name="Slug",
        help_text="Identifiant machine (ex. formateur, hotel).",
    )
    name = models.CharField(max_length=100, unique=True, verbose_name="Libellé")
    color = models.CharField(
        max_length=7, default="#6B7280", verbose_name="Couleur (hex)"
    )
    is_seeded = models.BooleanField(
        default=False,
        verbose_name="Entrée système",
        help_text="Les entrées système ne peuvent pas être supprimées.",
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")

    class Meta:
        verbose_name = "Type de bénéficiaire"
        verbose_name_plural = "Types de bénéficiaires"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def seed_defaults(cls):
        """
        Create the standard seeded types.
        Call from a data migration or management command.
        """
        defaults = [
            ("formateur", "Formateur", "#3B82F6"),
            ("employe", "Employé", "#10B981"),
            ("hotel", "Hôtel / Hébergement", "#F59E0B"),
            ("restaurant", "Restaurant", "#EF4444"),
            ("transport", "Transport / Taxi", "#8B5CF6"),
            ("imprimerie", "Imprimerie / Reprographie", "#EC4899"),
            ("commercant", "Commerçant / Détaillant", "#F97316"),
            ("organisation", "Organisation / Association", "#14B8A6"),
            ("fournisseur", "Fournisseur de matériel", "#64748B"),
            ("autre", "Autre", "#6B7280"),
        ]
        for slug, name, color in defaults:
            cls.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "color": color, "is_seeded": True},
            )


class Beneficiary(TimeStampedModel):
    """
    A registered payee / partner — the "dealers directory".

    Trainers are auto-linked (OneToOne) via Trainer.save().
    Other beneficiaries (hotels, suppliers, …) are created manually
    or via the quick-add modal on the expense form.

    IRG
    ---
    irg_rate = 0      → no withholding (employees, companies with exemption)
    irg_rate = 0.10   → 10% withholding (external trainers under Algerian fiscal law)
    irg_rate is stored here as a default and snapshotted on each Expense.
    """

    name = models.CharField(max_length=255, verbose_name="Nom / Raison sociale")
    beneficiary_type = models.ForeignKey(
        BeneficiaryType,
        on_delete=models.PROTECT,
        related_name="beneficiaries",
        verbose_name="Type",
    )

    # ---- Link to Trainer (optional) ---------------------------------- #
    trainer = models.OneToOneField(
        "formations.Trainer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="beneficiary",
        verbose_name="Formateur lié",
        help_text="Rempli automatiquement pour les formateurs.",
    )
    is_trainer = models.BooleanField(default=False, verbose_name="Est un formateur")
    is_employee = models.BooleanField(
        default=False,
        verbose_name="Est un employé (interne)",
        help_text="True pour les formateurs internes ou le personnel administratif.",
    )

    # ---- Contact & fiscal ------------------------------------------- #
    nif = models.CharField(max_length=100, blank=True, verbose_name="NIF")
    rib = models.CharField(max_length=255, blank=True, verbose_name="RIB")
    phone = models.CharField(max_length=50, blank=True, verbose_name="Téléphone")
    email = models.EmailField(blank=True, verbose_name="Email")
    address = models.TextField(blank=True, verbose_name="Adresse")

    # ---- Rates (snapshotted on expense entry) ------------------------ #
    daily_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name="Tarif journalier (DA)",
    )
    monthly_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name="Tarif mensuel (DA)",
    )

    # ---- IRG default ------------------------------------------------- #
    irg_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0"),
        verbose_name="Taux IRG par défaut",
        help_text="0 pour aucune retenue; 0.10 pour prestataires externes (10%).",
    )

    notes = models.TextField(blank=True, verbose_name="Notes")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Bénéficiaire"
        verbose_name_plural = "Bénéficiaires"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.beneficiary_type})"

    @property
    def default_payment_account(self):
        """Return the default PaymentAccount or None."""
        return self.payment_accounts.filter(is_default=True).first()


class PaymentAccount(TimeStampedModel):
    """
    A payment account / channel belonging to a Beneficiary.

    One beneficiary can have multiple accounts (e.g. CCP + bank virement).
    The expense form shows only accounts belonging to the selected beneficiary.
    A new account can be created via modal without leaving the expense form.
    """

    class AccountType(models.TextChoices):
        ESPECES = "especes", "Espèces"
        BANK = "bank", "Virement bancaire"
        CCP = "ccp", "CCP"
        CIB = "cib", "CIB / Carte bancaire"
        CHEQUE = "cheque", "Chèque"
        AUTRE = "autre", "Autre"

    beneficiary = models.ForeignKey(
        Beneficiary,
        on_delete=models.CASCADE,
        related_name="payment_accounts",
        verbose_name="Bénéficiaire",
    )
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        verbose_name="Type de compte",
    )
    label = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Libellé",
        help_text="Ex. CPA Agence Sétif, CCP 12345-67.",
    )
    account_number = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Numéro / Code",
        help_text="RIB, numéro CCP, code CIB, etc.",
    )
    bank_name = models.CharField(
        max_length=255, blank=True, verbose_name="Banque / Établissement"
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name="Compte par défaut",
        help_text="Un seul compte par défaut par bénéficiaire.",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Compte de paiement"
        verbose_name_plural = "Comptes de paiement"
        ordering = ["-is_default", "account_type", "label"]

    def __str__(self):
        parts = [self.get_account_type_display()]
        if self.label:
            parts.append(self.label)
        if self.account_number:
            parts.append(self.account_number)
        return " — ".join(parts)

    def save(self, *args, **kwargs):
        if self.is_default:
            PaymentAccount.objects.filter(
                beneficiary=self.beneficiary, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


# ======================================================================= #
# Expenses
# ======================================================================= #


class ExpenseCategory(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True, verbose_name="Catégorie")
    description = models.TextField(blank=True, verbose_name="Description")
    is_direct_cost = models.BooleanField(
        default=True,
        verbose_name="Coût direct",
        help_text="Coût direct = imputable à un service ou projet. Indirect = frais généraux.",
    )
    color = models.CharField(
        max_length=7, default="#6B7280", verbose_name="Couleur (hex)"
    )

    class Meta:
        verbose_name = "Catégorie de dépense"
        verbose_name_plural = "Catégories de dépenses"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Expense(TimeStampedModel):
    """
    An operational expenditure incurred by the institute — v4.0.

    Beneficiary & payment
    ─────────────────────
    beneficiary         → registered payee (from the Beneficiary directory)
    payment_account     → which account of that beneficiary was used
    supplier            → legacy free-text fallback (kept for backward compat)

    IRG (withholding tax on service providers)
    ──────────────────────────────────────────
    gross_amount        → montant versé au formateur / prestataire
    irg_rate            → snapshotted from Beneficiary.irg_rate at entry time
    irg_amount          → computed and stored: gross_amount × irg_rate (versé à l'État)
    amount              → coût TOTAL pour l'organisme = gross_amount + irg_amount

    IRG (Impôt sur le Revenu Global) est une charge fiscale SUPPLÉMENTAIRE versée à
    l'État par l'organisme — ce n'est pas une retenue sur le paiement du prestataire.
    For non-trainer expenses irg_rate = 0 so gross_amount == amount.

    Trainer payment modes
    ─────────────────────
    trainer_payment_mode → PER_FORMATION | PER_SESSION | DIRECT | None
    linked_formation     → for PER_FORMATION (covers the whole training program)
    allocated_to_session → for PER_SESSION (one expense per session, existing field)
    training_period_label→ free-text period description e.g. "22-24/12/2023"
    daily_rate_snapshot  → trainer daily rate at time of entry
    monthly_rate_snapshot→ trainer monthly rate at time of entry

    Cost centre allocation — mutually exclusive
    ───────────────────────────────────────────
    allocated_to_session  OR  allocated_to_project  OR  is_overhead = True
    For TRAINER expenses the session link doubles as the cost centre.
    clean() enforces exactly one cost centre.
    """

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "En attente"
        APPROVED = "approved", "Approuvée"
        REJECTED = "rejected", "Refusée"

    class TrainerPaymentMode(models.TextChoices):
        PER_FORMATION = "per_formation", "Par formation (forfait global)"
        PER_SESSION = "per_session", "Par session"
        DIRECT = "direct", "Paiement direct (sans lien)"

    # ---- Core -------------------------------------------------------- #
    date = models.DateField(verbose_name="Date", db_index=True)
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses",
        verbose_name="Catégorie",
    )
    description = models.CharField(max_length=500, verbose_name="Description")

    # ---- Beneficiary -------------------------------------------------- #
    beneficiary = models.ForeignKey(
        Beneficiary,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
        verbose_name="Bénéficiaire",
    )
    payment_account = models.ForeignKey(
        PaymentAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
        verbose_name="Compte de paiement",
    )
    # Legacy free-text (kept for backward compat / non-registered payees)
    supplier = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Fournisseur libre",
        help_text="Utilisez le champ Bénéficiaire de préférence.",
    )

    # ---- Amounts & IRG ----------------------------------------------- #
    gross_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Montant brut (DA)",
        help_text="Montant avant retenue IRG. Rempli automatiquement si IRG = 0.",
    )
    irg_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0"),
        verbose_name="Taux IRG",
        help_text="Retenue à la source (ex. 0.10 = 10%). Copié depuis le bénéficiaire.",
    )
    irg_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name="Montant IRG (DA)",
        help_text="Calculé automatiquement : montant brut × taux IRG.",
    )

    # ---- TVA (on the TTC expense amount) ----------------------------- #
    tva_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0"),
        verbose_name="Taux TVA",
        help_text=(
            "Taux TVA applicable sur cette dépense (ex. 0.09 = 9%, 0.19 = 19%). "
            "Laissez à 0 si exonéré ou inconnu."
        ),
    )
    tva_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        verbose_name="Montant TVA (DA)",
        help_text=(
            "Calculé automatiquement : montant TTC × taux / (1 + taux). "
            "Représente la TVA récupérable / déductible sur cette dépense."
        ),
    )

    # ---- Timbre fiscal (informational — stored for reporting/stats) -- #
    timbre_fiscal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        verbose_name="Timbre fiscal (DA)",
        help_text=(
            "Calculé automatiquement sur HT+TVA (montant brut, déjà TTC) : "
            "≤ 30 000 DA → 1% ; 30 000–100 000 DA → 1,5% ; ≥ 100 000 DA → 2%. "
            "Stocké pour les statistiques — n'affecte pas le coût total (`amount`)."
        ),
    )

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name="Coût total (DA)",
        help_text="Coût total pour l'organisme = montant prestataire + IRG versé à l'État.",
    )
    payment_reference = models.CharField(
        max_length=100, blank=True, verbose_name="Référence de paiement"
    )
    payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date de règlement",
        help_text="Date effective du virement / paiement.",
        db_index=True,
    )

    # ---- Trainer-specific fields ------------------------------------- #
    trainer_payment_mode = models.CharField(
        max_length=20,
        choices=TrainerPaymentMode.choices,
        null=True,
        blank=True,
        verbose_name="Mode de paiement formateur",
        help_text="Renseigner uniquement pour les dépenses liées à un formateur.",
    )
    linked_formation = models.ForeignKey(
        "formations.Formation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trainer_expenses",
        verbose_name="Formation liée (forfait)",
        help_text="Pour le mode 'Par formation' — couvre l'ensemble des sessions.",
    )
    training_period_label = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Période de formation",
        help_text="Ex. '22-24/12/2023' — description libre de la période couverte.",
    )
    daily_rate_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Tarif journalier (snapshot)",
    )
    monthly_rate_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Tarif mensuel (snapshot)",
    )

    # ---- Cost centre allocation --------------------------------------- #
    allocated_to_session = models.ForeignKey(
        "formations.Session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
        verbose_name="Session",
    )
    allocated_to_project = models.ForeignKey(
        "etudes.StudyProject",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
        verbose_name="Projet",
    )
    is_overhead = models.BooleanField(
        default=False,
        verbose_name="Frais généraux",
        help_text="Cocher si non imputable à un service ou projet.",
    )

    # ---- Archiving / organization ------------------------------------ #
    fiscal_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Exercice fiscal",
        help_text="Rempli automatiquement d'après la date.",
        db_index=True,
    )
    quarter = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="Trimestre",
        help_text="1–4, calculé automatiquement.",
    )
    g50_month = models.DateField(
        null=True,
        blank=True,
        verbose_name="Mois G50",
        help_text="Premier jour du mois de déclaration G50 (ex. 2026-01-01 pour janvier 2026). Période fiscale générale — non liée au formateur.",
        db_index=True,
    )

    # ---- Documents & approval ---------------------------------------- #
    receipt = models.FileField(
        upload_to="receipts/%Y/%m/", blank=True, verbose_name="Justificatif"
    )
    receipt_missing = models.BooleanField(
        default=False, verbose_name="Justificatif manquant"
    )
    approval_status = models.CharField(
        max_length=10,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.APPROVED,
        verbose_name="Statut d'approbation",
    )
    approval_notes = models.TextField(blank=True, verbose_name="Notes d'approbation")
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Dépense"
        verbose_name_plural = "Dépenses"
        ordering = ["-date"]
        indexes = [
            models.Index(fields=["date"]),
            models.Index(fields=["approval_status"]),
            models.Index(fields=["category"]),
            models.Index(fields=["fiscal_year", "quarter"]),
            models.Index(fields=["beneficiary"]),
        ]

    def __str__(self):
        payee = str(self.beneficiary) if self.beneficiary_id else self.supplier or "—"
        return f"{self.date} — {self.description} ({self.amount} DA) [{payee}]"

    # ------------------------------------------------------------------ #
    # Timbre fiscal — tiered slab on HT+TVA (gross_amount is already the
    # TTC figure by the time save() runs — see clean() in ExpenseForm).
    # ------------------------------------------------------------------ #

    @staticmethod
    def _compute_timbre_fiscal(base: Decimal) -> Decimal:
        """
        base ≤  30 000 DA        → 1%
        30 000 < base < 100 000  → 1.5%
        base ≥ 100 000 DA        → 2%

        Unlike Invoice.timbre_fiscal, this is unconditional (Expense has no
        payment-mode field to gate on) and does NOT feed into `amount` —
        it's stored purely for reporting/stats.
        """
        if not base:
            return Decimal("0")
        if base <= Decimal("30000"):
            rate = Decimal("0.01")
        elif base < Decimal("100000"):
            rate = Decimal("0.015")
        else:
            rate = Decimal("0.02")
        return (base * rate).quantize(Decimal("0.01"))

    # ------------------------------------------------------------------ #
    # Save — auto-compute IRG, gross_amount, fiscal_year, quarter
    # ------------------------------------------------------------------ #

    def save(self, *args, **kwargs):
        # Timbre fiscal — user-editable (see ExpenseForm); only applies when the
        # expense was paid in cash. Defaults to 0 and is left as submitted —
        # the JS "Suggérer" button pre-fills the computed slab value client-side,
        # but save() must NOT silently overwrite a manually entered amount.
        # Resolved BEFORE the total-cost computation below so it is included
        # in `amount` regardless of whether the entered figure was HT or TTC.
        if self.timbre_fiscal is None:
            self.timbre_fiscal = Decimal("0.00")

        # Compute IRG and total cost
        if self.gross_amount is not None:
            self.irg_amount = (self.gross_amount * self.irg_rate).quantize(
                Decimal("0.01")
            )
            # IRG is paid ADDITIONALLY to the State — total org cost = gross + IRG + timbre
            self.amount = self.gross_amount + self.irg_amount + self.timbre_fiscal
        else:
            # gross_amount not provided — treat amount as net (no IRG)
            self.gross_amount = self.amount
            self.irg_amount = Decimal("0")
            self.amount = self.gross_amount + self.timbre_fiscal

        # Compute TVA extracted from the TTC amount (gross_amount = TTC paid)
        tva_rate = self.tva_rate or Decimal("0")
        if tva_rate > 0 and self.gross_amount:
            self.tva_amount = (self.gross_amount * tva_rate / (1 + tva_rate)).quantize(
                Decimal("0.01")
            )
        else:
            self.tva_amount = Decimal("0")

        # Auto-fill fiscal metadata
        if self.date:
            self.fiscal_year = self.date.year
            self.quarter = (self.date.month - 1) // 3 + 1

        super().save(*args, **kwargs)

    # ------------------------------------------------------------------ #
    # Validation
    # ------------------------------------------------------------------ #

    def clean(self):
        filled = sum(
            [
                bool(self.allocated_to_session_id),
                bool(self.allocated_to_project_id),
                bool(self.is_overhead),
            ]
        )
        if filled > 1:
            raise ValidationError(
                "Une dépense ne peut être imputée qu'à un seul centre de coût."
            )

        # Trainer payment mode cross-field checks (optional — not enforced)
        # PER_FORMATION and PER_SESSION validations are advisory only

        # Payment account must belong to selected beneficiary
        if self.payment_account_id and self.beneficiary_id:
            if self.payment_account.beneficiary_id != self.beneficiary_id:
                raise ValidationError(
                    "Le compte de paiement ne correspond pas au bénéficiaire sélectionné."
                )

    # ------------------------------------------------------------------ #
    # Properties
    # ------------------------------------------------------------------ #

    @property
    def cost_centre_label(self) -> str:
        if self.allocated_to_session_id:
            return str(self.allocated_to_session)
        if self.allocated_to_project_id:
            return str(self.allocated_to_project)
        return "Frais généraux"

    @property
    def needs_action(self) -> bool:
        return (
            self.receipt_missing or self.approval_status == self.ApprovalStatus.PENDING
        )

    @property
    def is_approved(self) -> bool:
        return self.approval_status == self.ApprovalStatus.APPROVED

    @property
    def payee_display(self) -> str:
        """Human-readable payee for templates."""
        if self.beneficiary_id:
            return self.beneficiary.name
        return self.supplier or "—"

    @property
    def has_irg(self) -> bool:
        return self.irg_amount > Decimal("0")

    @property
    def has_tva(self) -> bool:
        return self.tva_amount > Decimal("0")

    @property
    def amount_ht(self) -> Decimal:
        """HT portion of the expense (TTC gross_amount minus TVA)."""
        return (self.gross_amount or Decimal("0")) - self.tva_amount


# ======================================================================= #
# Financial period (reporting helper)
# ======================================================================= #


# ======================================================================= #
# ProformaSnapshot — frozen copy of the proforma before finalization
# ======================================================================= #


class ProformaSnapshot(TimeStampedModel):
    """
    Immutable snapshot of a proforma invoice created at finalization.
    Preserves amounts, client data, and validity info as they were
    before the invoice was promoted to FINALE phase.
    OneToOne with Invoice — one snapshot per finalized invoice.
    """

    invoice = models.OneToOneField(
        Invoice,
        on_delete=models.CASCADE,
        related_name="proforma_snapshot",
        verbose_name="Facture",
    )
    proforma_reference = models.CharField(max_length=50, verbose_name="N° Proforma")
    invoice_type = models.CharField(max_length=20, verbose_name="Type")
    invoice_date = models.DateField(verbose_name="Date d'émission")
    validity_date = models.DateField(null=True, blank=True, verbose_name="Validité")
    page_ref = models.CharField(max_length=100, blank=True, verbose_name="Réf. interne")

    # Amounts as they were BEFORE finalization (TVA may be zeroed for exempt clients)
    amount_ht = models.DecimalField(max_digits=14, decimal_places=2)
    tva_rate = models.DecimalField(max_digits=5, decimal_places=4)
    amount_tva = models.DecimalField(max_digits=14, decimal_places=2)
    amount_ttc = models.DecimalField(max_digits=14, decimal_places=2)

    # BC info
    bon_commande_number = models.CharField(max_length=100, blank=True)
    bon_commande_date = models.DateField(null=True, blank=True)
    bon_commande_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True
    )

    # Client data at time of finalization
    client_name = models.CharField(max_length=255, blank=True)
    client_address = models.TextField(blank=True)
    client_type = models.CharField(max_length=20, blank=True)
    client_nif = models.CharField(max_length=100, blank=True)
    client_nis = models.CharField(max_length=100, blank=True)
    client_rc = models.CharField(max_length=100, blank=True)
    client_ai = models.CharField(max_length=100, blank=True)
    client_nin = models.CharField(max_length=20, blank=True)
    client_rib = models.CharField(max_length=255, blank=True)
    client_tin = models.CharField(max_length=50, blank=True)

    # Notes / footer
    notes = models.TextField(blank=True)
    footer_text = models.TextField(blank=True)

    class Meta:
        verbose_name = "Snapshot proforma"
        verbose_name_plural = "Snapshots proforma"

    def __str__(self):
        return f"Snapshot {self.proforma_reference}"


# ======================================================================= #


class FinancialPeriod(TimeStampedModel):
    """
    A named financial period used to group finalized invoices and expenses
    for reporting.
    """

    class PeriodType(models.TextChoices):
        YEAR = "year", "Exercice annuel"
        QUARTER = "quarter", "Trimestre"
        MONTH = "month", "Mois"
        CUSTOM = "custom", "Période personnalisée"

    name = models.CharField(
        max_length=100, verbose_name="Nom", help_text="Ex. Exercice 2026."
    )
    period_type = models.CharField(
        max_length=10, choices=PeriodType.choices, default=PeriodType.YEAR
    )
    date_start = models.DateField(verbose_name="Début")
    date_end = models.DateField(verbose_name="Fin")
    is_closed = models.BooleanField(
        default=False,
        verbose_name="Clôturé",
        help_text="Une période clôturée ne devrait plus recevoir de nouvelles écritures.",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Période financière"
        verbose_name_plural = "Périodes financières"
        ordering = ["-date_start"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(date_end__gte=models.F("date_start")),
                name="financial_period_end_after_start",
            )
        ]

    def __str__(self):
        return self.name

    def _invoice_qs(self):
        return Invoice.objects.filter(
            phase=Invoice.Phase.FINALE,
            invoice_date__range=[self.date_start, self.date_end],
            status__in=[
                Invoice.Status.UNPAID,
                Invoice.Status.PARTIALLY_PAID,
                Invoice.Status.PAID,
            ],
        )

    @property
    def total_invoiced_ht(self) -> Decimal:
        return self._invoice_qs().aggregate(t=Sum("amount_ht"))["t"] or Decimal("0")

    @property
    def total_collected(self) -> Decimal:
        return Payment.objects.filter(
            date__range=[self.date_start, self.date_end],
            status=Payment.Status.CONFIRMED,
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    @property
    def total_expenses(self) -> Decimal:
        return Expense.objects.filter(
            date__range=[self.date_start, self.date_end],
            approval_status=Expense.ApprovalStatus.APPROVED,
        ).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    @property
    def total_expense_tva(self) -> Decimal:
        return Expense.objects.filter(
            date__range=[self.date_start, self.date_end],
            approval_status=Expense.ApprovalStatus.APPROVED,
        ).aggregate(t=Sum("tva_amount"))["t"] or Decimal("0")

    @property
    def gross_margin(self) -> Decimal:
        return self.total_invoiced_ht - self.total_expenses

    @property
    def formation_revenue_ht(self) -> Decimal:
        return self._invoice_qs().filter(
            invoice_type=Invoice.InvoiceType.FORMATION
        ).aggregate(t=Sum("amount_ht"))["t"] or Decimal("0")

    @property
    def etude_revenue_ht(self) -> Decimal:
        return self._invoice_qs().filter(
            invoice_type=Invoice.InvoiceType.ETUDE
        ).aggregate(t=Sum("amount_ht"))["t"] or Decimal("0")


# ======================================================================= #
# InvoiceSequence  — persistent counter per (type × year × phase)
# ======================================================================= #


class InvoiceSequence(models.Model):
    """
    Stores the last-used counter for proforma and finale invoice references.

    Setting last_number = N - 1 via the admin or the dedicated view means the
    *next* invoice created will receive number N.

    Example: set last_number = 4 → next proforma gets FP-005-2026.
    """

    class Phase(models.TextChoices):
        PROFORMA = "proforma", "Proforma"
        FINALE = "finale", "Finale"

    invoice_type = models.CharField(
        max_length=20,
        choices=Invoice.InvoiceType.choices,
        verbose_name="Type de facture",
    )
    year = models.PositiveSmallIntegerField(verbose_name="Année")
    phase = models.CharField(
        max_length=10,
        choices=Phase.choices,
        verbose_name="Phase",
    )
    last_number = models.PositiveIntegerField(
        default=0,
        verbose_name="Dernier numéro utilisé",
        help_text=(
            "Le prochain numéro sera last_number + 1. "
            "Modifiez ce champ pour reprendre la numérotation à un point précis."
        ),
    )

    class Meta:
        unique_together = [("invoice_type", "year", "phase")]
        verbose_name = "Séquence de facturation"
        verbose_name_plural = "Séquences de facturation"
        ordering = ["-year", "invoice_type", "phase"]

    def __str__(self):
        return (
            f"{self.get_invoice_type_display()} / {self.get_phase_display()} "
            f"{self.year} — dernier n° : {self.last_number:03d}"
        )

    # ------------------------------------------------------------------ #
    # Convenience                                                          #
    # ------------------------------------------------------------------ #

    @property
    def next_number(self) -> int:
        """The number that will be assigned to the next invoice."""
        return self.last_number + 1

    def set_next_number(self, n: int) -> None:
        """
        Set the counter so that the *next* invoice gets number `n`.
        Raises ValueError if n < 1.
        """
        if n < 1:
            raise ValueError("Le numéro de départ doit être ≥ 1.")
        self.last_number = n - 1
        self.save(update_fields=["last_number"])
