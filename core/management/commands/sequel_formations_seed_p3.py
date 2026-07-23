# core/management/commands/sequel_formations_seed_p3.py
"""
Sequel seed — Part 3: mixed-industry invoices (2025 & 2026)

Loads:
  • 4 new Clients (SETS, Algeria Ham Motors, Ibn Aouf, Nedjmedine Plast)
  • Reuses existing clients: HALLIBURTON (P2), SETIF MEDIC Production (P1)
  • Formations (reuses HSE category, adds Formation Power BI, Premiers
    Secours, Gestion de Stock, Habilitation Produits Chimiques, etc.)
  • 7 finalised FORMATION invoices spanning YEAR 2025 (038, 039) and
    YEAR 2026 (036, 037, 038, 039, 040)

Source invoices:
  - FACTURE_036 / 24-06-2026 → SOCIÉTÉ D'ÉTUDES TECHNIQUES DE SÉTIF (SETS)
  - FACTURE_037 / 25-06-2026 → HALLIBURTON (Advanced Excel — 48 candidats)
  - FACTURE_038 / 08-08-2025 → SARL ALGERIA HAM MOTORS
  - FACTURE_038 / 30-06-2026 → HALLIBURTON (Advanced Excel — 52+1 candidats)
  - FACTURE_039 / 08-08-2025 → SARL IBN AOUF IMPORT & EXPORT
  - FACTURE_039 / 30-06-2026 → SARL SETIF MEDIC Production (remise 15%)
  - FACTURE_040 / 30-06-2026 → SARL NEDJMEDINE PLAST

Run:
    python manage.py sequel_formations_seed_p3
    python manage.py sequel_formations_seed_p3 --clear
"""

import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from clients.models import Client, FormeJuridique
from financial.models import Invoice, InvoiceItem, InvoiceSequence
from formations.models import Formation, FormationCategory

TVA_9 = Decimal("0.09")
ZERO = Decimal("0.00")

NEW_CLIENT_NAMES = [
    "SOCIETE D'ETUDES TECHNIQUES DE SETIF",
    "SARL ALGERIA HAM MOTORS",
    "SARL IBN AOUF IMPORT & EXPORT REC",
    "SARL NEDJMEDINE PLAST",
]


