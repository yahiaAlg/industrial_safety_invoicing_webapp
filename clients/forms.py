# clients/forms.py  —  v3.2
# Changes: tin field added to ClientForm (optional, all client types).

from django import forms
from django.core.exceptions import ValidationError

from clients.models import Client, ClientContact, FormeJuridique


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            "name",
            "client_type",
            "forme_juridique",
            "activity_sector",
            "address",
            "postal_code",
            "city",
            "phone",
            "email",
            "website",
            "contact_name",
            "contact_phone",
            "contact_email",
            "nin",
            "nif",
            "nis",
            "rc",
            "article_imposition",
            "rib",
            "tin",
            "carte_auto_entrepreneur",
            "label_startup_number",
            "label_startup_date",
            "programme_accompagnement",
            "is_tva_exempt",
            "is_active",
            "notes",
        ]
        labels = {
            "name": "Nom / Raison sociale",
            "client_type": "Type de client",
            "forme_juridique": "Forme juridique",
            "activity_sector": "Secteur d'activité",
            "address": "Adresse",
            "postal_code": "Code postal",
            "city": "Ville",
            "phone": "Téléphone",
            "email": "Email",
            "website": "Site web",
            "contact_name": "Contact principal",
            "contact_phone": "Tél. contact",
            "contact_email": "Email contact",
            "nin": "NIN (Numéro d'Identité Nationale)",
            "nif": "NIF",
            "nis": "NIS",
            "rc": "Numéro RC",
            "article_imposition": "Article d'imposition (ART.I)",
            "rib": "RIB",
            "tin": "TIN (Tax Identification Number)",
            "carte_auto_entrepreneur": "N° Carte Auto-Entrepreneur",
            "label_startup_number": "N° Label Startup",
            "label_startup_date": "Date d'obtention du label",
            "programme_accompagnement": "Programme d'accompagnement",
            "is_tva_exempt": "Exonéré de TVA",
            "is_active": "Actif",
            "notes": "Notes",
        }
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "label_startup_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # ── forme_juridique — FK select, active entries only ─────────── #
        fj_field = self.fields["forme_juridique"]
        fj_field.queryset = FormeJuridique.objects.filter(is_active=True).order_by(
            "name"
        )
        fj_field.required = False
        fj_field.empty_label = "— Sélectionner —"
        fj_field.help_text = (
            "Applicable aux entreprises et startups. "
            "Si non listée, choisir « Autre »."
        )

        # ── Optional / type-specific fields ──────────────────────────── #
        for f in (
            "nin",
            "nif",
            "nis",
            "rc",
            "article_imposition",
            "rib",
            "tin",
            "carte_auto_entrepreneur",
            "label_startup_number",
            "label_startup_date",
            "programme_accompagnement",
            "contact_name",
            "contact_phone",
            "contact_email",
            "website",
            "notes",
        ):
            if f in self.fields:
                self.fields[f].required = False

        # ── TVA exempt — disable for auto-exempt types (edit mode) ───── #
        if self.instance and self.instance.pk:
            if self.instance.client_type in {
                Client.ClientType.PARTICULIER,
                Client.ClientType.AUTO_ENTREPRENEUR,
            }:
                self.fields["is_tva_exempt"].disabled = True
                self.fields["is_tva_exempt"].help_text = (
                    "Automatiquement exonéré pour ce type de client."
                )

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip()
        if not name:
            raise ValidationError("Le nom du client est obligatoire.")
        qs = Client.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Un client portant ce nom existe déjà.")
        return name

    def clean_email(self):
        return self.cleaned_data.get("email", "").strip().lower()

    def clean_nin(self):
        nin = self.cleaned_data.get("nin", "").strip()
        if nin and not nin.isdigit():
            raise ValidationError("Le NIN ne doit contenir que des chiffres.")
        if nin and len(nin) != 18:
            raise ValidationError("Le NIN doit comporter 18 chiffres.")
        return nin

    def clean(self):
        cleaned = super().clean()
        client_type = cleaned.get("client_type")

        # Force TVA exempt for auto-exempt types
        if client_type in (
            Client.ClientType.PARTICULIER,
            Client.ClientType.AUTO_ENTREPRENEUR,
        ):
            cleaned["is_tva_exempt"] = True

        # Soft cross-field warnings (hard check happens at finalization)
        if client_type == Client.ClientType.PARTICULIER:
            for field in ("nif", "nis", "rc", "article_imposition"):
                if cleaned.get(field):
                    self.add_error(
                        field, "Ce champ n'est pas applicable aux particuliers."
                    )

        if client_type == Client.ClientType.AUTO_ENTREPRENEUR:
            for field in ("nis", "rc"):
                if cleaned.get(field):
                    self.add_error(
                        field, "Ce champ n'est pas applicable aux auto-entrepreneurs."
                    )

        # Auto-default forme_juridique to "Autre" for entreprise / startup
        if client_type in (Client.ClientType.ENTREPRISE, Client.ClientType.STARTUP):
            if not cleaned.get("forme_juridique"):
                cleaned["forme_juridique"] = FormeJuridique.get_default()

        return cleaned


# ---------------------------------------------------------------------------
# Supporting forms
# ---------------------------------------------------------------------------


class ClientFilterForm(forms.Form):
    q = forms.CharField(
        label="Recherche",
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Nom, ville, secteur…"}),
    )
    client_type = forms.ChoiceField(
        label="Type",
        required=False,
        choices=[("", "Tous")] + Client.ClientType.choices,
    )
    has_balance = forms.ChoiceField(
        label="Solde",
        required=False,
        choices=[("", "Tous"), ("yes", "Solde impayé"), ("no", "Aucun impayé")],
    )
    is_active = forms.ChoiceField(
        label="Statut",
        required=False,
        choices=[("", "Tous"), ("1", "Actif"), ("0", "Inactif")],
    )
    is_tva_exempt = forms.ChoiceField(
        label="TVA",
        required=False,
        choices=[("", "Tous"), ("1", "Exonéré TVA"), ("0", "Assujetti TVA")],
    )


class ClientContactForm(forms.ModelForm):
    class Meta:
        model = ClientContact
        fields = [
            "first_name",
            "last_name",
            "job_title",
            "phone",
            "email",
            "is_primary",
            "notes",
        ]
        labels = {
            "first_name": "Prénom",
            "last_name": "Nom",
            "job_title": "Fonction",
            "phone": "Téléphone",
            "email": "Email",
            "is_primary": "Contact principal",
            "notes": "Notes",
        }
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("job_title", "phone", "email", "notes"):
            self.fields[f].required = False

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("first_name") and not cleaned.get("last_name"):
            raise ValidationError("Au moins le prénom ou le nom est requis.")
        return cleaned


class FormeJuridiqueForm(forms.ModelForm):
    """Admin-only form to add / edit forme juridique entries dynamically."""

    class Meta:
        model = FormeJuridique
        fields = ["name", "description", "is_active"]
        labels = {
            "name": "Sigle",
            "description": "Description complète",
            "is_active": "Active",
        }
        widgets = {
            "description": forms.TextInput(
                attrs={"placeholder": "Ex. Société par Actions"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].required = False

    def clean_name(self):
        name = self.cleaned_data.get("name", "").strip().upper()
        if not name:
            raise ValidationError("Le sigle est obligatoire.")
        qs = FormeJuridique.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(f"« {name} » existe déjà.")
        return name
