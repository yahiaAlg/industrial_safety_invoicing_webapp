"""
Etudes models — Study / consulting projects, phases, deliverables.
"""

from django.db import models
from django.db.models import Sum
from django.utils import timezone

from clients.models import Client
from core.base_models import TimeStampedModel


class StudyProject(TimeStampedModel):
    """
    An industrial safety consulting project for a client.
    """

    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_ON_HOLD = "on_hold"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_COMPLETED, "Terminé"),
        (STATUS_ON_HOLD, "En pause"),
        (STATUS_CANCELLED, "Annulé"),
    ]

    PRIORITY_LOW = "low"
    PRIORITY_MEDIUM = "medium"
    PRIORITY_HIGH = "high"
    PRIORITY_URGENT = "urgent"

    PRIORITY_CHOICES = [
        (PRIORITY_LOW, "Basse"),
        (PRIORITY_MEDIUM, "Normale"),
        (PRIORITY_HIGH, "Haute"),
        (PRIORITY_URGENT, "Urgente"),
    ]

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="study_projects",
        verbose_name="Client",
    )
    title = models.CharField(max_length=255, verbose_name="Titre")
    reference = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Référence interne",
        help_text="Référence courte pour usage interne (ex. ETU-2026-001).",
    )
    description = models.TextField(blank=True, verbose_name="Description")

    # ---- Scope ------------------------------------------------------- #
    project_type = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Type de mission",
        help_text="Ex. Audit SST, Diagnostic incendie, Étude de risques ATEX.",
    )
    site_address = models.TextField(
        blank=True, verbose_name="Adresse du site d'intervention"
    )

    # ---- Scheduling -------------------------------------------------- #
    start_date = models.DateField(verbose_name="Date de début")
    end_date = models.DateField(
        null=True, blank=True, verbose_name="Date de fin prévue"
    )
    actual_end_date = models.DateField(
        null=True, blank=True, verbose_name="Date de fin réelle"
    )

    # ---- Financial --------------------------------------------------- #
    budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Budget contractuel (DA)",
    )

    # ---- Status & priority ------------------------------------------- #
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_IN_PROGRESS,
        verbose_name="Statut",
    )
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_MEDIUM,
        verbose_name="Priorité",
    )

    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Projet d'étude"
        verbose_name_plural = "Projets d'étude"
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.title} — {self.client.name}"

    # ------------------------------------------------------------------ #
    # Phase progress
    # ------------------------------------------------------------------ #

    @property
    def phase_count(self):
        return self.phases.count()

    @property
    def completed_phase_count(self):
        return self.phases.filter(status=ProjectPhase.STATUS_COMPLETED).count()

    @property
    def progress_percentage(self):
        if self.phase_count == 0:
            return 0
        return round((self.completed_phase_count / self.phase_count) * 100, 1)

    # ------------------------------------------------------------------ #
    # Financial — single DB query via aggregate
    # ------------------------------------------------------------------ #

    @property
    def total_expenses(self):
        from financial.models import Expense

        result = Expense.objects.filter(allocated_to_project=self).aggregate(
            total=Sum("amount")
        )
        return result["total"] or 0

    @property
    def margin(self):
        return self.budget - self.total_expenses

    @property
    def margin_rate(self):
        """Margin as a percentage of budget."""
        if not self.budget:
            return 0
        return round((self.margin / self.budget) * 100, 1)

    # ------------------------------------------------------------------ #
    # Scheduling helpers
    # ------------------------------------------------------------------ #

    @property
    def is_overdue(self):
        """True if end_date has passed and project is still active."""
        return (
            self.end_date
            and self.end_date < timezone.now().date()
            and self.status == self.STATUS_IN_PROGRESS
        )

    @property
    def days_overdue(self):
        if not self.is_overdue:
            return 0
        return (timezone.now().date() - self.end_date).days

    def can_be_closed(self):
        """Project can be closed only when all phases are completed."""
        if self.phase_count == 0:
            return True
        return not self.phases.filter(status=ProjectPhase.STATUS_IN_PROGRESS).exists()


class ProjectPhase(TimeStampedModel):
    """
    A discrete phase within a study project.
    Example phases: Diagnostic initial, Enquête terrain, Analyse, Rapport final.
    """

    STATUS_PENDING = "pending"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_COMPLETED = "completed"
    STATUS_BLOCKED = "blocked"

    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_IN_PROGRESS, "En cours"),
        (STATUS_COMPLETED, "Terminée"),
        (STATUS_BLOCKED, "Bloquée"),
    ]

    project = models.ForeignKey(
        StudyProject,
        on_delete=models.CASCADE,
        related_name="phases",
        verbose_name="Projet",
    )
    name = models.CharField(max_length=255, verbose_name="Nom")
    description = models.TextField(blank=True, verbose_name="Description")
    order = models.PositiveIntegerField(default=1, verbose_name="Ordre")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        verbose_name="Statut",
    )

    # ---- Scheduling -------------------------------------------------- #
    start_date = models.DateField(null=True, blank=True, verbose_name="Date de début")
    due_date = models.DateField(null=True, blank=True, verbose_name="Date d'échéance")
    completion_date = models.DateField(
        null=True, blank=True, verbose_name="Date d'achèvement"
    )

    # ---- Effort ------------------------------------------------------ #
    estimated_hours = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Heures estimées",
    )
    actual_hours = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        verbose_name="Heures réelles",
    )

    # ---- Deliverable summary (for quick reference) ------------------- #
    deliverable = models.CharField(
        max_length=255, blank=True, verbose_name="Livrable attendu"
    )

    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Phase de projet"
        verbose_name_plural = "Phases de projet"
        ordering = ["project", "order"]

    def __str__(self):
        return f"{self.project.title} — {self.name}"

    @property
    def is_overdue(self):
        return (
            self.due_date
            and self.due_date < timezone.now().date()
            and self.status not in [self.STATUS_COMPLETED]
        )

    @property
    def deliverable_count(self):
        return self.deliverables.count()


class ProjectDeliverable(TimeStampedModel):
    """
    A document or output produced during a project phase.
    """

    phase = models.ForeignKey(
        ProjectPhase,
        on_delete=models.CASCADE,
        related_name="deliverables",
        verbose_name="Phase",
    )
    title = models.CharField(max_length=255, verbose_name="Titre")
    description = models.TextField(blank=True, verbose_name="Description")
    document = models.FileField(upload_to="deliverables/%Y/%m/", verbose_name="Fichier")
    version = models.CharField(max_length=20, default="1.0", verbose_name="Version")
    # Track who the document was submitted to and when
    submitted_to = models.CharField(max_length=255, blank=True, verbose_name="Remis à")
    submission_date = models.DateField(
        null=True, blank=True, verbose_name="Date de remise"
    )
    client_approved = models.BooleanField(
        null=True,
        verbose_name="Approuvé par le client",
        help_text="Null = en attente de retour.",
    )
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Livrable"
        verbose_name_plural = "Livrables"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.phase.project.title} — {self.title} v{self.version}"
