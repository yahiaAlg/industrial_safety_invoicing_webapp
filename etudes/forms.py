# etudes/forms.py

from django import forms
from django.core.exceptions import ValidationError

from etudes.models import ProjectDeliverable, ProjectPhase, StudyProject


class StudyProjectForm(forms.ModelForm):
    class Meta:
        model = StudyProject
        fields = [
            "client",
            "title",
            "reference",
            "description",
            "project_type",
            "site_address",
            "start_date",
            "end_date",
            "budget",
            "status",
            "priority",
            "notes",
        ]
        labels = {
            "client": "Client",
            "title": "Titre du projet",
            "reference": "Référence interne",
            "description": "Description",
            "project_type": "Type de mission",
            "site_address": "Adresse du site",
            "start_date": "Date de début",
            "end_date": "Date de fin prévue",
            "budget": "Budget contractuel (DA)",
            "status": "Statut",
            "priority": "Priorité",
            "notes": "Notes",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "site_address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, is_receptionist=False, **kwargs):
        super().__init__(*args, **kwargs)
        # Receptionists can only set basic intake fields
        if is_receptionist:
            allowed = [
                "client",
                "title",
                "description",
                "project_type",
                "site_address",
                "start_date",
            ]
            for field in list(self.fields.keys()):
                if field not in allowed:
                    self.fields.pop(field)

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        if start and end and end < start:
            self.add_error(
                "end_date", "La date de fin doit être postérieure à la date de début."
            )
        return cleaned_data


class StudyProjectFilterForm(forms.Form):
    q = forms.CharField(
        label="Recherche",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Titre, client, type…"}),
    )
    status = forms.ChoiceField(
        label="Statut",
        required=False,
        choices=[("", "Tous")] + StudyProject.STATUS_CHOICES,
    )
    priority = forms.ChoiceField(
        label="Priorité",
        required=False,
        choices=[("", "Toutes")] + StudyProject.PRIORITY_CHOICES,
    )
    overdue_only = forms.BooleanField(label="En retard uniquement", required=False)


class ProjectCloseForm(forms.Form):
    """Confirm project closure; requires all phases to be completed."""

    actual_end_date = forms.DateField(
        label="Date de clôture réelle",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    notes = forms.CharField(
        label="Notes de clôture",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class ProjectCancelForm(forms.Form):
    reason = forms.CharField(
        label="Motif d'annulation",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class ProjectPhaseForm(forms.ModelForm):
    class Meta:
        model = ProjectPhase
        fields = [
            "name",
            "description",
            "order",
            "status",
            "start_date",
            "due_date",
            "estimated_hours",
            "deliverable",
            "notes",
        ]
        labels = {
            "name": "Nom de la phase",
            "description": "Description",
            "order": "Ordre",
            "status": "Statut",
            "start_date": "Date de début",
            "due_date": "Date d'échéance",
            "estimated_hours": "Heures estimées",
            "deliverable": "Livrable attendu",
            "notes": "Notes",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        due = cleaned_data.get("due_date")
        if start and due and due < start:
            self.add_error(
                "due_date",
                "La date d'échéance doit être postérieure à la date de début.",
            )
        return cleaned_data


class PhaseStatusForm(forms.Form):
    STATUS_TRANSITIONS = {
        ProjectPhase.STATUS_PENDING: [
            ProjectPhase.STATUS_IN_PROGRESS,
            ProjectPhase.STATUS_BLOCKED,
        ],
        ProjectPhase.STATUS_IN_PROGRESS: [
            ProjectPhase.STATUS_COMPLETED,
            ProjectPhase.STATUS_BLOCKED,
        ],
        ProjectPhase.STATUS_BLOCKED: [
            ProjectPhase.STATUS_IN_PROGRESS,
        ],
    }

    status = forms.ChoiceField(
        choices=ProjectPhase.STATUS_CHOICES, label="Nouveau statut"
    )
    completion_date = forms.DateField(
        label="Date d'achèvement",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    actual_hours = forms.DecimalField(
        label="Heures réelles",
        required=False,
        min_value=0,
        max_digits=6,
        decimal_places=1,
    )

    def __init__(self, *args, current_status=None, **kwargs):
        self.current_status = current_status
        super().__init__(*args, **kwargs)
        allowed = self.STATUS_TRANSITIONS.get(current_status, [])
        self.fields["status"].choices = [
            (v, l) for v, l in ProjectPhase.STATUS_CHOICES if v in allowed
        ]

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("status") == ProjectPhase.STATUS_COMPLETED:
            if not cleaned_data.get("completion_date"):
                self.add_error("completion_date", "La date d'achèvement est requise.")
        return cleaned_data


class PhaseReorderForm(forms.Form):
    """Accepts a JSON-style ordered list of phase PKs."""

    ordered_ids = forms.CharField(
        widget=forms.HiddenInput,
        help_text="Comma-separated phase PKs in new order.",
    )

    def clean_ordered_ids(self):
        raw = self.cleaned_data.get("ordered_ids", "")
        try:
            ids = [int(i.strip()) for i in raw.split(",") if i.strip()]
        except ValueError:
            raise ValidationError("Format invalide.")
        if not ids:
            raise ValidationError("La liste des phases est vide.")
        return ids


class ProjectDeliverableForm(forms.ModelForm):
    class Meta:
        model = ProjectDeliverable
        fields = [
            "title",
            "description",
            "document",
            "version",
            "submitted_to",
            "submission_date",
            "notes",
        ]
        labels = {
            "title": "Titre",
            "description": "Description",
            "document": "Fichier",
            "version": "Version",
            "submitted_to": "Remis à",
            "submission_date": "Date de remise",
            "notes": "Notes",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "submission_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean_version(self):
        version = self.cleaned_data.get("version", "1.0").strip()
        if not version:
            return "1.0"
        return version


class DeliverableApproveForm(forms.Form):
    client_approved = forms.ChoiceField(
        label="Décision client",
        choices=[
            ("true", "Approuvé"),
            ("false", "Refusé"),
        ],
    )
    notes = forms.CharField(
        label="Notes",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )
