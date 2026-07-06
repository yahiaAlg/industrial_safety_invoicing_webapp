"""
Core models — institute configuration and singleton business-line settings.
v3.1: Added legal_infos + bank_rib to FormationInfo and BureauEtudeInfo;
      agrement_number + article_imposition already on InstituteInfo.
      FormationInfo TVA default corrected to 9% per Algerian fiscal code.
"""

from decimal import Decimal

from django.db import models

from core.base_models import TimeStampedModel


class SingletonModel(TimeStampedModel):
    """
    Abstract base for singleton configuration records.
    Forces pk=1 on save; ignores delete calls.
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # Singleton records cannot be deleted.

    @classmethod
    def get_instance(cls):
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance


class InstituteInfo(SingletonModel):
    """
    General information about the Industrial Safety Institute.
    Singleton — only one record should ever exist.
    """

    name = models.CharField(max_length=255, verbose_name="Nom de l'institut")
    abbreviation = models.CharField(
        max_length=50, blank=True, verbose_name="Abréviation"
    )
    address = models.TextField(verbose_name="Adresse")
    postal_code = models.CharField(
        max_length=10, blank=True, verbose_name="Code postal"
    )
    city = models.CharField(max_length=100, verbose_name="Ville")
    phone = models.CharField(max_length=50, verbose_name="Téléphone")
    email = models.EmailField(verbose_name="Email")
    website = models.URLField(blank=True, verbose_name="Site web")

    # ---- Algerian fiscal registration --------------------------------- #
    rc = models.CharField(max_length=100, blank=True, verbose_name="Numéro RC")
    nif = models.CharField(max_length=100, blank=True, verbose_name="NIF")
    nis = models.CharField(max_length=100, blank=True, verbose_name="NIS")
    article_imposition = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Article d'imposition (ART.I)",
    )
    agrement_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="N° Agrément",
        help_text="Numéro d'agrément officiel de l'institut (ex. formation professionnelle).",
    )

    # ---- Bank details ------------------------------------------------- #
    bank_name = models.CharField(max_length=255, blank=True, verbose_name="Banque")
    bank_account = models.CharField(
        max_length=255, blank=True, verbose_name="N° de compte"
    )
    bank_rib = models.CharField(max_length=255, blank=True, verbose_name="RIB")

    # ---- Branding ----------------------------------------------------- #
    logo = models.ImageField(upload_to="institute/", blank=True, verbose_name="Logo")
    director_signature = models.ImageField(
        upload_to="institute/", blank=True, verbose_name="Signature du directeur"
    )
    director_name = models.CharField(
        max_length=255, blank=True, verbose_name="Nom du directeur"
    )
    director_title = models.CharField(
        max_length=255, blank=True, verbose_name="Titre du directeur"
    )

    # ---- Invoice footer ----------------------------------------------- #
    invoice_footer_text = models.TextField(
        blank=True,
        verbose_name="Pied de page des factures",
        help_text="Texte affiché en bas de chaque facture (conditions de paiement, etc.).",
    )

    class Meta:
        verbose_name = "Informations de l'institut"
        verbose_name_plural = "Informations de l'institut"

    def __str__(self):
        return self.name


class BureauEtudeInfo(SingletonModel):
    """
    Configuration specific to the Études (Consulting) business line.
    TVA: 19% standard rate for consulting services.
    """

    name = models.CharField(
        max_length=255, default="Bureau d'Étude", verbose_name="Nom"
    )
    description = models.TextField(blank=True, verbose_name="Description")
    address = models.TextField(blank=True, verbose_name="Adresse spécifique")
    phone = models.CharField(
        max_length=50, blank=True, verbose_name="Téléphone spécifique"
    )
    email = models.EmailField(blank=True, verbose_name="Email spécifique")

    # ---- Invoice numbering ------------------------------------------- #
    invoice_prefix = models.CharField(
        max_length=10,
        default="E",
        verbose_name="Préfixe des factures",
        help_text="Utilisé dans les références — ex. E → E-2026-001.",
    )
    proforma_prefix = models.CharField(
        max_length=10,
        default="FP-E",
        verbose_name="Préfixe proforma",
        help_text="Utilisé dans les références proforma — ex. FP-E → FP-E-001-2026.",
    )

    # ---- TVA ---------------------------------------------------------- #
    tva_applicable = models.BooleanField(default=True, verbose_name="TVA applicable")
    tva_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.19"),
        verbose_name="Taux de TVA",
        help_text="Taux standard 19% pour les études et le conseil.",
    )

    # ---- Legal / fiscal identifiers ---------------------------------- #
    rc = models.CharField(max_length=100, blank=True, verbose_name="Numéro RC")
    nif = models.CharField(max_length=100, blank=True, verbose_name="NIF")
    nis = models.CharField(max_length=100, blank=True, verbose_name="NIS")
    article_imposition = models.CharField(
        max_length=100, blank=True, verbose_name="Article d'imposition (ART.I)"
    )

    # ---- Bank details ------------------------------------------------- #
    bank_name = models.CharField(max_length=255, blank=True, verbose_name="Banque")
    bank_account = models.CharField(
        max_length=255, blank=True, verbose_name="N° de compte"
    )
    bank_rib = models.CharField(max_length=255, blank=True, verbose_name="RIB")

    @property
    def legal_infos(self) -> str:
        """Assembled for invoice template backward-compat."""
        lines = []
        if self.rc:
            lines.append(f"RC : {self.rc}")
        if self.nif:
            lines.append(f"NIF : {self.nif}")
        if self.nis:
            lines.append(f"NIS : {self.nis}")
        if self.article_imposition:
            lines.append(f"ART.I : {self.article_imposition}")
        return "\n".join(lines)

    # ---- Signatory ---------------------------------------------------- #
    chief_engineer_name = models.CharField(
        max_length=255, blank=True, verbose_name="Ingénieur en chef"
    )
    chief_engineer_title = models.CharField(
        max_length=255, blank=True, verbose_name="Titre"
    )
    chief_engineer_signature = models.ImageField(
        upload_to="etudes/", blank=True, verbose_name="Signature de l'ingénieur en chef"
    )

    class Meta:
        verbose_name = "Informations Bureau d'Étude"
        verbose_name_plural = "Informations Bureau d'Étude"

    def __str__(self):
        return self.name


class FormationInfo(SingletonModel):
    """
    Configuration specific to the Formations (Training) business line.
    TVA: 9% — reduced rate applicable to professional training services
    under Algerian fiscal code.
    """

    name = models.CharField(
        max_length=255, default="Centre de Formation", verbose_name="Nom"
    )
    description = models.TextField(blank=True, verbose_name="Description")
    address = models.TextField(blank=True, verbose_name="Adresse spécifique")
    phone = models.CharField(
        max_length=50, blank=True, verbose_name="Téléphone spécifique"
    )
    email = models.EmailField(blank=True, verbose_name="Email spécifique")

    # ---- Invoice numbering ------------------------------------------- #
    invoice_prefix = models.CharField(
        max_length=10,
        default="F",
        verbose_name="Préfixe des factures",
        help_text="Utilisé dans les références — ex. F → F-2026-001.",
    )
    proforma_prefix = models.CharField(
        max_length=10,
        default="FP",
        verbose_name="Préfixe proforma",
        help_text="Utilisé dans les références proforma — ex. FP → FP-001-2026.",
    )

    # ---- TVA ---------------------------------------------------------- #
    tva_applicable = models.BooleanField(default=True, verbose_name="TVA applicable")
    tva_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal("0.09"),
        verbose_name="Taux de TVA",
        help_text="Taux réduit 9% pour les prestations de formation professionnelle.",
    )

    # ---- Legal / fiscal identifiers ---------------------------------- #
    rc = models.CharField(max_length=100, blank=True, verbose_name="Numéro RC")
    nif = models.CharField(max_length=100, blank=True, verbose_name="NIF")
    nis = models.CharField(max_length=100, blank=True, verbose_name="NIS")
    article_imposition = models.CharField(
        max_length=100, blank=True, verbose_name="Article d'imposition (ART.I)"
    )
    agrement_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="N° Agrément formation",
        help_text="Ex. AGR/FORM/2019/0042",
    )

    # ---- Bank details ------------------------------------------------- #
    bank_name = models.CharField(max_length=255, blank=True, verbose_name="Banque")
    bank_account = models.CharField(
        max_length=255, blank=True, verbose_name="N° de compte"
    )
    bank_rib = models.CharField(max_length=255, blank=True, verbose_name="RIB")

    @property
    def legal_infos(self) -> str:
        """Assembled for invoice template backward-compat."""
        lines = []
        if self.rc:
            lines.append(f"RC : {self.rc}")
        if self.nif:
            lines.append(f"NIF : {self.nif}")
        if self.nis:
            lines.append(f"NIS : {self.nis}")
        if self.article_imposition:
            lines.append(f"ART.I : {self.article_imposition}")
        if self.agrement_number:
            lines.append(f"Agrément N° : {self.agrement_number}")
        return "\n".join(lines)

    # ---- Training director ------------------------------------------- #
    director_name = models.CharField(
        max_length=255, blank=True, verbose_name="Directeur"
    )
    director_title = models.CharField(max_length=255, blank=True, verbose_name="Titre")
    director_signature = models.ImageField(
        upload_to="formations/", blank=True, verbose_name="Signature du directeur"
    )

    # ---- Attestations ------------------------------------------------- #
    attestation_validity_years = models.PositiveIntegerField(
        default=5, verbose_name="Validité des attestations (années)"
    )
    min_attendance_percent = models.PositiveIntegerField(
        default=80,
        verbose_name="Présence minimale requise (%)",
        help_text="Seuil de présence en dessous duquel aucune attestation n'est délivrée.",
    )

    class Meta:
        verbose_name = "Informations Centre de Formation"
        verbose_name_plural = "Informations Centre de Formation"

    def __str__(self):
        return self.name
