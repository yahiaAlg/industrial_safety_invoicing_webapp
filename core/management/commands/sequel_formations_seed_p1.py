# core/management/commands/sequel_formations_seed_p1.py
"""
Sequel seed — Part 1: SARL SETIF MEDIC pharmaceutical invoices (2025)

Loads:
  • 1 new FormationCategory : Industrie Pharmaceutique (PHM)
  • 17 new Formations extracted from invoices 025, 029, 035
  • 2 new Clients : SARL SETIF MEDIC Production & Commerce de Gros
  • 3 finalised FORMATION invoices for year 2025 (025, 029, 035)

Source invoices:
  - FACTURE_025 / 19-06-2025 → SARL SETIF MEDIC Production de Produits Pharmaceutiques
  - FACTURE_029 / 25-06-2025 → SARL SETIF MEDIC (Commerce de Gros)
  - FACTURE_035 / 07-07-2025 → SARL SETIF MEDIC (Commerce de Gros)

Run:
    python manage.py sequel_formations_seed_p1
    python manage.py sequel_formations_seed_p1 --clear
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
YEAR = 2025


class Command(BaseCommand):
    help = "Sequel seed P1 — SARL SETIF MEDIC pharmaceutical invoices (2025)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete SETIF MEDIC clients and their invoices before re-seeding.",
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
            self.style.SUCCESS("\n✓ Sequel seed P1 terminé avec succès.\n")
        )

    # ------------------------------------------------------------------ #
    # Clear
    # ------------------------------------------------------------------ #
    def _clear_data(self):
        targets = [
            "SARL SETIF MEDIC Production de Produits Pharmaceutiques",
            "SARL SETIF MEDIC",
        ]
        client_qs = Client.objects.filter(name__in=targets)
        InvoiceItem.objects.filter(invoice__client__in=client_qs).delete()
        Invoice.objects.filter(client__in=client_qs).delete()
        client_qs.delete()
        self.stdout.write("  ✓ Données SETIF MEDIC supprimées.")

    # ------------------------------------------------------------------ #
    # Formation catalog — new category + 17 formations
    # ------------------------------------------------------------------ #
    def _seed_formation_catalog(self):
        from django.utils.text import slugify

        cat, _ = FormationCategory.objects.get_or_create(
            code="PHM",
            defaults={"name": "Industrie Pharmaceutique", "color": "#0891B2"},
        )

        # (title, duration_days, duration_hours, base_price)
        formations = [
            # ── Invoice 025 — Production pharmaceutique ────────────────
            (
                "BPF Avancée avec Évaluation à Chaud et Rapport d'Action",
                2,
                16,
                Decimal("72500.00"),
            ),
            (
                "Initiation Audit BPF — Rédaction des Rapports",
                2,
                16,
                Decimal("42500.00"),
            ),
            (
                "Modalités de Recrutement et Induction en Industrie Pharmaceutique",
                1,
                8,
                Decimal("60172.47"),
            ),
            (
                "Gestion des Formations et Qualification du Personnel",
                1,
                8,
                Decimal("32000.00"),
            ),
            (
                "Gestion des Flux en Industrie Pharmaceutique",
                1,
                8,
                Decimal("30000.00"),
            ),
            (
                "Maîtrise et Gestion Documentaire",
                1,
                8,
                Decimal("65000.00"),
            ),
            (
                "Exécution Pratique du Processus de Gestion Documentaire",
                1,
                8,
                Decimal("45000.00"),
            ),
            (
                "Site Master File (SMF)",
                1,
                8,
                Decimal("35000.00"),
            ),
            (
                "Manuel Qualité",
                1,
                8,
                Decimal("38000.00"),
            ),
            # ── Invoice 029 — Commerce de Gros : risques & marchés ─────
            (
                "Initiation Analyse de Risque",
                2,
                16,
                Decimal("96618.39"),
            ),
            (
                "Analyse de Risque",
                5,
                40,
                Decimal("52200.00"),
            ),
            (
                "Étude de Marché et Sélection des Produits",
                4,
                32,
                Decimal("50000.00"),
            ),
            (
                "Étude Technico-Économique et Business Plan — Nouveaux Produits",
                10,
                80,
                Decimal("37191.00"),
            ),
            (
                "Qualification et Agrément des Fournisseurs et Sous-Traitants Logistiques",
                4,
                32,
                Decimal("87500.00"),
            ),
            # ── Invoice 035 — Distribution pharmaceutique ──────────────
            (
                "Lutte Contre les Nuisibles — Entrepôts et Distribution Pharmaceutique",
                3,
                24,
                Decimal("100595.57"),
            ),
            (
                "Gestion des Approvisionnements en Distribution Pharmaceutique",
                5,
                40,
                Decimal("75800.00"),
            ),
            (
                "Organisation et Gestion des Affaires Réglementaires",
                4,
                32,
                Decimal("57500.00"),
            ),
            (
                "Change Control et Gestion des Déviations en Milieu Distributeur",
                4,
                32,
                Decimal("50230.50"),
            ),
        ]

        created = 0
        for title, days, hours, price in formations:
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
            f"  ✓ Catégorie PHM — {created} formations créées, "
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
                "setif_medic_prod",
                dict(
                    name="SARL SETIF MEDIC Production de Produits Pharmaceutiques",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="ZI Toussa Classe N° 20 Groupe N°81 Ilot N°36",
                    city="Sétif",
                    activity_sector="Production de Produits Pharmaceutiques",
                    rc="08 B 0087714-04/19",
                    nif="0081900877145919004",
                    nis="000819010054947",
                    article_imposition="19016311031",
                ),
            ),
            (
                "setif_medic_gros",
                dict(
                    name="SARL SETIF MEDIC",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="N°30 Rue Hamadou Torki Cité Tlidjene",
                    city="Sétif",
                    activity_sector="Commerce de Gros de Produits Pharmaceutiques",
                    rc="08 B 0087714-00/19",
                    nif="000819008771459",
                    nis="000819010054947",
                    article_imposition="19012916024",
                ),
            ),
        ]

        clients = {}
        for key, defaults in specs:
            client, _ = Client.objects.get_or_create(
                name=defaults["name"], defaults=defaults
            )
            clients[key] = client

        self.stdout.write(f"  ✓ {len(clients)} clients SETIF MEDIC")
        return clients

    # ------------------------------------------------------------------ #
    # Invoices
    # ------------------------------------------------------------------ #
    def _seed_invoices(self, C: dict):
        PP = InvoiceItem.PricingMode.PER_PERSON
        PD = InvoiceItem.PricingMode.PER_DAY
        FF = InvoiceItem.PricingMode.FORFAIT
        D = Decimal

        # Each spec: ref, date, client key, bc, mode, totals, items.
        # Items: (order, description, pricing_mode, nb_persons, nb_days, unit_price_ht)
        #
        # Invoice 025 uses "Prix U/p" (per-person) → PP for qty > 1, FF for qty = 1.
        # Invoices 029 & 035 use "Prix U/j" (per-day) → PD where qty × price = total,
        # FF where the arithmetic does not resolve cleanly from the invoice columns alone.
        def _prime_and_get_ref(target_number: int) -> str:
            """
            Set the FORMATION/FINALE sequence for YEAR to (target_number - 1)
            so that the next call to _next_final_reference() yields exactly
            target_number — matching the original invoice document numbering.
            """
            for phase in (InvoiceSequence.Phase.PROFORMA, InvoiceSequence.Phase.FINALE):
                InvoiceSequence.objects.update_or_create(
                    invoice_type=Invoice.InvoiceType.FORMATION,
                    year=YEAR,
                    phase=phase,
                    defaults={"last_number": target_number - 1},
                )
            return Invoice._next_final_reference(Invoice.InvoiceType.FORMATION, YEAR)

        specs = [
            # ── 025 / SETIF MEDIC Production — multi-formations BPF ───
            dict(
                target_number=25,
                date=datetime.date(2025, 6, 19),
                client=C["setif_medic_prod"],
                bc="",
                mode="",
                amount_ht=D("535172.47"),
                amount_tva=D("48165.52"),
                amount_ttc=D("583338.00"),
                items=[
                    # (order, description, mode, nb_persons, nb_days, unit_price_ht)
                    (
                        1,
                        "Formation BPF avancée en vigueur avec évaluation à chaud "
                        "et établissement du rapport d'action de la formation",
                        PP,
                        D("2"),
                        D("1"),
                        D("72500.00"),
                    ),
                    (
                        2,
                        "Formation initiation sur audit BPF rédaction des rapports",
                        PP,
                        D("2"),
                        D("1"),
                        D("42500.00"),
                    ),
                    (
                        3,
                        "Formation les modalités de recrutement et induction "
                        "en industrie pharmaceutique",
                        FF,
                        D("1"),
                        D("1"),
                        D("60172.47"),
                    ),
                    (
                        4,
                        "Formation la gestion des formations et la qualification du personnel",
                        FF,
                        D("1"),
                        D("1"),
                        D("32000.00"),
                    ),
                    (
                        5,
                        "Formation sur la gestion des flux en industrie pharmaceutique",
                        FF,
                        D("1"),
                        D("1"),
                        D("30000.00"),
                    ),
                    (
                        6,
                        "Formation sur la maîtrise et la gestion documentaire",
                        FF,
                        D("1"),
                        D("1"),
                        D("65000.00"),
                    ),
                    (
                        7,
                        "Formation pratique exécution du processus de gestion documentaire",
                        FF,
                        D("1"),
                        D("1"),
                        D("45000.00"),
                    ),
                    (
                        8,
                        "Formation sur le SMF ou site master file",
                        FF,
                        D("1"),
                        D("1"),
                        D("35000.00"),
                    ),
                    (
                        9,
                        "Formation sur le manuel qualité",
                        FF,
                        D("1"),
                        D("1"),
                        D("38000.00"),
                    ),
                ],
            ),
            # ── 029 / SETIF MEDIC Commerce de Gros — Risques & Marchés ─
            dict(
                target_number=29,
                date=datetime.date(2025, 6, 25),
                client=C["setif_medic_gros"],
                bc="",
                mode="",
                amount_ht=D("1376146.78"),
                amount_tva=D("123853.22"),
                amount_ttc=D("1500000.00"),
                items=[
                    (
                        1,
                        "Formation d'initiation analyse de risque",
                        PD,
                        D("1"),
                        D("2"),
                        D("96618.39"),  # 2j × 96 618.39 = 193 236.78
                    ),
                    (
                        2,
                        "Formation analyse de risque",
                        FF,
                        D("1"),
                        D("1"),
                        D("261000.00"),  # forfait global (5j implicites)
                    ),
                    (
                        3,
                        "Formation l'étude de marché et sélection des produits",
                        PP,
                        D("4"),
                        D("1"),
                        D("50000.00"),  # 4p × 50 000 = 200 000
                    ),
                    (
                        4,
                        "Formation l'étude technico-économique et l'élaboration de "
                        "business plan pour lancement de nouveaux produits",
                        PP,
                        D("10"),
                        D("1"),
                        D("37191.00"),  # 10p × 37 191 = 371 910
                    ),
                    (
                        5,
                        "Formation la qualification & l'agrément des fournisseurs "
                        "et sous-traitants logistiques",
                        PP,
                        D("4"),
                        D("1"),
                        D("87500.00"),  # 4p × 87 500 = 350 000
                    ),
                ],
            ),
            # ── 035 / SETIF MEDIC Commerce de Gros — Distribution Pharma
            dict(
                target_number=35,
                date=datetime.date(2025, 7, 7),
                client=C["setif_medic_gros"],
                bc="",
                mode="",
                amount_ht=D("1111708.71"),
                amount_tva=D("100053.79"),
                amount_ttc=D("1211762.50"),
                items=[
                    (
                        1,
                        "Formation lutte contre les nuisibles dans les entrepôts "
                        "et centres de distribution pharmaceutique",
                        PD,
                        D("1"),
                        D("3"),
                        D("100595.57"),  # 3j × 100 595.57 = 301 786.71
                    ),
                    (
                        2,
                        "Formation gestion des approvisionnements en distribution "
                        "pharmaceutique (achat local & import/export)",
                        PD,
                        D("1"),
                        D("5"),
                        D("75800.00"),  # 5j × 75 800 = 379 000
                    ),
                    (
                        3,
                        "Formation l'organisation la gestion des affaires réglementaires "
                        "(autorisations, déclarations, vigilance)",
                        PD,
                        D("1"),
                        D("4"),
                        D("57500.00"),  # 4j × 57 500 = 230 000
                    ),
                    (
                        4,
                        "Formation d'initiation sur le change control et la gestion "
                        "des déviations en milieu distributeur",
                        PD,
                        D("1"),
                        D("4"),
                        D("50230.50"),  # 4j × 50 230.50 = 200 922
                    ),
                ],
            ),
        ]

        created = 0
        for spec in specs:
            client = spec["client"]
            final_ref = _prime_and_get_ref(spec["target_number"])

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
            for order, desc, mode, nb_persons, nb_days, unit_price in spec["items"]:
                item = InvoiceItem(
                    invoice=inv,
                    order=order,
                    description=desc,
                    pricing_mode=mode,
                    nb_persons=nb_persons,
                    nb_days=nb_days,
                    unit_price_ht=unit_price,
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

        self.stdout.write(f"  ✓ {created} factures FORMATION finalisées ({YEAR})")

    # ------------------------------------------------------------------ #
    # Sequence counters
    # ------------------------------------------------------------------ #
    def _update_sequences(self):
        # The sequence was already advanced to 35 by the last _prime_and_get_ref()
        # call during invoice creation. We just report the final state here.
        seq = InvoiceSequence.objects.filter(
            invoice_type=Invoice.InvoiceType.FORMATION,
            year=YEAR,
            phase=InvoiceSequence.Phase.FINALE,
        ).first()
        last = seq.last_number if seq else "?"
        self.stdout.write(
            f"  ✓ InvoiceSequence {YEAR} → dernier n° {last} (géré automatiquement)"
        )
