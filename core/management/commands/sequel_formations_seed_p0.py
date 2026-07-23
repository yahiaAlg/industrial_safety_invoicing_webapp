# core/management/commands/sequel_formations_seed_p0.py
"""
Sequel seed — Part 0: mixed-industry invoices (2026), gap 021–026

Fills the gap between the base seed (invoices 001–020) and sequel P2
(invoices 027–035).

Loads:
  • 4 new Clients (LAMSAT KABIR, SETIF CITERNES, ALPHAS Algérie Pompes
    Hydrauliques Accessoires, NICE PLUS)
  • Reuses existing client: EURL BAIT EL OUTOUR EL ALAMIA (base seed)
  • Formations (reuses HSE / MET / RH categories, adds a few new titles)
  • 6 finalised FORMATION invoices for year 2026 (021–026)

Source invoices:
  - FACTURE_021 / 22-04-2026 → SARL LAMSAT KABIR
  - FACTURE_022 / 27-04-2026 → EURL BAIT EL OUTOUR EL ALAMIA (ATEX + HSE)
  - FACTURE_023 / 28-04-2026 → EURL BAIT EL OUTOUR EL ALAMIA (Chariots)
  - FACTURE_024 / 07-05-2026 → SARL SETIF CITERNES
  - FACTURE_025 / 10-05-2026 → SARL ALPHAS PRODUCTION
  - FACTURE_026 / 10-05-2026 → SARL NICE PLUS

Run:
    python manage.py sequel_formations_seed_p0
    python manage.py sequel_formations_seed_p0 --clear
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
YEAR = 2026

NEW_CLIENT_NAMES = [
    "SARL LAMSAT KABIR",
    "SARL SETIF CITERNES",
    "SARL ALPHAS Algérie Pompes Hydrauliques Accessoires",
    "SARL NICE PLUS",
]


class Command(BaseCommand):
    help = "Sequel seed P0 — mixed-industry invoices (2026), gap 021–026."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete the P0 invoices (and any newly-created clients) before re-seeding.",
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
            self.style.SUCCESS("\n✓ Sequel seed P0 terminé avec succès.\n")
        )

    # ------------------------------------------------------------------ #
    # Clear
    # ------------------------------------------------------------------ #
    def _clear_data(self):
        # Invoices 021-026 identified by client + date range (safe even
        # though bait_el_outour is a reused client with other invoices).
        target_dates = [
            datetime.date(2026, 4, 22),
            datetime.date(2026, 4, 27),
            datetime.date(2026, 4, 28),
            datetime.date(2026, 5, 7),
            datetime.date(2026, 5, 10),
        ]
        inv_qs = Invoice.objects.filter(
            invoice_type=Invoice.InvoiceType.FORMATION,
            invoice_date__in=target_dates,
            client__name__in=NEW_CLIENT_NAMES + ["EURL BAIT EL OUTOUR EL ALAMIA"],
        )
        InvoiceItem.objects.filter(invoice__in=inv_qs).delete()
        inv_qs.delete()
        Client.objects.filter(name__in=NEW_CLIENT_NAMES).delete()
        self.stdout.write("  ✓ Données P0 supprimées.")

    # ------------------------------------------------------------------ #
    # Formation catalog — reuse HSE / MET / RH, add new titles
    # ------------------------------------------------------------------ #
    def _seed_formation_catalog(self):
        from django.utils.text import slugify

        cat_hse, _ = FormationCategory.objects.get_or_create(
            code="HSE", defaults={"name": "Formation HSE", "color": "#EF4444"}
        )
        cat_met, _ = FormationCategory.objects.get_or_create(
            code="MET",
            defaults={"name": "Industrie & Métallurgie", "color": "#78716C"},
        )
        cat_rh, _ = FormationCategory.objects.get_or_create(
            code="RH",
            defaults={"name": "Management des Ressources Humaines", "color": "#6366F1"},
        )

        # (title, category, duration_days, duration_hours, base_price)
        formations = [
            (
                "Formation de Qualification de Conduite de Transport Personnel",
                cat_hse,
                1,
                8,
                Decimal("32000.00"),
            ),
            ("Formation ATEX, Non Certifiant", cat_hse, 2, 16, Decimal("80000.00")),
            (
                "Formation Animateur / Superviseur HSE",
                cat_hse,
                5,
                40,
                Decimal("10000.00"),
            ),
            (
                "Formation de Conduite en Sécurité des Chariots Élévateurs",
                cat_met,
                8,
                64,
                Decimal("18000.00"),
            ),
            ("Formation Sûreté Interne", cat_hse, 3, 24, Decimal("50000.00")),
            (
                "Formation de Conduite de Pont Roulant",
                cat_met,
                2,
                16,
                Decimal("45000.00"),
            ),
            ("Audit SST", cat_hse, 1, 8, Decimal("55000.00")),
            (
                "Formation Non-Certifiant ISM-ATEX",
                cat_hse,
                2,
                16,
                Decimal("120000.00"),
            ),
            (
                "Formation Certifiant ISM-ATEX 2 E-M",
                cat_hse,
                5,
                40,
                Decimal("130000.00"),
            ),
            ("Formation Gestion de Personnel", cat_rh, 3, 24, Decimal("40000.00")),
            (
                "Formation Gestion des Compétences",
                cat_rh,
                2,
                16,
                Decimal("35000.00"),
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
            f"  ✓ Catégories HSE / MET / RH — {created} formations créées, "
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
        fj_eurl, _ = FormeJuridique.objects.get_or_create(
            name="EURL",
            defaults={
                "description": "Entreprise Unipersonnelle à Responsabilité Limitée"
            },
        )
        E = Client.ClientType.ENTREPRISE

        specs = [
            (
                "lamsat_kabir",
                dict(
                    name="SARL LAMSAT KABIR",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="Khalfoune Sec 08 Gr 57, Sétif",
                    city="Sétif",
                    activity_sector="Transformation de Produits Alimentaires",
                    rc="24B0095792-19/01",
                    nif="002419009579287",
                    nis="002419330047252",
                    article_imposition="19338553041",
                ),
            ),
            (
                "setif_citernes",
                dict(
                    name="SARL SETIF CITERNES",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="Zone d'Activité 2ème Tranche N°17, Sétif",
                    city="Sétif",
                    activity_sector="Fabrication d'Articles en Plastique",
                    rc="17B0092770-00/19",
                    nif="001719009277061",
                    nis="001719010032364",
                    article_imposition="19018054081",
                ),
            ),
            (
                "alphas_production",
                dict(
                    name="SARL ALPHAS Algérie Pompes Hydrauliques Accessoires",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="Cité 112 Logts, Quartier Seghir Bt 04 Bp 488, Liberté, Béjaïa",
                    city="Béjaïa",
                    activity_sector="Production de Pompes Hydrauliques et Accessoires",
                    rc="98B0182572-00/06",
                    nif="099806018257209",
                    nis="099606010302544",
                    article_imposition="061014515192",
                ),
            ),
            (
                "nice_plus",
                dict(
                    name="SARL NICE PLUS",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="Zone Industrielle Salah Bey, Sétif",
                    city="Sétif",
                    activity_sector="Fabrication de Détergents",
                    rc="13B0090718-00/19",
                    nif="001319009071883",
                    nis="001319390048738",
                    article_imposition="19390513429",
                ),
            ),
            (
                # Reuse the client created in the base seed (invoice 017)
                "bait_el_outour",
                dict(
                    name="EURL BAIT EL OUTOUR EL ALAMIA",
                    client_type=E,
                    forme_juridique=fj_eurl,
                    address="Cité Kaaboub Coop Belle Vue Section 07 Groupe 911 Rdc",
                    city="Sétif",
                    activity_sector="Fabrication Des Produits Cosmétiques et d'hygiène Corporelle",
                    rc="16B0092089-00/19",
                    nif="001619009208992",
                    nis="001619010011762",
                    article_imposition="19018604901",
                ),
            ),
        ]

        clients = {}
        for key, defaults in specs:
            client, _ = Client.objects.get_or_create(
                name=defaults["name"], defaults=defaults
            )
            clients[key] = client

        self.stdout.write(f"  ✓ {len(clients)} clients référencés (4 nouveaux + 1 réutilisé)")
        return clients

    # ------------------------------------------------------------------ #
    # Invoices
    # ------------------------------------------------------------------ #
    def _seed_invoices(self, C: dict):
        PP = InvoiceItem.PricingMode.PER_PERSON
        PD = InvoiceItem.PricingMode.PER_DAY
        FF = InvoiceItem.PricingMode.FORFAIT
        D = Decimal

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
            # ── 021 / LAMSAT KABIR — Qualification conduite transport ──
            dict(
                target_number=21,
                date=datetime.date(2026, 4, 22),
                client=C["lamsat_kabir"],
                bc="",
                mode="",
                amount_ht=D("32000.00"),
                amount_tva=D("2880.00"),
                amount_ttc=D("34880.00"),
                items=[
                    (
                        1,
                        "Formation de Qualification de Conduite de Transport Personnel",
                        PP,
                        D("1"),
                        D("1"),
                        D("32000.00"),
                    ),
                ],
            ),
            # ── 022 / BAIT EL OUTOUR — ATEX + Superviseur HSE ──────────
            dict(
                target_number=22,
                date=datetime.date(2026, 4, 27),
                client=C["bait_el_outour"],
                bc="0029/2026",
                mode="",
                amount_ht=D("210000.00"),
                amount_tva=D("18900.00"),
                amount_ttc=D("228900.00"),
                items=[
                    (
                        1,
                        "Formation ATEX, Non Certifiant",
                        PD,
                        D("1"),
                        D("2"),
                        D("80000.00"),
                    ),
                    (
                        2,
                        "Formation Animateur / Superviseur HSE (01 personne)",
                        PD,
                        D("1"),
                        D("5"),
                        D("10000.00"),
                    ),
                ],
            ),
            # ── 023 / BAIT EL OUTOUR — Chariots élévateurs ─────────────
            dict(
                target_number=23,
                date=datetime.date(2026, 4, 28),
                client=C["bait_el_outour"],
                bc="0023/2026",
                mode="",
                amount_ht=D("144000.00"),
                amount_tva=D("12960.00"),
                amount_ttc=D("156960.00"),
                items=[
                    (
                        1,
                        "Formation de Conduite en Sécurité des Chariots Élévateurs",
                        PP,
                        D("8"),
                        D("8"),
                        D("18000.00"),
                    ),
                ],
            ),
            # ── 024 / SETIF CITERNES — Sûreté interne + Pont roulant ───
            dict(
                target_number=24,
                date=datetime.date(2026, 5, 7),
                client=C["setif_citernes"],
                bc="",
                mode="",
                amount_ht=D("240000.00"),
                amount_tva=D("21600.00"),
                amount_ttc=D("261600.00"),
                items=[
                    (
                        1,
                        "Formation Sûreté Interne",
                        PD,
                        D("1"),
                        D("3"),
                        D("50000.00"),
                    ),
                    (
                        2,
                        "Formation de Conduite de Pont Roulant",
                        PD,
                        D("1"),
                        D("2"),
                        D("45000.00"),
                    ),
                ],
            ),
            # ── 025 / ALPHAS PRODUCTION — Audit SST + ISM-ATEX ─────────
            dict(
                target_number=25,
                date=datetime.date(2026, 5, 10),
                client=C["alphas_production"],
                bc="",
                mode="Chèque",
                amount_ht=D("945000.00"),
                amount_tva=D("85050.00"),
                amount_ttc=D("1030050.00"),
                items=[
                    (1, "Audit SST (01 site)", FF, D("1"), D("1"), D("55000.00")),
                    (
                        2,
                        "Formation Non-Certifiant ISM-ATEX",
                        PD,
                        D("1"),
                        D("2"),
                        D("120000.00"),
                    ),
                    (
                        3,
                        "Formation Certifiant ISM-ATEX 2 E-M (05 personnes)",
                        PP,
                        D("5"),
                        D("1"),
                        D("130000.00"),
                    ),
                ],
            ),
            # ── 026 / NICE PLUS — Gestion Personnel + Compétences ──────
            dict(
                target_number=26,
                date=datetime.date(2026, 5, 10),
                client=C["nice_plus"],
                bc="",
                mode="",
                amount_ht=D("190000.00"),
                amount_tva=D("17100.00"),
                amount_ttc=D("207100.00"),
                items=[
                    (
                        1,
                        "Formation Gestion de Personnel",
                        PD,
                        D("1"),
                        D("3"),
                        D("40000.00"),
                    ),
                    (
                        2,
                        "Formation Gestion des Compétences",
                        PD,
                        D("1"),
                        D("2"),
                        D("35000.00"),
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
        seq = InvoiceSequence.objects.filter(
            invoice_type=Invoice.InvoiceType.FORMATION,
            year=YEAR,
            phase=InvoiceSequence.Phase.FINALE,
        ).first()
        last = seq.last_number if seq else "?"
        self.stdout.write(
            f"  ✓ InvoiceSequence {YEAR} → dernier n° {last} (géré automatiquement)"
        )
