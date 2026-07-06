# formations/forms.py

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify
from formations.models import TrainingRoom

from formations.models import Trainer

from formations.models import (
    Attestation,
    Formation,
    FormationCategory,
    Participant,
    Session,
)


class FormationCategoryForm(forms.ModelForm):
    class Meta:
        model = FormationCategory
        fields = ["name", "description", "color"]
        labels = {
            "name": "Catégorie",
            "description": "Description",
            "color": "Couleur",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "color": forms.TextInput(attrs={"type": "color"}),
        }

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        qs = FormationCategory.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Cette catégorie existe déjà.")
        return name


class FormationForm(forms.ModelForm):
    class Meta:
        model = Formation
        fields = [
            "category",
            "title",
            "description",
            "objectives",
            "target_audience",
            "prerequisites",
            "duration_days",
            "duration_hours",
            "base_price",
            "max_participants",
            "min_participants",
            "accreditation_body",
            "accreditation_reference",
            "is_active",
        ]
        labels = {
            "category": "Catégorie",
            "title": "Titre",
            "description": "Description",
            "objectives": "Objectifs pédagogiques",
            "target_audience": "Public cible",
            "prerequisites": "Prérequis",
            "duration_days": "Durée (jours)",
            "duration_hours": "Durée (heures)",
            "base_price": "Prix de base (DA)",
            "max_participants": "Capacité maximale",
            "min_participants": "Minimum de participants",
            "accreditation_body": "Organisme d'accréditation",
            "accreditation_reference": "Référence d'accréditation",
            "is_active": "Active",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "objectives": forms.Textarea(attrs={"rows": 3}),
            "target_audience": forms.Textarea(attrs={"rows": 2}),
            "prerequisites": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_title(self):
        title = self.cleaned_data.get("title", "").strip()
        if not title:
            raise ValidationError("Le titre est obligatoire.")
        slug = slugify(title)
        qs = Formation.objects.filter(slug=slug)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Une formation avec un titre similaire existe déjà.")
        return title

    def clean(self):
        cleaned_data = super().clean()
        min_p = cleaned_data.get("min_participants")
        max_p = cleaned_data.get("max_participants")
        if min_p and max_p and min_p > max_p:
            self.add_error(
                "min_participants",
                "Le minimum ne peut pas dépasser la capacité maximale.",
            )
        d_days = cleaned_data.get("duration_days", 0)
        d_hours = cleaned_data.get("duration_hours", 0)
        if d_hours and d_days and d_hours > d_days * 24:
            self.add_error(
                "duration_hours",
                "Les heures déclarées dépassent la durée en jours × 24.",
            )
        return cleaned_data


class SessionForm(forms.ModelForm):
    class Meta:
        model = Session
        fields = [
            "formation",
            "client",
            "date_start",
            "date_end",
            "trainer",
            "room",
            "external_location",
            "capacity",
            "session_hours",
            "price_per_participant",
            "notes",
        ]
        labels = {
            "formation": "Formation",
            "client": "Client",
            "date_start": "Date de début",
            "date_end": "Date de fin",
            "trainer": "Formateur",
            "room": "Salle",
            "external_location": "Lieu externe",
            "capacity": "Capacité",
            "session_hours": "Durée de la session (heures)",
            "price_per_participant": "Prix / participant (DA)",
            "notes": "Notes",
        }
        widgets = {
            "date_start": forms.DateInput(attrs={"type": "date"}),
            "date_end": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active formations in dropdown
        self.fields["formation"].queryset = Formation.objects.filter(is_active=True)
        # Rooms from resources

        self.fields["room"].queryset = TrainingRoom.objects.filter(is_active=True)

        self.fields["trainer"].queryset = Trainer.objects.filter(is_active=True)
        self.fields["client"].required = False
        self.fields["room"].required = False
        self.fields["trainer"].required = False
        self.fields["price_per_participant"].required = False

    def clean(self):
        cleaned_data = super().clean()
        date_start = cleaned_data.get("date_start")
        date_end = cleaned_data.get("date_end")
        if date_start and date_end and date_end < date_start:
            self.add_error(
                "date_end",
                "La date de fin doit être postérieure ou égale à la date de début.",
            )

        # Room double-booking check
        room = cleaned_data.get("room")
        if room and date_start and date_end:
            exclude_pk = self.instance.pk if self.instance.pk else None
            if not room.is_available(
                date_start,
                date_end,
                exclude_session=self.instance if self.instance.pk else None,
            ):
                self.add_error(
                    "room",
                    f"La salle « {room.name} » est déjà réservée sur cette période.",
                )

        # Trainer double-booking check
        trainer = cleaned_data.get("trainer")
        if trainer and date_start and date_end:
            qs = Session.objects.filter(
                trainer=trainer,
                status__in=[Session.STATUS_PLANNED, Session.STATUS_IN_PROGRESS],
                date_start__lte=date_end,
                date_end__gte=date_start,
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                self.add_error(
                    "trainer",
                    f"Le formateur est déjà affecté à une session sur cette période.",
                )

        # Capacity vs formation min/max
        formation = cleaned_data.get("formation")
        capacity = cleaned_data.get("capacity")
        if formation and capacity:
            if capacity < formation.min_participants:
                self.add_error(
                    "capacity",
                    f"La capacité est inférieure au minimum requis ({formation.min_participants}).",
                )
            if capacity > formation.max_participants:
                self.add_error(
                    "capacity",
                    f"La capacité dépasse le maximum défini ({formation.max_participants}).",
                )
        return cleaned_data


class SessionStatusForm(forms.Form):
    """Standalone form for status transitions."""

    STATUS_TRANSITIONS = {
        Session.STATUS_PLANNED: [Session.STATUS_IN_PROGRESS, Session.STATUS_CANCELLED],
        Session.STATUS_IN_PROGRESS: [
            Session.STATUS_COMPLETED,
            Session.STATUS_CANCELLED,
        ],
    }

    status = forms.ChoiceField(choices=Session.STATUS_CHOICES, label="Nouveau statut")
    cancellation_reason = forms.CharField(
        label="Motif d'annulation",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, current_status=None, **kwargs):
        self.current_status = current_status
        super().__init__(*args, **kwargs)
        allowed = self.STATUS_TRANSITIONS.get(current_status, [])
        self.fields["status"].choices = [
            (v, l) for v, l in Session.STATUS_CHOICES if v in allowed
        ]

    def clean(self):
        cleaned_data = super().clean()
        new_status = cleaned_data.get("status")
        if new_status == Session.STATUS_CANCELLED and not cleaned_data.get(
            "cancellation_reason"
        ):
            self.add_error("cancellation_reason", "Le motif d'annulation est requis.")
        return cleaned_data


class SessionCancelForm(forms.Form):
    cancellation_reason = forms.CharField(
        label="Motif d'annulation",
        widget=forms.Textarea(attrs={"rows": 3}),
    )


class SessionFilterForm(forms.Form):
    q = forms.CharField(
        label="Recherche",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Formation, client, formateur…"}),
    )
    status = forms.ChoiceField(
        label="Statut",
        required=False,
        choices=[("", "Tous")] + Session.STATUS_CHOICES,
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
    formation = forms.ModelChoiceField(
        label="Formation",
        required=False,
        queryset=Formation.objects.filter(is_active=True),
        empty_label="Toutes",
    )


class ParticipantForm(forms.ModelForm):
    class Meta:
        model = Participant
        fields = [
            "first_name",
            "last_name",
            "employer",
            "employer_client",
            "phone",
            "email",
            "job_title",
            "attended",
            "notes",
        ]
        labels = {
            "first_name": "Prénom",
            "last_name": "Nom",
            "employer": "Employeur",
            "employer_client": "Employeur (client enregistré)",
            "phone": "Téléphone",
            "email": "Email",
            "job_title": "Fonction",
            "attended": "Présent",
            "notes": "Notes",
        }
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, session=None, **kwargs):
        self.session = session
        super().__init__(*args, **kwargs)
        self.fields["employer_client"].required = False
        self.fields["employer"].required = False

    def clean(self):
        cleaned_data = super().clean()
        if self.session and self.session.is_full and not self.instance.pk:
            raise ValidationError(
                f"La session est complète ({self.session.capacity} participants maximum)."
            )
        # Unique together check (session, first_name, last_name, email)
        first = cleaned_data.get("first_name", "")
        last = cleaned_data.get("last_name", "")
        email = cleaned_data.get("email", "")
        if self.session:
            qs = Participant.objects.filter(
                session=self.session,
                first_name__iexact=first,
                last_name__iexact=last,
            )
            if email:
                qs = Participant.objects.filter(
                    session=self.session, email__iexact=email
                )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    "Ce participant est déjà inscrit à cette session."
                )
        return cleaned_data


class ParticipantImportForm(forms.Form):
    """CSV/Excel import of participants for bulk enrollment."""

    file = forms.FileField(
        label="Fichier (CSV ou Excel)",
        help_text="Colonnes attendues : Prénom, Nom, Employeur, Email, Téléphone.",
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        name = f.name.lower()
        if not (
            name.endswith(".csv") or name.endswith(".xlsx") or name.endswith(".xls")
        ):
            raise ValidationError(
                "Seuls les fichiers CSV et Excel (.xlsx, .xls) sont acceptés."
            )
        if f.size > 5 * 1024 * 1024:
            raise ValidationError("Le fichier ne doit pas dépasser 5 Mo.")
        return f


class AttestationIssueForm(forms.Form):
    """Controls bulk issuance of attestations for a completed session."""

    issue_date = forms.DateField(
        label="Date d'émission",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    participant_ids = forms.ModelMultipleChoiceField(
        queryset=Participant.objects.none(),
        label="Participants éligibles",
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, session=None, **kwargs):
        super().__init__(*args, **kwargs)
        if session:
            eligible = session.participants.filter(attended=True).exclude(
                attestation__isnull=False
            )
            self.fields["participant_ids"].queryset = eligible

    def clean_participant_ids(self):
        participants = self.cleaned_data.get("participant_ids")
        if not participants:
            raise ValidationError("Sélectionnez au moins un participant.")
        return participants
