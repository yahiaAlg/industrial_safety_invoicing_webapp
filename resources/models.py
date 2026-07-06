"""
Resources models — Trainers, rooms, equipment, maintenance logs.
"""

from django.db import models
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from formations.models import Session  # now safe, no cycle
from core.base_models import TimeStampedModel


class Equipment(TimeStampedModel):
    """
    A physical asset owned by the institute (measuring devices,
    safety testing tools, PPE kits, projectors, etc.).
    """

    CONDITION_GOOD = "good"
    CONDITION_NEEDS_REVIEW = "needs_review"
    CONDITION_OUT_OF_SERVICE = "out_of_service"

    CONDITION_CHOICES = [
        (CONDITION_GOOD, "Bon état"),
        (CONDITION_NEEDS_REVIEW, "À réviser"),
        (CONDITION_OUT_OF_SERVICE, "Hors service"),
    ]

    STATUS_ACTIVE = "active"
    STATUS_MAINTENANCE = "maintenance"
    STATUS_RESERVED = "reserved"
    STATUS_FOR_SALE = "for_sale"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Actif"),
        (STATUS_MAINTENANCE, "En maintenance"),
        (STATUS_RESERVED, "Mis en réserve"),
        (STATUS_FOR_SALE, "À vendre / Réformer"),
    ]

    name = models.CharField(max_length=255, verbose_name="Nom")
    category = models.CharField(max_length=255, verbose_name="Catégorie")
    # Unique identifier stamped on the physical asset
    serial_number = models.CharField(
        max_length=100, blank=True, verbose_name="Numéro de série"
    )
    model_number = models.CharField(
        max_length=100, blank=True, verbose_name="Référence modèle"
    )
    supplier = models.CharField(max_length=255, blank=True, verbose_name="Fournisseur")
    # Manufacturer warranty expiry
    warranty_expiry = models.DateField(
        null=True, blank=True, verbose_name="Fin de garantie"
    )

    # ---- Purchase & valuation --------------------------------------- #
    purchase_date = models.DateField(verbose_name="Date d'achat")
    purchase_cost = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Coût d'achat (DA)"
    )
    current_value = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Valeur actuelle estimée (DA)"
    )
    # Expected useful life for depreciation calculation
    useful_life_years = models.PositiveIntegerField(
        default=5, verbose_name="Durée de vie utile (années)"
    )

    # ---- Status & location ------------------------------------------ #
    condition = models.CharField(
        max_length=20,
        choices=CONDITION_CHOICES,
        default=CONDITION_GOOD,
        verbose_name="État",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_ACTIVE,
        verbose_name="Statut",
    )
    location = models.CharField(max_length=255, blank=True, verbose_name="Emplacement")

    # ---- Maintenance schedule --------------------------------------- #
    maintenance_interval_days = models.PositiveIntegerField(
        default=180, verbose_name="Intervalle de maintenance (jours)"
    )

    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Équipement"
        verbose_name_plural = "Équipements"
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.name} ({self.category})"

    # ------------------------------------------------------------------ #
    # Usage statistics
    # ------------------------------------------------------------------ #

    @property
    def usage_count(self):
        return self.usages.count()

    @property
    def total_usage_hours(self):
        result = self.usages.aggregate(total=Sum("duration_hours"))
        return result["total"] or 0

    @property
    def last_used_date(self):
        last = self.usages.order_by("-date").first()
        return last.date if last else None

    @property
    def days_since_last_use(self):
        last_date = self.last_used_date
        if last_date:
            return (timezone.now().date() - last_date).days
        return None

    @property
    def is_idle(self):
        """Hasn't been used for more than the configured idle threshold."""
        from django.conf import settings

        threshold = getattr(settings, "EQUIPMENT_IDLE_THRESHOLD_DAYS", 90)
        days = self.days_since_last_use
        return days is not None and days > threshold

    # ------------------------------------------------------------------ #
    # Financial analysis
    # ------------------------------------------------------------------ #

    @property
    def total_maintenance_cost(self):
        result = self.maintenance_logs.aggregate(total=Sum("cost"))
        return result["total"] or 0

    @property
    def total_cost_of_ownership(self):
        return self.purchase_cost + self.total_maintenance_cost

    @property
    def cost_per_use(self):
        """Total cost of ownership divided by number of uses."""
        if self.usage_count == 0:
            return self.total_cost_of_ownership
        return round(self.total_cost_of_ownership / self.usage_count, 2)

    @property
    def depreciation_rate(self):
        """Annual straight-line depreciation amount."""
        if not self.useful_life_years:
            return 0
        return round(self.purchase_cost / self.useful_life_years, 2)

    @property
    def age_years(self):
        from datetime import date

        return (date.today() - self.purchase_date).days / 365

    # ------------------------------------------------------------------ #
    # Maintenance schedule
    # ------------------------------------------------------------------ #

    @property
    def next_maintenance_due(self):
        last = self.maintenance_logs.order_by("-date").first()
        base = last.date if last else self.purchase_date
        return base + timedelta(days=self.maintenance_interval_days)

    @property
    def is_maintenance_due(self):
        return self.next_maintenance_due <= timezone.now().date()

    @property
    def is_under_warranty(self):
        if not self.warranty_expiry:
            return False
        return self.warranty_expiry >= timezone.now().date()


