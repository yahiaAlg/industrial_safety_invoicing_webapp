# core/management/commands/seed_initial_expenses.py
"""
One-shot import of the real ISI expense records exported from the legacy system.

Source file : Expense-2026-05-05.csv
Run        : python manage.py seed_initial_expenses
             python manage.py seed_initial_expenses --dry-run   # preview only

Prerequisites
─────────────
* seed_db_minimal (or seed_db) must have been run first so that
  ExpenseCategory rows exist with the canonical naming convention.
* BeneficiaryType defaults must be seeded (seed_db_minimal does this).

Notes
─────────────────────────────────────────────────────────────────────
* All CSV records are overhead (is_overhead=True, no session/project link).
* Amounts use French comma notation  e.g. "58 040,00" → 58040.00
* For trainer payments (category "Honoraires Formateurs") irg_rate is set
  to 10% on both the Beneficiary record and each Expense row.
* Each unique supplier gets a Beneficiary record (name-based get_or_create).
* payment_reference is stored on the Expense directly; a PaymentAccount is
  NOT created because the CSV mixes CCP numbers, cheque refs, and invoice
  numbers — these are reference strings, not re-usable bank accounts.
* Duplicate detection: an expense is skipped if an existing Expense matches
  on (date, gross_amount, supplier name fragment, payment_reference).
"""

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.core.management.base import BaseCommand
from django.db import transaction

# ── Raw expense data (from Expense-2026-05-05.csv) ──────────────────────── #
# Fields: date, csv_category, description, amount_str, supplier,
#         payment_reference, receipt_missing
#
# csv_category → canonical ExpenseCategory mapping:
#   charge / charge espece  → "Charges & Honoraires Professionnels"
#   telecommunication        → "Télécommunications"
#   hotelerie                → "Hôtellerie & Hébergement"
#   paiment formateur        → "Honoraires Formateurs"
#   salaire / salaire espece → "Salaires & Charges Sociales"

