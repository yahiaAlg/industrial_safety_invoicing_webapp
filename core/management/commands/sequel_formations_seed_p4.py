# core/management/commands/sequel_formations_seed_p4.py
"""
Sequel seed — Part 4: remaining 2025/2026 invoices (small industry clients)

Loads:
  • 8 new Clients (Zouaoui, Satarex, Baraka Food Investissement/One/Two,
    Beliedelice, Bioreal Pharm Eleulma)
  • Reuses existing client: SARL ALGERIA HAM MOTORS (P3)
  • Formations (ISO 9001, ISO 45001, produits chimiques, HACCP, leadership
    HSE, habilitation chariots, leadership managérial, RH/trésorerie/
    sécurité/conflits)
  • 9 finalised FORMATION invoices spanning YEAR 2025 (063) and
    YEAR 2026 (041, 042, 043, 044, 045, 046, 047, 048)

Source invoices:
  - FACTURE_041 / 30-06-2026 → EURL SOCIETE ZOUAOUI (ISO 9001 ver 2015)
  - FACTURE_042 / 30-06-2026 → EURL SATEREX (produits chimiques, 3 groupes)
  - FACTURE_043 / 30-06-2026 → SARL EL BARAKA FOOD INVESTISSEMENT (HACCP)
  - FACTURE_044 / 30-06-2026 → SARL EL BARAKA FOOD ONE (Leadership et culture HSE)
  - FACTURE_045 / 30-06-2026 → SARL EL BARAKA FOOD TWO (Habilitation chariots)
  - FACTURE_046 / 30-06-2026 → EURL SOCIETE ZOUAOUI (ISO 45001)
  - FACTURE_047 / 30-06-2026 → SARL BELIEDELICE (Leadership managérial, 2 pers.)
  - FACTURE_048 / 30-06-2026 → SPA BIOREAL PHARM ETS ELEULMA (4 formations)
  - FACTURE_063 / 21-12-2025 → SARL ALGERIA HAM MOTORS (Habilitation chariots)

Run:
    python manage.py sequel_formations_seed_p4
    python manage.py sequel_formations_seed_p4 --clear
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
    "EURL SOCIETE ZOUAOUI",
    "EURL SATEREX",
    "SARL EL BARAKA FOOD INVESTISSEMENT",
    "SARL EL BARAKA FOOD ONE",
    "SARL EL BARAKA FOOD TWO",
    "SARL BELIEDELICE",
    "SPA BIOREAL PHARM ETS ELEULMA",
]


class Command(BaseCommand):
    help = "Sequel seed P4 — remaining 2025/2026 small industry invoices."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete the P4 invoices (and any newly-created clients) before re-seeding.",
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
            self.style.SUCCESS("\n✓ Sequel seed P4 terminé avec succès.\n")
        )

    # ------------------------------------------------------------------ #
    # Clear
    # ------------------------------------------------------------------ #
    def _clear_data(self):
        refs = ["F041/2026", "F042/2026", "F043/2026", "F044/2026",
                "F045/2026", "F046/2026", "F047/2026", "F048/2026",
                "F063/2025"]
        Invoice.objects.filter(reference__in=refs).delete()
        # Only remove clients created solely for this part (not shared ones).
        client_qs = Client.objects.filter(name__in=NEW_CLIENT_NAMES)
        InvoiceItem.objects.filter(invoice__client__in=client_qs).delete()
        Invoice.objects.filter(client__in=client_qs).delete()
        client_qs.delete()
        self.stdout.write("  ✓ Données P4 supprimées.")

    # ------------------------------------------------------------------ #
    # Formation catalog
    # ------------------------------------------------------------------ #
    def _seed_formation_catalog(self):
        from django.utils.text import slugify

        cat_qua, _ = FormationCategory.objects.get_or_create(
            code="QUA", defaults={"name": "Qualité & Normes ISO", "color": "#0EA5E9"}
        )
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
            ("Formation ISO 9001 version 2015", cat_qua, 2, 16, Decimal("65000.00")),
            ("Formation ISO 45001", cat_qua, 2, 16, Decimal("65000.00")),
            ("Formation d'Utilisation des Produits Chimiques", cat_hse, 3, 24, Decimal("250000.00")),
            ("Hazard Analysis Critical Control Point (HACCP)", cat_hse, 3, 24, Decimal("60000.00")),
            ("Leadership et Culture HSE", cat_hse, 5, 40, Decimal("40000.00")),
            ("Habilitation de Conduite des Chariots Élévateurs", cat_met, 2, 16, Decimal("22000.00")),
            ("Formation Leadership Managérial", cat_com, 2, 16, Decimal("80000.00")),
            ("Formation Management RH", cat_com, 5, 40, Decimal("50000.00")),
            ("Formation Gestion de Trésorerie", cat_com, 4, 32, Decimal("55000.00")),
            ("Formation des Agents de Sécurité", cat_hse, 3, 24, Decimal("55000.00")),
            ("Formation Gestion de Conflits", cat_com, 3, 24, Decimal("65000.00")),
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
            f"  ✓ Catalogue P4 — {created} formations créées, "
            f"{len(formations) - created} déjà existantes."
        )

    # ------------------------------------------------------------------ #
    # Clients
    # ------------------------------------------------------------------ #
    def _seed_clients(self):
        fj_eurl, _ = FormeJuridique.objects.get_or_create(
            name="EURL",
            defaults={"description": "Entreprise Unipersonnelle à Responsabilité Limitée"},
        )
        fj_sarl, _ = FormeJuridique.objects.get_or_create(
            name="SARL",
            defaults={"description": "Société à Responsabilité Limitée"},
        )
        fj_spa, _ = FormeJuridique.objects.get_or_create(
            name="SPA",
            defaults={"description": "Société par Actions"},
        )
        E = Client.ClientType.ENTREPRISE

        specs = [
            (
                "zouaoui",
                dict(
                    name="EURL SOCIETE ZOUAOUI",
                    client_type=E,
                    forme_juridique=fj_eurl,
                    address="Section N°23 groupement N°38 EL-Barriaka commune Guedjal, Sétif",
                    city="Sétif",
                    activity_sector="Production Panneaux Sandwichs & Accessoires",
                    rc="05B0086380-19/03",
                    nif="00051900863802819003",
                    nis="",
                    article_imposition="19017832033",
                ),
            ),
            (
                "satarex",
                dict(
                    name="EURL SATEREX",
                    client_type=E,
                    forme_juridique=fj_eurl,
                    address="Zone Industrielle, Extension Lot N°92 (Section 20 Flot 138), Sétif",
                    city="Sétif",
                    activity_sector="Fabrication de Produits Électroniques et Électro-Ménagers",
                    rc="04B0085573-00/19",
                    nif="000419008557395",
                    nis="000419011230367",
                    article_imposition="19018309011",
                ),
            ),
            (
                "baraka_investissement",
                dict(
                    name="SARL EL BARAKA FOOD INVESTISSEMENT",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="Coop Immob Et Salam, Cité Laid Dahoui, Local N°B11 RDC, Sétif",
                    city="Sétif",
                    activity_sector="Production Industrielle de Crème Glacée et Autres Produits Glacés",
                    rc="14B0091043/19-00",
                    nif="001419009104377",
                    nis="",
                    article_imposition="19018702823",
                ),
            ),
            (
                "baraka_one",
                dict(
                    name="SARL EL BARAKA FOOD ONE",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="Coop Immob Et Salam, Cité Laid Dahoui, Local N°B11 RDC, Sétif",
                    city="Sétif",
                    activity_sector="Importation d'Huiles Animales et Végétales et Autres Matières Grasses",
                    rc="21B0094537/19-00",
                    nif="002119009453738",
                    nis="",
                    article_imposition="19338358021",
                ),
            ),
            (
                "baraka_two",
                dict(
                    name="SARL EL BARAKA FOOD TWO",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="Coop Immob Houria Et Salam, Cité Laid Dahoui, Local N°B11 RDC, Sétif",
                    city="Sétif",
                    activity_sector="Importation des Matières Premières et Produits Destinés à l'Industrie Agroalimentaire",
                    rc="21B0094537/19-00",
                    nif="002119009453738",
                    nis="",
                    article_imposition="19338358021",
                ),
            ),
            (
                "beliedelice",
                dict(
                    name="SARL BELIEDELICE",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="Zone Industrielle, Lot 225 Classe 10, Groupements 300-299-290-291, Ouled Saber, Sétif",
                    city="Sétif",
                    activity_sector="Production Agroalimentaire",
                    rc="16B0092119-19/00",
                    nif="001619009211972",
                    nis="001619470015254",
                    article_imposition="19470140326",
                ),
            ),
            (
                "bioreal_pharm",
                dict(
                    name="SPA BIOREAL PHARM ETS ELEULMA",
                    client_type=E,
                    forme_juridique=fj_spa,
                    address="Mechta Bourioune, Partie 04, Groupement de Propriétés N°39, Commune Bazar Sekra, El Eulma, Sétif",
                    city="El Eulma",
                    activity_sector="Vente et Distribution de Produits Pharmaceutiques",
                    rc="99B000959604/19",
                    nif="099916000959666",
                    nis="099516120567227",
                    article_imposition="19310139296",
                ),
            ),
        ]

        clients = {}
        for key, defaults in specs:
            client, _ = Client.objects.get_or_create(
                name=defaults["name"], defaults=defaults
            )
            clients[key] = client

        # Reuse existing client created in P3.
        clients["algeria_ham_motors"] = Client.objects.get(
            name="SARL ALGERIA HAM MOTORS"
        )

        self.stdout.write(f"  ✓ {len(specs)} nouveaux clients + 1 client réutilisé")
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
            # ── 041 / EURL SOCIETE ZOUAOUI — ISO 9001 v2015 (2026) ─────
            dict(
                target_number=41,
                year=2026,
                date=datetime.date(2026, 6, 30),
                client=C["zouaoui"],
                bc="",
                mode="Cheque 1/1",
                amount_ht=D("130000.00"),
                amount_tva=D("11700.00"),
                amount_ttc=D("141700.00"),
                items=[
                    (1, "Formation ISO 9001 version 2015", PD, D("1"), D("2"), D("65000.00"), D("0")),
                ],
            ),
            # ── 042 / EURL SATEREX — Produits Chimiques 3 groupes (2026) ─
            dict(
                target_number=42,
                year=2026,
                date=datetime.date(2026, 6, 30),
                client=C["satarex"],
                bc="U1001260100NMIM03019 DU: 25/06/2026",
                mode="Cheque 1/1",
                amount_ht=D("750000.00"),
                amount_tva=D("67500.00"),
                amount_ttc=D("817500.00"),
                items=[
                    (1, "Formation d'utilisation des produits chimiques (3 groupes)", FF, D("1"), D("1"), D("750000.00"), D("0")),
                ],
            ),
            # ── 043 / BARAKA FOOD INVESTISSEMENT — HACCP (2026) ────────
            dict(
                target_number=43,
                year=2026,
                date=datetime.date(2026, 6, 30),
                client=C["baraka_investissement"],
                bc="12 DU: 22/06/2026",
                mode="",
                amount_ht=D("240000.00"),
                amount_tva=D("21600.00"),
                amount_ttc=D("261600.00"),
                items=[
                    (1, "Hazard Analysis Critical Control Point (HACCP)", PP, D("4"), D("3"), D("60000.00"), D("0")),
                ],
            ),
            # ── 044 / BARAKA FOOD ONE — Leadership et Culture HSE (2026)
            dict(
                target_number=44,
                year=2026,
                date=datetime.date(2026, 6, 30),
                client=C["baraka_one"],
                bc="13 DU: 24/06/2026",
                mode="",
                amount_ht=D("40000.00"),
                amount_tva=D("3600.00"),
                amount_ttc=D("43600.00"),
                items=[
                    (1, "Leadership et culture HSE", PP, D("1"), D("5"), D("40000.00"), D("0")),
                ],
            ),
            # ── 045 / BARAKA FOOD TWO — Habilitation Chariots (2026) ───
            dict(
                target_number=45,
                year=2026,
                date=datetime.date(2026, 6, 30),
                client=C["baraka_two"],
                bc="14 DU: 24/06/2026",
                mode="",
                amount_ht=D("22000.00"),
                amount_tva=D("1980.00"),
                amount_ttc=D("23980.00"),
                items=[
                    (1, "Habilitation de conduite des chariots élévateurs", PP, D("1"), D("2"), D("22000.00"), D("0")),
                ],
            ),
            # ── 046 / EURL SOCIETE ZOUAOUI — ISO 45001 (2026) ──────────
            dict(
                target_number=46,
                year=2026,
                date=datetime.date(2026, 6, 30),
                client=C["zouaoui"],
                bc="",
                mode="Cheque 1/1",
                amount_ht=D("130000.00"),
                amount_tva=D("11700.00"),
                amount_ttc=D("141700.00"),
                items=[
                    (1, "Formation ISO 45001", PD, D("1"), D("2"), D("65000.00"), D("0")),
                ],
            ),
            # ── 047 / SARL BELIEDELICE — Leadership Managérial (2026) ──
            dict(
                target_number=47,
                year=2026,
                date=datetime.date(2026, 6, 30),
                client=C["beliedelice"],
                bc="",
                mode="",
                amount_ht=D("160000.00"),
                amount_tva=D("14400.00"),
                amount_ttc=D("174400.00"),
                items=[
                    (1, "Formation leadership managérial", PP, D("2"), D("2"), D("80000.00"), D("0")),
                ],
            ),
            # ── 048 / SPA BIOREAL PHARM ETS ELEULMA — 4 formations (2026)
            dict(
                target_number=48,
                year=2026,
                date=datetime.date(2026, 6, 30),
                client=C["bioreal_pharm"],
                bc="",
                mode="Cheque 1/1",
                amount_ht=D("630000.00"),
                amount_tva=D("56700.00"),
                amount_ttc=D("686700.00"),
                items=[
                    (1, "Formation management RH", PD, D("1"), D("5"), D("50000.00"), D("0")),
                    (2, "Formation gestion de trésorerie", PD, D("1"), D("4"), D("55000.00"), D("0")),
                    (3, "Formation des agents de sécurité", PD, D("1"), D("3"), D("55000.00"), D("0")),
                    (4, "Formation gestion de conflits", PD, D("1"), D("3"), D("65000.00"), D("0")),
                ],
            ),
            # ── 063 / SARL ALGERIA HAM MOTORS — Habilitation Chariots (2025)
            dict(
                target_number=63,
                year=2025,
                date=datetime.date(2025, 12, 21),
                client=C["algeria_ham_motors"],
                bc="00075/2025",
                mode="",
                amount_ht=D("96000.00"),
                amount_tva=D("8640.00"),
                amount_ttc=D("104640.00"),
                items=[
                    (1, "Formations l'habilitation conduite des chariots élévateurs", PD, D("1"), D("2"), D("48000.00"), D("0")),
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
