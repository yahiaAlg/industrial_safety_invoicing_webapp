# core/management/commands/seed_db.py
"""
Seed the database with:
  1. InstituteInfo, FormationInfo, BureauEtudeInfo  — from the real invoice header
  2. FormeJuridique standard Algerian entries
  3. ExpenseCategory defaults  (if financial app present)

Run: python manage.py seed_db
"""

from django.core.management.base import BaseCommand

# ── Institute data extracted from the real invoice document ────────────── #
INSTITUTE = {
    "name": "SARL Mouassasset Tamayouz Lilidara W Essalama",
    "abbreviation": "ISI",
    "address": "Cité Lotis Hachemi, 1ère Tranche, Étage 1 et 2",
    "postal_code": "19000",
    "city": "Sétif",
    "phone": "036 52 75 57",
    "email": "contact@isi-algerie.dz",
    "website": "",
    # Fiscal
    "rc": "21B0094443-00/19",
    "nif": "002119009444326",
    "nis": "197847060093220",
    "article_imposition": "19011780071",
    "agrement_number": "EFP 003-14/03/2022",
    # Bank
    "bank_name": "",
    "bank_account": "",
    "bank_rib": "001-00711030001829-41",
    # Branding
    "director_name": "",
    "director_title": "",
    "invoice_footer_text": (
        "Règlement par virement bancaire — RIB : 001-00711030001829-41\n"
        "Tout retard de paiement entraîne des pénalités conformément à la législation en vigueur."
    ),
}

# Formation-specific overrides  (same legal entity, same RC/NIF/NIS/ART.I)
FORMATION = {
    "name": "Centre de Formation ISI",
    "invoice_prefix": "F",
    "proforma_prefix": "FP",
    "tva_applicable": True,
    "tva_rate": "0.0900",
    "rc": INSTITUTE["rc"],
    "nif": INSTITUTE["nif"],
    "nis": INSTITUTE["nis"],
    "article_imposition": INSTITUTE["article_imposition"],
    "agrement_number": INSTITUTE["agrement_number"],
    "bank_rib": INSTITUTE["bank_rib"],
    "attestation_validity_years": 5,
    "min_attendance_percent": 80,
}

# Bureau d'Étude overrides
BUREAU = {
    "name": "Bureau d'Étude ISI",
    "invoice_prefix": "E",
    "proforma_prefix": "FP-E",
    "tva_applicable": True,
    "tva_rate": "0.1900",
    "rc": INSTITUTE["rc"],
    "nif": INSTITUTE["nif"],
    "nis": INSTITUTE["nis"],
    "article_imposition": INSTITUTE["article_imposition"],
    "bank_rib": INSTITUTE["bank_rib"],
}

# ── Formes juridiques ──────────────────────────────────────────────────── #
FORMES_JURIDIQUES = [
    ("Autre", "Forme juridique non listée ou non applicable"),
    ("SARL", "Société à Responsabilité Limitée"),
    ("SPA", "Société par Actions"),
    ("EURL", "Entreprise Unipersonnelle à Responsabilité Limitée"),
    ("SA", "Société Anonyme"),
    ("SNC", "Société en Nom Collectif"),
    ("SNCI", "Société en Nom Collectif et en Industrie"),
    ("SCS", "Société en Commandite Simple"),
    ("GIE", "Groupement d'Intérêt Économique"),
    ("EP", "Entreprise Publique"),
    ("EPS", "Établissement Public à caractère Social"),
    ("EPIC", "Établissement Public à caractère Industriel et Commercial"),
    ("SEM", "Société d'Économie Mixte"),
    ("SSPA", "Société par Actions Simplifiée Unipersonnelle"),
]

# ── Expense categories (unified naming — kept in sync with seed_db.py) ── #
EXPENSE_CATEGORIES = [
    # Direct costs
    ("Honoraires Formateurs",               True,  "#EAB308"),
    ("Salaires & Charges Sociales",         True,  "#3B82F6"),
    ("Sous-traitance",                      True,  "#8B5CF6"),
    ("Hôtellerie & Hébergement",            True,  "#F97316"),
    ("Transport & Déplacements",            True,  "#06B6D4"),
    ("Matériel Consommable",                True,  "#10B981"),
    ("Location de Salles",                  True,  "#F59E0B"),
    ("Équipements & Matériels",             True,  "#84CC16"),
    # Indirect / overhead
    ("Loyer & Charges Locatives",           False, "#6B7280"),
    ("Télécommunications",                  False, "#0EA5E9"),
    ("Charges & Honoraires Professionnels", False, "#7C3AED"),
    ("Fournitures de Bureau",               False, "#64748B"),
    ("Maintenance & Réparations",           False, "#EF4444"),
    ("Assurances",                          False, "#94A3B8"),
    ("Frais Bancaires",                     False, "#A1A1AA"),
    ("Communication & Publicité",           False, "#EC4899"),
    ("Divers",                              False, "#9CA3AF"),
]