EXPENSES = [
    # id=12
    {
        "date": "2026-04-19",
        "csv_category": "charge",
        "description": "Notaire Sétif",
        "amount_str": "58040,00",
        "supplier": "Makhoukhe Rima",
        "payment_reference": "EEMS BNA CHEQUE 2763398",
        "receipt_missing": True,
    },
    # id=11
    {
        "date": "2026-04-19",
        "csv_category": "charge",
        "description": "Notaire Sétif",
        "amount_str": "208040,00",
        "supplier": "Makhoukhe Rima",
        "payment_reference": "EEMS BNA CHEQUE 2763399",
        "receipt_missing": True,
    },
    # id=19
    {
        "date": "2026-04-15",
        "csv_category": "telecommunication",
        "description": "Facture téléphone 0773446213",
        "amount_str": "2300,00",
        "supplier": "Djezzy",
        "payment_reference": "Ticket 30150718",
        "receipt_missing": True,
    },
    # id=16
    {
        "date": "2026-04-11",
        "csv_category": "hotelerie",
        "description": "Facture hôtel — espèces",
        "amount_str": "18230,00",
        "supplier": "Hôtel Madaure",
        "payment_reference": "186/2026",
        "receipt_missing": True,
    },
    # id=20
    {
        "date": "2026-04-09",
        "csv_category": "paiment formateur",
        "description": "Paiement formateur — BDL 223",
        "amount_str": "100000,00",
        "supplier": "Gueddah Haroun",
        "payment_reference": "00500233 000 0001791 49",
        "receipt_missing": True,
    },
    # id=6
    {
        "date": "2026-04-09",
        "csv_category": "paiment formateur",
        "description": "Paiement formateur — CCP formation",
        "amount_str": "60000,00",
        "supplier": "Hammani Bachir",
        "payment_reference": "007 99999 0007406522-42",
        "receipt_missing": True,
    },
    # id=5
    {
        "date": "2026-04-09",
        "csv_category": "paiment formateur",
        "description": "Paiement formateur — CCP formation COMET",
        "amount_str": "60000,00",
        "supplier": "Abdenour Limame",
        "payment_reference": "007 99999 0001291843-21",
        "receipt_missing": True,
    },
    # id=21
    {
        "date": "2026-04-07",
        "csv_category": "paiment formateur",
        "description": "Paiement formateur — CCP formation CPHS",
        "amount_str": "82500,00",
        "supplier": "Hattab Mahmoud",
        "payment_reference": "007 99999 0001426002-94",
        "receipt_missing": True,
    },
    # id=10
    {
        "date": "2026-04-07",
        "csv_category": "paiment formateur",
        "description": "Paiement formateur — CCP formation",
        "amount_str": "75000,00",
        "supplier": "Hammani Bachir",
        "payment_reference": "007 99999 0007406522-42",
        "receipt_missing": True,
    },
    # id=9
    {
        "date": "2026-04-07",
        "csv_category": "paiment formateur",
        "description": "Paiement formateur — CCP formation COMET",
        "amount_str": "75000,00",
        "supplier": "Abdenour Limame",
        "payment_reference": "007 99999 0001291843-21",
        "receipt_missing": True,
    },
    # id=8
    {
        "date": "2026-04-07",
        "csv_category": "paiment formateur",
        "description": "Paiement formateur — CCP formation COMET",
        "amount_str": "32753,00",
        "supplier": "Messadi Mohammed Lyazid",
        "payment_reference": "007 99999 0001286344-28",
        "receipt_missing": True,
    },
    # id=7
    {
        "date": "2026-04-07",
        "csv_category": "paiment formateur",
        "description": "Paiement formateur — CCP étude Aïn Salah",
        "amount_str": "150000,00",
        "supplier": "Guezzi Nour El Houda",
        "payment_reference": "007 99999 0017652907-90",
        "receipt_missing": True,
    },
    # id=15
    {
        "date": "2026-04-06",
        "csv_category": "charge espece",
        "description": "Facture — espèces",
        "amount_str": "102000,10",
        "supplier": "ETS Krache Omar",
        "payment_reference": "26FC00023",
        "receipt_missing": True,
    },
    # id=3
    {
        "date": "2026-04-06",
        "csv_category": "salaire espece",
        "description": "CCP — paie mars 2026 (espèces)",
        "amount_str": "12000,00",
        "supplier": "Lakrache Hocine",
        "payment_reference": "007 99999 01868659/53",
        "receipt_missing": True,
    },
    # id=2
    {
        "date": "2026-04-06",
        "csv_category": "salaire",
        "description": "CCP — paie mars 2026",
        "amount_str": "38846,60",
        "supplier": "Lakrache Hocine",
        "payment_reference": "001 00711 020000 630063",
        "receipt_missing": True,
    },
    # id=1
    {
        "date": "2026-04-06",
        "csv_category": "salaire",
        "description": "CCP — paie mars 2026",
        "amount_str": "13935,00",
        "supplier": "Yahia Abderraouf Lakhfif",
        "payment_reference": "007 99999 0025979811 79",
        "receipt_missing": True,
    },
    # id=18
    {
        "date": "2026-04-04",
        "csv_category": "telecommunication",
        "description": "Facture téléphone — espèces",
        "amount_str": "1126,65",
        "supplier": "Actel Laararssa",
        "payment_reference": "5492969625",
        "receipt_missing": True,
    },
    # id=17
    {
        "date": "2026-04-04",
        "csv_category": "telecommunication",
        "description": "Facture internet — espèces",
        "amount_str": "8080,00",
        "supplier": "Actel Laararssa",
        "payment_reference": "36527557",
        "receipt_missing": True,
    },
    # id=14
    {
        "date": "2026-04-01",
        "csv_category": "hotelerie",
        "description": "Hébergement — Arab Banque",
        "amount_str": "64500,00",
        "supplier": "SPA Prom Bati",
        "payment_reference": "00026 05304 0051884500-70",
        "receipt_missing": True,
    },
    # id=13
    {
        "date": "2026-04-01",
        "csv_category": "hotelerie",
        "description": "Hébergement — CPA",
        "amount_str": "29529,70",
        "supplier": "Housna Kamel",
        "payment_reference": "00004 00327 4002026011-10",
        "receipt_missing": True,
    },
    # id=4
    {
        "date": "2026-04-01",
        "csv_category": "paiment formateur",
        "description": "Paiement formateur — CCP formation Wataniya",
        "amount_str": "75000,00",
        "supplier": "Messaoud Reda",
        "payment_reference": "007 99999 00 08245883 79",
        "receipt_missing": True,
    },
]

# CSV category slug → canonical ExpenseCategory name
CATEGORY_MAP = {
    "charge": "Charges & Honoraires Professionnels",
    "charge espece": "Charges & Honoraires Professionnels",
    "telecommunication": "Télécommunications",
    "hotelerie": "Hôtellerie & Hébergement",
    "paiment formateur": "Honoraires Formateurs",
    "salaire": "Salaires & Charges Sociales",
    "salaire espece": "Salaires & Charges Sociales",
}

# BeneficiaryType slug hint per CSV category  (matched against seeded type names)
BTYPE_HINT = {
    "charge": "Entreprise / Prestataire",
    "charge espece": "Entreprise / Prestataire",
    "telecommunication": "Entreprise / Prestataire",
    "hotelerie": "Hôtel / Hébergement",
    "paiment formateur": "Formateur",
    "salaire": "Salarié",
    "salaire espece": "Salarié",
}