class Command(BaseCommand):
    help = "Sequel seed P3 — mixed-industry invoices (2025 & 2026)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete the P3 invoices (and any newly-created clients) before re-seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["clear"]:
            self._clear_data()

        self._seed_formation_catalog()
        clients = self._seed_clients()
        self._seed_invoices(clients)
        self._update_sequences()

        self.stdout.write(
            self.style.SUCCESS("\n✓ Sequel seed P3 terminé avec succès.\n")
        )

    # ------------------------------------------------------------------ #
    # Clear
    # ------------------------------------------------------------------ #
    def _clear_data(self):
        refs = ["F036/2026", "F037/2026", "F038/2025", "F038/2026",
                "F039/2025", "F039/2026", "F040/2026"]
        Invoice.objects.filter(reference__in=refs).delete()
        # Only remove clients created solely for this part (not shared ones).
        client_qs = Client.objects.filter(name__in=NEW_CLIENT_NAMES)
        InvoiceItem.objects.filter(invoice__client__in=client_qs).delete()
        Invoice.objects.filter(client__in=client_qs).delete()
        client_qs.delete()
        self.stdout.write("  ✓ Données P3 supprimées.")

    # ------------------------------------------------------------------ #
    # Formation catalog
    # ------------------------------------------------------------------ #
    def _seed_formation_catalog(self):
        from django.utils.text import slugify

        cat_hse, _ = FormationCategory.objects.get_or_create(
            code="HSE", defaults={"name": "Formation HSE", "color": "#EF4444"}
        )
        cat_com, _ = FormationCategory.objects.get_or_create(
            code="COM", defaults={"name": "Formation Commerce & Gestion", "color": "#2563EB"}
        )
        cat_met, _ = FormationCategory.objects.get_or_create(
            code="MET",
            defaults={"name": "Industrie & Métallurgie", "color": "#78716C"},
        )

        # (title, category, duration_days, duration_hours, base_price)
        formations = [
            ("Premiers Secours", cat_hse, 2, 16, Decimal("50000.00")),
            ("Advanced Excel Training", cat_hse, 3, 24, Decimal("60000.00")),
            ("Gestion de Stock", cat_com, 4, 32, Decimal("67278.29")),
            ("Habilitation de Conduite des Chariots Élévateurs", cat_met, 2, 16, Decimal("48000.00")),
            ("Superviseur HSE", cat_hse, 2, 16, Decimal("45000.00")),
            ("Formation Power BI", cat_com, 2, 16, Decimal("57000.00")),
            ("Habilitation Produits Chimiques", cat_hse, 5, 40, Decimal("53000.00")),
            ("Habilitation Électrique", cat_hse, 4, 32, Decimal("55000.00")),
            (
                "Fondamentaux des Opérations dans une Entreprise Industrielle "
                "(Maintenance, Production et Planification)",
                cat_met, 3, 24, Decimal("65000.00"),
            ),
        ]

        created = 0
        for title, cat, days, hours, price in formations:
            _, was_created = Formation.objects.get_or_create(
                slug=slugify(title)[:255],
                defaults={
                    "category": cat,
                    "title": title,
                    "duration_days": days,
                    "duration_hours": hours,
                    "base_price": price,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1

        self.stdout.write(
            f"  ✓ Catalogue P3 — {created} formations créées, "
            f"{len(formations) - created} déjà existantes."
        )

    # ------------------------------------------------------------------ #
    # Clients
    # ------------------------------------------------------------------ #
    def _seed_clients(self):
        fj_sarl, _ = FormeJuridique.objects.get_or_create(
            name="SARL",
            defaults={"description": "Société à Responsabilité Limitée"},
        )
        E = Client.ClientType.ENTREPRISE

        specs = [
            (
                "sets",
                dict(
                    name="SOCIETE D'ETUDES TECHNIQUES DE SETIF",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="Route des Abattoirs BP 89, Sétif 19000",
                    city="Sétif",
                    activity_sector="Études Techniques",
                    rc="99 B 0083290-00/19",
                    nif="099919008329067",
                    nis="097919010016831",
                    article_imposition="19011767171",
                ),
            ),
            (
                "algeria_ham_motors",
                dict(
                    name="SARL ALGERIA HAM MOTORS",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="Zone d'Activité, 74 Lot N°4, Ain Azel, Sétif",
                    city="Ain Azel",
                    activity_sector="Fabrication de Motocycles",
                    rc="1380090595-00/19",
                    nif="0013L9009059593",
                    nis="",
                    article_imposition="19402988015",
                ),
            ),
            (
                "ibn_aouf",
                dict(
                    name="SARL IBN AOUF IMPORT & EXPORT REC",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="Mechta Ouled Darouche, Ain Lahdjra, 19013 Sétif",
                    city="Sétif",
                    activity_sector="Importation de Cycles et Motocycles et leurs Accessoires",
                    rc="03 B 0085181-00/19",
                    nif="000319008518129",
                    nis="000319200545455",
                    article_imposition="19181709021",
                ),
            ),
            (
                "nedjmedine_plast",
                dict(
                    name="SARL NEDJMEDINE PLAST",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="RCD El Malha, Ain Arnet, Sétif",
                    city="Sétif",
                    activity_sector="Première Transformation de la Matière Plastique de Base",
                    rc="20 B0094004-00/19",
                    nif="002019009400445",
                    nis="002019260002170",
                    article_imposition="19269490041",
                ),
            ),
        ]

        clients = {}
        for key, defaults in specs:
            client, _ = Client.objects.get_or_create(
                name=defaults["name"], defaults=defaults
            )
            clients[key] = client

        # Reuse existing clients created in earlier sequels.
        clients["halliburton"] = Client.objects.get(
            name="HALLIBURTON ENERGY SERVICES INC ALGERIA DIVISION"
        )
        clients["setif_medic_prod"] = Client.objects.get(
            name="SARL SETIF MEDIC Production de Produits Pharmaceutiques"
        )

        self.stdout.write(f"  ✓ {len(specs)} nouveaux clients + 2 clients réutilisés")
        return clients

    # ------------------------------------------------------------------ #
    # Invoices
    # ------------------------------------------------------------------ #
    def _seed_invoices(self, C: dict):
        PP = InvoiceItem.PricingMode.PER_PERSON
        PD = InvoiceItem.PricingMode.PER_DAY
        FF = InvoiceItem.PricingMode.FORFAIT
        D = Decimal

        def _prime_and_get_ref(target_number: int, year: int) -> str:
            for phase in (InvoiceSequence.Phase.PROFORMA, InvoiceSequence.Phase.FINALE):
                InvoiceSequence.objects.update_or_create(
                    invoice_type=Invoice.InvoiceType.FORMATION,
                    year=year,
                    phase=phase,
                    defaults={"last_number": target_number - 1},
                )
            return Invoice._next_final_reference(Invoice.InvoiceType.FORMATION, year)

        specs = [
            # ── 036 / SETS — Premiers Secours (2026) ───────────────────
            dict(
                target_number=36,
                year=2026,
                date=datetime.date(2026, 6, 24),
                client=C["sets"],
                bc="696DG/2026 DU: 17/06/2026",
                mode="",
                amount_ht=D("100000.00"),
                amount_tva=D("9000.00"),
                amount_ttc=D("109000.00"),
                items=[
                    (1, "Formation premiers secours", PD, D("1"), D("2"), D("50000.00"), D("0")),
                ],
            ),
            # ── 037 / HALLIBURTON — Advanced Excel (48 candidats) ──────
            dict(
                target_number=37,
                year=2026,
                date=datetime.date(2026, 6, 25),
                client=C["halliburton"],
                bc="4201927994 DU: 07/06/2026",
                mode="",
                amount_ht=D("1118500.00"),
                amount_tva=D("100665.00"),
                amount_ttc=D("1219165.00"),
                items=[
                    (1, "Advanced excel training", PD, D("1"), D("3"), D("60000.00"), D("0")),
                    (2, "Single room for candidates (48)", FF, D("1"), D("1"), D("768000.00"), D("0")),
                    (3, "Coffee break (39)", FF, D("1"), D("1"), D("78000.00"), D("0")),
                    (4, "Restauration for candidates (51)", FF, D("1"), D("1"), D("116000.00"), D("0")),
                ],
            ),
            # ── 038 / ALGERIA HAM MOTORS — Gestion de Stock (2025) ─────
            dict(
                target_number=38,
                year=2025,
                date=datetime.date(2025, 8, 8),
                client=C["algeria_ham_motors"],
                bc="",
                mode="",
                amount_ht=D("201834.86"),
                amount_tva=D("18165.13"),
                amount_ttc=D("220000.00"),
                items=[
                    (1, "Formations Gestion de Stock", PD, D("1"), D("3"), D("67278.29"), D("0")),
                ],
            ),
            # ── 038 / HALLIBURTON — Advanced Excel (52+1 candidats) ────
            dict(
                target_number=38,
                year=2026,
                date=datetime.date(2026, 6, 30),
                client=C["halliburton"],
                bc="4201927994 DU: 07/06/2026",
                mode="",
                amount_ht=D("1996500.00"),
                amount_tva=D("179685.00"),
                amount_ttc=D("2176185.00"),
                items=[
                    (1, "Advanced excel training", PD, D("1"), D("3"), D("60000.00"), D("0")),
                    (2, "Single room for candidates (52+1)", FF, D("1"), D("1"), D("1404500.00"), D("0")),
                    (3, "Coffee break (42)", FF, D("1"), D("1"), D("84000.00"), D("0")),
                    (4, "Restauration for candidates (52)", FF, D("1"), D("1"), D("208000.00"), D("0")),
                ],
            ),
            # ── 039 / IBN AOUF — 3 formations (2025) ───────────────────
            dict(
                target_number=39,
                year=2025,
                date=datetime.date(2025, 8, 8),
                client=C["ibn_aouf"],
                bc="",
                mode="",
                amount_ht=D("300000.00"),
                amount_tva=D("27000.00"),
                amount_ttc=D("327000.00"),
                items=[
                    (
                        1,
                        "Formation l'Habilitation Conduite des Chariots Élévateurs",
                        PD, D("1"), D("2"), D("48000.00"), D("0"),
                    ),
                    (2, "Formation superviseur HSE", PP, D("2"), D("1"), D("45000.00"), D("0")),
                    (3, "Formation Power BI", PD, D("1"), D("2"), D("57000.00"), D("0")),
                ],
            ),
            # ── 039 / SETIF MEDIC Production — remise 15% (2026) ───────
            dict(
                target_number=39,
                year=2026,
                date=datetime.date(2026, 6, 30),
                client=C["setif_medic_prod"],
                bc="81-82/DG/DRH/2026",
                mode="",
                amount_ht=D("412250.00"),
                amount_tva=D("37102.50"),
                amount_ttc=D("449352.50"),
                items=[
                    (
                        1,
                        "Formation Habilitation Produits Chimiques",
                        PD, D("1"), D("5"), D("53000.00"), D("15"),
                    ),
                    (
                        2,
                        "Formation Habilitation Électrique",
                        PD, D("1"), D("4"), D("55000.00"), D("15"),
                    ),
                ],
            ),
            # ── 040 / NEDJMEDINE PLAST — Fondamentaux Opérations (2026) ─
            dict(
                target_number=40,
                year=2026,
                date=datetime.date(2026, 6, 30),
                client=C["nedjmedine_plast"],
                bc="",
                mode="",
                amount_ht=D("195000.00"),
                amount_tva=D("17550.00"),
                amount_ttc=D("212550.00"),
                items=[
                    (
                        1,
                        "Formation fondamentaux opérations dans une entreprise "
                        "industrielle (maintenance-production et planification)",
                        PD, D("1"), D("3"), D("65000.00"), D("0"),
                    ),
                ],
            ),
        ]

        created = 0
        for spec in specs:
            client = spec["client"]
            final_ref = _prime_and_get_ref(spec["target_number"], spec["year"])

            inv = Invoice.objects.create(
                invoice_type=Invoice.InvoiceType.FORMATION,
                phase=Invoice.Phase.PROFORMA,
                status=Invoice.Status.DRAFT,
                client=client,
                invoice_date=spec["date"],
                tva_rate=TVA_9,
                bon_commande_number=spec["bc"],
                mode_reglement=spec["mode"],
            )

            item_objs = []
            for order, desc, mode, nb_persons, nb_days, unit_price, discount in spec["items"]:
                item = InvoiceItem(
                    invoice=inv,
                    order=order,
                    description=desc,
                    pricing_mode=mode,
                    nb_persons=nb_persons,
                    nb_days=nb_days,
                    unit_price_ht=unit_price,
                    discount_percent=discount,
                    total_ht=ZERO,
                )
                item.total_ht = item._compute_total_ht()
                item_objs.append(item)

            InvoiceItem.objects.bulk_create(item_objs)

            finalized_at = timezone.make_aware(
                datetime.datetime.combine(spec["date"], datetime.time(12, 0))
            )
            Invoice.objects.filter(pk=inv.pk).update(
                phase=Invoice.Phase.FINALE,
                status=Invoice.Status.UNPAID,
                reference=final_ref,
                finalized_at=finalized_at,
                amount_ht=spec["amount_ht"],
                amount_tva=spec["amount_tva"],
                amount_ttc=spec["amount_ttc"],
                amount_remaining=spec["amount_ttc"],
                client_name_snapshot=client.name,
                client_address_snapshot=client.address,
                client_type_snapshot=client.client_type,
                client_nif_snapshot=client.nif,
                client_nis_snapshot=getattr(client, "nis", ""),
                client_rc_snapshot=client.rc,
                client_ai_snapshot=client.article_imposition,
                client_nin_snapshot=getattr(client, "nin", ""),
                client_rib_snapshot=getattr(client, "rib", ""),
                client_tin_snapshot=getattr(client, "tin", ""),
            )
            created += 1
            self.stdout.write(f"    + {final_ref}  {client.name[:50]}")

        self.stdout.write(f"  ✓ {created} factures FORMATION finalisées")

    # ------------------------------------------------------------------ #
    # Sequence counters
    # ------------------------------------------------------------------ #
    def _update_sequences(self):
        for year in (2025, 2026):
            seq = InvoiceSequence.objects.filter(
                invoice_type=Invoice.InvoiceType.FORMATION,
                year=year,
                phase=InvoiceSequence.Phase.FINALE,
            ).first()
            last = seq.last_number if seq else "?"
            self.stdout.write(
                f"  ✓ InvoiceSequence {year} → dernier n° {last} (géré automatiquement)"
            )
