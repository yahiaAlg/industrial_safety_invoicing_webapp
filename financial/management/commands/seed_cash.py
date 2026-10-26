"""
Seed / erase demo data for the cash journal (Caisse) — testing only.

    python manage.py seed_cash            # create the demo journal + sample vouchers
    python manage.py seed_cash --clear    # erase the demo journal and its vouchers
    python manage.py seed_cash --reset    # erase then re-create

Only the journal named DEMO_NAME (and the vouchers inside it) is ever touched;
payments, expenses, invoices and your real journals are never modified.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from financial.models import CashJournal, CashVoucher

DEMO_NAME = "[DÉMO] Caisse de test"

# (days ago, kind, amount, label, counterparty)
SAMPLE = [
    (85, "in", "120000.00", "Règlement facture formation SST", "SARL Sanofi Algérie"),
    (82, "out", "8500.00", "Achat fournitures de bureau", "Papeterie El Wiam"),
    (78, "out", "15000.00", "Frais de transport formateur", "Karim B."),
    (70, "in", "45000.00", "Acompte étude HSE", "EURL Tassili Pétrole"),
    (63, "out", "22000.00", "Restauration session incendie", "Traiteur El Baraka"),
    (55, "out", "6200.50", "Recharge extincteurs", "Sécur Plus"),
    (48, "in", "80000.00", "Règlement facture formation secourisme", "SPA Cosider"),
    (40, "out", "30000.00", "Honoraires formateur", "Samir H."),
    (33, "out", "4500.00", "Carburant véhicule de service", "Station Naftal"),
    (27, "in", "15000.00", "Vente supports de cours", "Participants session 12"),
    (20, "out", "12750.00", "Maintenance climatisation salle B", "Froid Service"),
    (14, "in", "60000.00", "Règlement facture audit sécurité", "SARL Mobilis Sud"),
    (9, "out", "9800.00", "Impression attestations", "Imprimerie Ennour"),
    (4, "out", "3200.00", "Café et eau — salle de formation", "Supérette Rahma"),
    (1, "in", "25000.00", "Règlement facture formation EPI", "EURL Batigec"),
]


class Command(BaseCommand):
    help = "Seed (or erase with --clear) demo data for the cash journal. Testing only."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Erase the demo journal and its vouchers.")
        parser.add_argument("--reset", action="store_true", help="Erase then re-create the demo data.")
        parser.add_argument("--initial", default="50000", help="Initial balance of the demo journal (default 50000).")

    @transaction.atomic
    def handle(self, *args, **opts):
        if opts["clear"] or opts["reset"]:
            self._clear()
            if opts["clear"]:
                return
        self._seed(Decimal(opts["initial"]))

    def _clear(self):
        journals = CashJournal.objects.filter(name=DEMO_NAME)
        n_v = CashVoucher.objects.filter(journal__in=journals).count()
        CashVoucher.objects.filter(journal__in=journals).delete()
        n_j = journals.count()
        journals.delete()
        self.stdout.write(self.style.SUCCESS(f"Erased {n_j} demo journal(s) and {n_v} voucher(s)."))

    def _seed(self, initial):
        if CashJournal.objects.filter(name=DEMO_NAME).exists():
            self.stdout.write(self.style.WARNING("Demo data already present — use --reset to recreate."))
            return
        journal = CashJournal.objects.create(
            name=DEMO_NAME, initial_balance=initial, notes="Données de test — supprimables avec seed_cash --clear"
        )
        today = timezone.localdate()
        for days, kind, amount, label, who in SAMPLE:
            CashVoucher.objects.create(
                journal=journal, kind=kind, date=today - timedelta(days=days),
                amount=Decimal(amount), label=label, counterparty=who,
            )
        self.stdout.write(
            self.style.SUCCESS(
                f"Created « {DEMO_NAME} » with {len(SAMPLE)} vouchers — "
                f"balance: {journal.current_balance:,.2f} DA. Erase with: manage.py seed_cash --clear"
            )
        )