class Command(BaseCommand):
    help = "Seed institute info, formes juridiques and expense categories."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing singleton values (default: only create if empty).",
        )

    def handle(self, *args, **options):
        force = options["force"]
        self._seed_admin(force)
        self._seed_institute(force)
        self._seed_formes_juridiques()
        self._seed_beneficiary_types()
        self._seed_expense_categories()
        self.stdout.write(self.style.SUCCESS("✓ Seed completed successfully."))

    # ------------------------------------------------------------------ #

    def _seed_admin(self, force):
        from django.contrib.auth.models import User

        from accounts.models import UserProfile

        username = "admin"
        password = "admin1234!"

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": "Admin",
                "last_name": "ISI",
                "email": INSTITUTE["email"],
                "is_staff": True,
                "is_superuser": True,
            },
        )

        if created or force:
            user.set_password(password)
            user.is_staff = True
            user.is_superuser = True
            user.save()
            UserProfile.objects.update_or_create(
                user=user,
                defaults={"role": UserProfile.ROLE_ADMIN, "is_active": True},
            )
            self.stdout.write(
                f"  → Admin user '{ username }' {'created' if created else 'updated'}."
            )
        else:
            self.stdout.write(
                f"  · Admin user '{ username }' already exists — skipped (use --force to overwrite)."
            )

    def _seed_institute(self, force):
        from decimal import Decimal

        from core.models import BureauEtudeInfo, FormationInfo, InstituteInfo

        # ── InstituteInfo ──────────────────────────────────────────────
        inst = InstituteInfo.get_instance()
        if force or not inst.name:
            for field, value in INSTITUTE.items():
                setattr(inst, field, value)
            inst.save()
            self.stdout.write("  → InstituteInfo updated.")
        else:
            self.stdout.write(
                "  · InstituteInfo already set — skipped (use --force to overwrite)."
            )

        # ── FormationInfo ──────────────────────────────────────────────
        fi = FormationInfo.get_instance()
        if force or not fi.rc:
            for field, value in FORMATION.items():
                if field == "tva_rate":
                    setattr(fi, field, Decimal(value))
                else:
                    setattr(fi, field, value)
            fi.save()
            self.stdout.write("  → FormationInfo updated.")
        else:
            self.stdout.write("  · FormationInfo already set — skipped.")

        # ── BureauEtudeInfo ────────────────────────────────────────────
        bi = BureauEtudeInfo.get_instance()
        if force or not bi.rc:
            for field, value in BUREAU.items():
                if field == "tva_rate":
                    setattr(bi, field, Decimal(value))
                else:
                    setattr(bi, field, value)
            bi.save()
            self.stdout.write("  → BureauEtudeInfo updated.")
        else:
            self.stdout.write("  · BureauEtudeInfo already set — skipped.")

    def _seed_formes_juridiques(self):
        from clients.models import FormeJuridique

        created = 0
        for name, description in FORMES_JURIDIQUES:
            _, was_created = FormeJuridique.objects.get_or_create(
                name=name,
                defaults={"description": description, "is_active": True},
            )
            if was_created:
                created += 1

        self.stdout.write(
            f"  → FormeJuridique: {created} created, "
            f"{len(FORMES_JURIDIQUES) - created} already existed."
        )

    def _seed_beneficiary_types(self):
        try:
            from financial.models import BeneficiaryType
        except ImportError:
            return

        BeneficiaryType.seed_defaults()
        count = BeneficiaryType.objects.filter(is_seeded=True).count()
        self.stdout.write(f"  → BeneficiaryType: {count} system entries ensured.")

    def _seed_expense_categories(self):
        try:
            from financial.models import ExpenseCategory
        except ImportError:
            return

        created = 0
        for name, is_direct, color in EXPENSE_CATEGORIES:
            _, was_created = ExpenseCategory.objects.get_or_create(
                name=name,
                defaults={"is_direct_cost": is_direct, "color": color},
            )
            if was_created:
                created += 1

        self.stdout.write(
            f"  → ExpenseCategory: {created} created, "
            f"{len(EXPENSE_CATEGORIES) - created} already existed."
        )
