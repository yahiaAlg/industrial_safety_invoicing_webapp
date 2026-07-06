"""
Formations models — Training catalog, sessions, enrollments, attestations.
"""

from django.db import models, transaction
from django.db.models import Count, Sum
from django.utils import timezone
from datetime import timedelta

from clients.models import Client
from core.base_models import TimeStampedModel


class FormationCategory(TimeStampedModel):
    code = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="Code branche",
        help_text="Code officiel de la branche professionnelle (ex. ACP, AGR, BTP).",
    )
    name = models.CharField(max_length=255, unique=True, verbose_name="Catégorie")
    description = models.TextField(blank=True, verbose_name="Description")
    color = models.CharField(
        max_length=7,
        default="#3B82F6",
        verbose_name="Couleur (hex)",
        help_text="Couleur d'affichage dans l'interface (ex. #3B82F6).",
    )

    class Meta:
        verbose_name = "Catégorie de formation"
        verbose_name_plural = "Catégories de formation"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class Formation(TimeStampedModel):
    category = models.ForeignKey(
        FormationCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="formations",
        verbose_name="Catégorie",
    )
    title = models.CharField(max_length=255, verbose_name="Titre")
    slug = models.SlugField(
        max_length=255,
        unique=True,
        verbose_name="Slug",
        help_text="Identifiant URL-friendly (généré automatiquement).",
    )
    description = models.TextField(blank=True, verbose_name="Description")
    objectives = models.TextField(blank=True, verbose_name="Objectifs pédagogiques")
    target_audience = models.TextField(blank=True, verbose_name="Public cible")
    prerequisites = models.TextField(blank=True, verbose_name="Prérequis")
    duration_days = models.PositiveIntegerField(default=1, verbose_name="Durée (jours)")
    duration_hours = models.PositiveIntegerField(
        default=8, verbose_name="Durée (heures)"
    )
    base_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name="Prix de base (DA)"
    )
    max_participants = models.PositiveIntegerField(
        default=20, verbose_name="Capacité maximale"
    )
    min_participants = models.PositiveIntegerField(
        default=5, verbose_name="Minimum de participants"
    )
    is_active = models.BooleanField(default=True, verbose_name="Active")
    accreditation_body = models.CharField(
        max_length=255, blank=True, verbose_name="Organisme d'accréditation"
    )
    accreditation_reference = models.CharField(
        max_length=100, blank=True, verbose_name="Référence d'accréditation"
    )

    class Meta:
        verbose_name = "Formation"
        verbose_name_plural = "Formations"
        ordering = ["title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify

            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    @property
    def session_count(self):
        return self.sessions.count()

    @property
    def total_participants_trained(self):
        return Participant.objects.filter(
            session__formation=self, session__status=Session.STATUS_COMPLETED
        ).count()


class Trainer(TimeStampedModel):
    """
    A trainer who delivers sessions.

    trainer_type
    ────────────
    INTERNAL  — salaried employee of the institute. A linked Beneficiary record
                (with is_employee=True) is auto-created/kept in sync on save.
    EXTERNAL  — independent contractor or freelancer.

    IRG withholding (10%) applies only to external trainers under Algerian fiscal law.
    Internal trainers are paid through payroll, not via expense vouchers.
    """

    TRAINER_TYPE_INTERNAL = "internal"
    TRAINER_TYPE_EXTERNAL = "external"
    TRAINER_TYPE_CHOICES = [
        (TRAINER_TYPE_INTERNAL, "Interne (salarié)"),
        (TRAINER_TYPE_EXTERNAL, "Externe (prestataire)"),
    ]

    first_name = models.CharField(max_length=100, verbose_name="Prénom")
    last_name = models.CharField(max_length=100, verbose_name="Nom")
    specialty = models.CharField(max_length=255, blank=True, verbose_name="Spécialité")
    trainer_type = models.CharField(
        max_length=10,
        choices=TRAINER_TYPE_CHOICES,
        default=TRAINER_TYPE_EXTERNAL,
        verbose_name="Type",
        db_index=True,
    )
    # ---- Rates ------------------------------------------------------- #
    daily_rate = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name="Tarif journalier (DA)"
    )
    monthly_rate = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Tarif mensuel (DA)",
        help_text="Utilisé pour les formateurs internes ou les contrats au forfait mensuel.",
    )
    # ---- Fiscal (external contractors) ------------------------------ #
    nif = models.CharField(max_length=100, blank=True, verbose_name="NIF")
    rib = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="RIB",
        help_text="Relevé d'Identité Bancaire — pour virement.",
    )
    phone = models.CharField(max_length=50, blank=True, verbose_name="Téléphone")
    email = models.EmailField(blank=True, verbose_name="Email")
    certifications = models.TextField(
        blank=True, verbose_name="Certifications et habilitations"
    )
    cv = models.FileField(upload_to="trainers/cvs/", blank=True, verbose_name="CV")
    notes = models.TextField(blank=True, verbose_name="Notes")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Formateur"
        verbose_name_plural = "Formateurs"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        type_label = (
            " (Int.)" if self.trainer_type == self.TRAINER_TYPE_INTERNAL else ""
        )
        return f"{self.full_name}{type_label}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_internal(self):
        return self.trainer_type == self.TRAINER_TYPE_INTERNAL

    @property
    def is_external(self):
        return self.trainer_type == self.TRAINER_TYPE_EXTERNAL

    @property
    def session_count(self):
        return self.sessions.count()

    @property
    def total_earnings(self):
        """Estimated earnings based on daily rate × session days."""
        sessions = self.sessions.all()
        total_days = sum((s.date_end - s.date_start).days + 1 for s in sessions)
        return total_days * self.daily_rate

    @property
    def upcoming_sessions(self):
        return self.sessions.filter(date_start__gte=timezone.now().date()).order_by(
            "date_start"
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # Guard: the reverse signal (Beneficiary → Trainer) sets this flag
        # before calling save() to prevent an infinite sync loop.
        if getattr(self, "_skip_beneficiary_sync", False):
            return

        # Keep linked Beneficiary in sync (lazy import to avoid circular).
        try:
            from financial.models import Beneficiary, BeneficiaryType

            btype, _ = BeneficiaryType.objects.get_or_create(
                slug="formateur",
                defaults={"name": "Formateur", "is_seeded": True, "color": "#3B82F6"},
            )

            sync_fields = {
                "name": self.full_name,
                "beneficiary_type": btype,
                "is_trainer": True,
                "is_employee": self.trainer_type == self.TRAINER_TYPE_INTERNAL,
                "nif": self.nif,
                "rib": self.rib,
                "phone": self.phone,
                "email": self.email,
                "daily_rate": self.daily_rate,
                "monthly_rate": self.monthly_rate,
                "is_active": self.is_active,
            }

            # Try to find an unlinked Beneficiary with the same name (e.g. created
            # by seed_initial_expenses before this Trainer existed) and adopt it
            # rather than creating a duplicate.
            existing = Beneficiary.objects.filter(
                beneficiary_type=btype,
                name=self.full_name,
                trainer__isnull=True,
            ).first()
            if existing:
                for field, value in sync_fields.items():
                    setattr(existing, field, value)
                existing.trainer = self
                # Flag to prevent the Beneficiary post_save signal from
                # creating yet another Trainer for this record.
                existing._skip_trainer_sync = True
                existing.save()
            else:
                Beneficiary.objects.update_or_create(
                    trainer=self,
                    defaults=sync_fields,
                )
        except Exception:
            pass  # financial app may not be migrated yet


class TrainingRoom(TimeStampedModel):
    name = models.CharField(max_length=255, verbose_name="Nom")
    capacity = models.PositiveIntegerField(default=20, verbose_name="Capacité")
    location = models.CharField(max_length=255, blank=True, verbose_name="Emplacement")
    description = models.TextField(blank=True, verbose_name="Description")
    has_projector = models.BooleanField(default=False, verbose_name="Projecteur")
    has_whiteboard = models.BooleanField(default=False, verbose_name="Tableau blanc")
    has_ac = models.BooleanField(default=False, verbose_name="Climatisation")
    is_active = models.BooleanField(default=True, verbose_name="Active")

    class Meta:
        verbose_name = "Salle de formation"
        verbose_name_plural = "Salles de formation"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def session_count(self):
        return self.sessions.count()

    def is_available(self, date_start, date_end, exclude_session=None):
        qs = self.sessions.filter(
            status__in=["planned", "in_progress"],
            date_start__lte=date_end,
            date_end__gte=date_start,
        )
        if exclude_session:
            qs = qs.exclude(pk=exclude_session.pk)
        return not qs.exists()


class Session(TimeStampedModel):
    STATUS_PLANNED = "planned"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PLANNED, "Planifiée"),
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_COMPLETED, "Terminée"),
        (STATUS_CANCELLED, "Annulée"),
    ]

    formation = models.ForeignKey(
        Formation,
        on_delete=models.CASCADE,
        related_name="sessions",
        verbose_name="Formation",
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name="Client",
    )
    date_start = models.DateField(verbose_name="Date de début")
    date_end = models.DateField(verbose_name="Date de fin")

    trainer = models.ForeignKey(
        "Trainer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name="Formateur",
    )
    room = models.ForeignKey(
        "TrainingRoom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions",
        verbose_name="Salle",
    )
    external_location = models.CharField(
        max_length=255, blank=True, verbose_name="Lieu externe (si hors-site)"
    )
    capacity = models.PositiveIntegerField(default=20, verbose_name="Capacité")

    # ── NEW: duration of this specific session in hours ────────────────
    session_hours = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Durée de la session (heures)",
        help_text=(
            "Nombre d'heures de cette session. "
            "Utilisé pour le calcul proportionnel du prix : "
            "prix_formation / durée_totale_h × durée_session_h."
        ),
    )
    # ──────────────────────────────────────────────────────────────────

    price_per_participant = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Prix par participant (DA)",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PLANNED,
        verbose_name="Statut",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")
    cancellation_reason = models.TextField(
        blank=True, verbose_name="Motif d'annulation"
    )

    class Meta:
        verbose_name = "Session"
        verbose_name_plural = "Sessions"
        ordering = ["-date_start"]

    def __str__(self):
        return f"{self.formation.title} — {self.date_start}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.date_end and self.date_start and self.date_end < self.date_start:
            raise ValidationError(
                "La date de fin doit être postérieure à la date de début."
            )

    # ── Computed properties ────────────────────────────────────────────

    @property
    def effective_price(self):
        """
        Price to use per participant.
        If price_per_participant is set explicitly, use it.
        Otherwise compute proportionally from formation base_price and session_hours.
        Falls back to formation base_price if no hours data is available.
        """
        if self.price_per_participant:
            return self.price_per_participant
        f = self.formation
        if self.session_hours and f.duration_hours:
            from decimal import Decimal, ROUND_HALF_UP

            return (
                f.base_price
                * Decimal(str(self.session_hours))
                / Decimal(str(f.duration_hours))
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f.base_price

    @property
    def participant_count(self):
        return self.participants.count()

    @property
    def attended_count(self):
        return self.participants.filter(attended=True).count()

    @property
    def available_spots(self):
        return self.capacity - self.participant_count

    @property
    def is_full(self):
        return self.participant_count >= self.capacity

    @property
    def fill_rate(self):
        if self.capacity == 0:
            return 0
        return round((self.participant_count / self.capacity) * 100, 1)

    @property
    def attendance_rate(self):
        if self.participant_count == 0:
            return 0
        return round((self.attended_count / self.participant_count) * 100, 1)

    @property
    def can_be_invoiced(self):
        return self.status == self.STATUS_COMPLETED

    @property
    def total_revenue(self):
        """Gross revenue = effective price × attended participants."""
        return self.effective_price * self.attended_count

    @property
    def duration_days(self):
        return (self.date_end - self.date_start).days + 1

    @property
    def is_overdue(self):
        return (
            self.status == self.STATUS_PLANNED
            and self.date_start < timezone.now().date()
        )


class Participant(TimeStampedModel):
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="participants",
        verbose_name="Session",
    )
    first_name = models.CharField(max_length=100, verbose_name="Prénom")
    last_name = models.CharField(max_length=100, verbose_name="Nom")
    employer = models.CharField(max_length=255, blank=True, verbose_name="Employeur")
    employer_client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="participants",
        verbose_name="Employeur (client enregistré)",
    )
    phone = models.CharField(max_length=50, blank=True, verbose_name="Téléphone")
    email = models.EmailField(blank=True, verbose_name="Email")
    job_title = models.CharField(max_length=255, blank=True, verbose_name="Fonction")
    attended = models.BooleanField(default=True, verbose_name="Présent")
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Participant"
        verbose_name_plural = "Participants"
        ordering = ["last_name", "first_name"]
        unique_together = ["session", "first_name", "last_name", "email"]

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def has_attestation(self):
        return hasattr(self, "attestation")

    @property
    def eligible_for_attestation(self):
        return self.attended and self.session.status == Session.STATUS_COMPLETED