class EquipmentUsage(TimeStampedModel):
    """
    A single usage event — records when equipment is assigned to a session or project.
    """

    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="usages",
        verbose_name="Équipement",
    )
    assigned_to_session = models.ForeignKey(
        "formations.Session",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="equipment_usages",
        verbose_name="Session",
    )
    assigned_to_project = models.ForeignKey(
        "etudes.StudyProject",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="equipment_usages",
        verbose_name="Projet",
    )
    date = models.DateField(verbose_name="Date")
    duration_hours = models.DecimalField(
        max_digits=6, decimal_places=2, default=1, verbose_name="Durée (heures)"
    )
    context = models.TextField(blank=True, verbose_name="Contexte / détails")

    class Meta:
        verbose_name = "Utilisation d'équipement"
        verbose_name_plural = "Utilisations d'équipements"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.equipment.name} — {self.date}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if not self.assigned_to_session and not self.assigned_to_project:
            raise ValidationError(
                "Associez l'utilisation à une session ou à un projet."
            )
        if self.assigned_to_session and self.assigned_to_project:
            raise ValidationError(
                "Choisissez soit une session, soit un projet — pas les deux."
            )


class EquipmentBooking(TimeStampedModel):
    """
    Advance reservation of equipment for an upcoming session or project.
    Prevents double-booking and gives the owner visibility on commitments.

    Note: EquipmentUsage is the retrospective log; EquipmentBooking is
    the prospective reservation.  When a session ends, the corresponding
    booking should be converted to a usage record.
    """

    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="bookings",
        verbose_name="Équipement",
    )
    reserved_for_session = models.ForeignKey(
        "formations.Session",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="equipment_bookings",
        verbose_name="Session",
    )
    reserved_for_project = models.ForeignKey(
        "etudes.StudyProject",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="equipment_bookings",
        verbose_name="Projet",
    )
    date_from = models.DateField(verbose_name="Du")
    date_to = models.DateField(verbose_name="Au")
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Réservation d'équipement"
        verbose_name_plural = "Réservations d'équipements"
        ordering = ["date_from"]

    def __str__(self):
        return f"{self.equipment.name} réservé du {self.date_from} au {self.date_to}"

    def clean(self):
        from django.core.exceptions import ValidationError

        # Validate exclusive assignment
        if not self.reserved_for_session and not self.reserved_for_project:
            raise ValidationError(
                "Associez la réservation à une session ou à un projet."
            )
        if self.reserved_for_session and self.reserved_for_project:
            raise ValidationError(
                "Choisissez soit une session, soit un projet — pas les deux."
            )
        # Detect date conflicts for the same equipment
        if self.date_from and self.date_to:
            conflicts = EquipmentBooking.objects.filter(
                equipment=self.equipment,
                date_from__lte=self.date_to,
                date_to__gte=self.date_from,
            ).exclude(pk=self.pk)
            if conflicts.exists():
                raise ValidationError(
                    f"L'équipement « {self.equipment.name} » est déjà réservé "
                    f"sur cette période."
                )


class MaintenanceLog(TimeStampedModel):
    """
    Record of a maintenance event performed on equipment.
    """

    TYPE_PREVENTIVE = "preventive"
    TYPE_CORRECTIVE = "corrective"

    TYPE_CHOICES = [
        (TYPE_PREVENTIVE, "Préventif"),
        (TYPE_CORRECTIVE, "Correctif"),
    ]

    equipment = models.ForeignKey(
        Equipment,
        on_delete=models.CASCADE,
        related_name="maintenance_logs",
        verbose_name="Équipement",
    )
    date = models.DateField(verbose_name="Date")
    maintenance_type = models.CharField(
        max_length=20, choices=TYPE_CHOICES, verbose_name="Type"
    )
    cost = models.DecimalField(
        max_digits=12, decimal_places=2, default=0, verbose_name="Coût (DA)"
    )
    performed_by = models.CharField(
        max_length=255, blank=True, verbose_name="Effectué par"
    )
    description = models.TextField(verbose_name="Description des travaux")
    # Resolution of any problem found
    resolution = models.TextField(blank=True, verbose_name="Résolution / résultat")
    next_due_date = models.DateField(
        null=True, blank=True, verbose_name="Prochaine échéance"
    )

    class Meta:
        verbose_name = "Maintenance"
        verbose_name_plural = "Maintenances"
        ordering = ["-date"]

    def __str__(self):
        return f"{self.equipment.name} — {self.date} ({self.get_maintenance_type_display()})"