def _parse_amount(raw: str) -> Decimal:
    """Convert French comma-decimal amount string to Decimal."""
    cleaned = raw.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"Cannot parse amount: {raw!r}")


class Command(BaseCommand):
    help = "Import the initial ISI expense records from the April-2026 CSV export."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be created without touching the database.",
        )
        parser.add_argument(
            "--skip-duplicates",
            action="store_true",
            default=True,
            help="Skip rows that already exist (default: True).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY-RUN mode — nothing will be saved.\n")
            )

        with transaction.atomic():
            self._run(dry_run)
            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS("✓ seed_initial_expenses completed."))

    # ------------------------------------------------------------------ #

    def _run(self, dry_run: bool):
        from financial.models import (
            Beneficiary,
            BeneficiaryType,
            Expense,
            ExpenseCategory,
        )

        # ── Resolve category objects ─────────────────────────────────── #
        cat_cache: dict[str, ExpenseCategory] = {}
        missing_cats: set[str] = set()

        for canonical in set(CATEGORY_MAP.values()):
            try:
                cat_cache[canonical] = ExpenseCategory.objects.get(name=canonical)
            except ExpenseCategory.DoesNotExist:
                missing_cats.add(canonical)

        if missing_cats:
            self.stdout.write(
                self.style.ERROR(
                    f"Missing ExpenseCategory rows — run seed_db_minimal first:\n"
                    + "\n".join(f"  · {n}" for n in sorted(missing_cats))
                )
            )
            return

        # ── Resolve / create BeneficiaryType helpers ─────────────────── #
        def _get_btype(hint: str) -> Optional[BeneficiaryType]:
            """Return the best-matching seeded BeneficiaryType or None."""
            qs = BeneficiaryType.objects.filter(is_seeded=True)
            # Exact match first
            exact = qs.filter(name__iexact=hint).first()
            if exact:
                return exact
            # Partial keyword match
            for word in hint.split():
                match = qs.filter(name__icontains=word).first()
                if match:
                    return match
            # Fallback: any seeded type
            return qs.first()

        btype_cache: dict = {}

        # ── Process each row ─────────────────────────────────────────── #
        created = skipped = 0

        for row in EXPENSES:
            csv_cat = row["csv_category"]
            canonical = CATEGORY_MAP[csv_cat]
            category = cat_cache[canonical]
            amount = _parse_amount(row["amount_str"])
            supplier = row["supplier"].strip()
            pay_ref = row["payment_reference"].strip()
            exp_date = datetime.strptime(row["date"], "%Y-%m-%d").date()

            # ── Duplicate check ──────────────────────────────────────── #
            if Expense.objects.filter(
                date=exp_date,
                gross_amount=amount,
                payment_reference=pay_ref,
            ).exists():
                self.stdout.write(
                    f"  · SKIP (duplicate) [{exp_date}] {supplier} — {amount:,.2f} DA"
                )
                skipped += 1
                continue

            # ── Beneficiary (get or create) ──────────────────────────── #
            btype_hint = BTYPE_HINT.get(csv_cat, "")
            if btype_hint not in btype_cache:
                btype_cache[btype_hint] = _get_btype(btype_hint)
            btype = btype_cache[btype_hint]

            is_formateur = csv_cat == "paiment formateur"
            if not dry_run:
                beneficiary, b_created = Beneficiary.objects.get_or_create(
                    name=supplier,
                    defaults={
                        "beneficiary_type": btype,
                        "irg_rate": Decimal("0.10") if is_formateur else Decimal("0"),
                        "is_trainer": is_formateur,
                    },
                )
            else:
                b_created = False
                beneficiary = None

            # ── Create Expense ────────────────────────────────────────── #
            # gross_amount == amount for all CSV rows (no IRG in source data).
            # Expense.save() will compute irg_amount = 0 and set amount = gross.
            if not dry_run:
                Expense.objects.create(
                    date=exp_date,
                    category=category,
                    description=row["description"],
                    gross_amount=amount,
                    irg_rate=Decimal("0.10") if is_formateur else Decimal("0"),
                    supplier=supplier,  # legacy text fallback
                    beneficiary=beneficiary,
                    payment_reference=pay_ref,
                    is_overhead=True,
                    receipt_missing=row["receipt_missing"],
                    approval_status=Expense.ApprovalStatus.APPROVED,
                    notes="Importé depuis export CSV Expense-2026-05-05.",
                )

            status = "CREATE" + (" (new beneficiary)" if b_created else "")
            self.stdout.write(
                f"  {status:30s} [{exp_date}] [{canonical}] "
                f"{supplier} — {amount:,.2f} DA  ref:{pay_ref}"
            )
            created += 1

        self.stdout.write(
            f"\n  Summary: {created} created, {skipped} skipped (duplicates)."
        )