class Attestation(TimeStampedModel):
    participant = models.OneToOneField(
        Participant,
        on_delete=models.CASCADE,
        related_name="attestation",
        verbose_name="Participant",
    )
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="attestations",
        verbose_name="Session",
    )
    reference = models.CharField(max_length=50, unique=True, verbose_name="Référence")
    issue_date = models.DateField(verbose_name="Date d'émission")
    valid_until = models.DateField(verbose_name="Valide jusqu'au")
    is_issued = models.BooleanField(default=True, verbose_name="Émise")

    class Meta:
        verbose_name = "Attestation"
        verbose_name_plural = "Attestations"
        ordering = ["-issue_date"]

    def __str__(self):
        return f"Attestation {self.reference} — {self.participant}"

    @property
    def is_valid(self):
        return self.valid_until >= timezone.now().date()

    @property
    def is_expired(self):
        return not self.is_valid

    @property
    def days_until_expiry(self):
        return max((self.valid_until - timezone.now().date()).days, 0)

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self._generate_reference()
        if not self.valid_until:
            from core.models import FormationInfo

            years = FormationInfo.get_instance().attestation_validity_years or 5
            self.valid_until = self.issue_date + timedelta(days=365 * years)
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_reference():
        from django.utils import timezone as tz

        year = tz.now().year
        with transaction.atomic():
            count = (
                Attestation.objects.select_for_update()
                .filter(issue_date__year=year)
                .count()
            ) + 1
        return f"ATT-{year}-{count:04d}"
