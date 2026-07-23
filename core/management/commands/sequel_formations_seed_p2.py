# core/management/commands/sequel_formations_seed_p2.py
"""
Sequel seed — Part 2: mixed-industry invoices (2026)

Loads:
  • 9 new Clients
  • Formations (reuses HSE category where applicable, adds 1 new
    FormationCategory : Industrie & Métallurgie (MET))
  • 9 finalised FORMATION invoices for year 2026 (027–035)

Source invoices:
  - FACTURE_027 / 12-05-2026 → EURL ALPHAS SERVICES
  - FACTURE_028 / 14-05-2026 → SARL GROUPE RIADH EL-FETH
  - FACTURE_029 / 14-05-2026 → SARL EIMI TRANSFO
  - FACTURE_030 / 20-05-2026 → EURL PRO TAM STEEL
  - FACTURE_031 / 21-05-2026 → EURL BAIT EL OUTOUR EL ALAMIA
  - FACTURE_032 / 31-05-2026 → SARL INSPECTA INTERNATIONAL ALGERIA
  - FACTURE_033 / 31-05-2026 → SARL MOF VET
  - FACTURE_034 / 13-06-2026 → HALLIBURTON ENERGY SERVICES (Overhead Crane)
  - FACTURE_035 / 25-06-2026 → HALLIBURTON ENERGY SERVICES (Advanced Excel)

Run:
    python manage.py sequel_formations_seed_p2
    python manage.py sequel_formations_seed_p2 --clear
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

CLIENT_NAMES = [
    "EURL ALPHAS SERVICES",
    "SARL GROUPE RIADH EL-FETH",
    "SARL EIMI TRANSFO",
    "EURL PRO TAM STEEL",
    "EURL BAIT EL OUTOUR EL ALAMIA",
    "SARL INSPECTA INTERNATIONAL ALGERIA",
    "SARL MOF VET",
    "HALLIBURTON ENERGY SERVICES INC ALGERIA DIVISION",
]


class Command(BaseCommand):
    help = "Sequel seed P2 — mixed-industry invoices (2026)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete these clients and their invoices before re-seeding.",
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
            self.style.SUCCESS("\n✓ Sequel seed P2 terminé avec succès.\n")
        )

    # ------------------------------------------------------------------ #
    # Clear
    # ------------------------------------------------------------------ #
    def _clear_data(self):
        client_qs = Client.objects.filter(name__in=CLIENT_NAMES)
        InvoiceItem.objects.filter(invoice__client__in=client_qs).delete()
        Invoice.objects.filter(client__in=client_qs).delete()
        client_qs.delete()
        self.stdout.write("  ✓ Données P2 supprimées.")

    # ------------------------------------------------------------------ #
    # Formation catalog — reuse HSE, add MET category
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

        # (title, category, duration_days, duration_hours, base_price)
        formations = [
            ("Formation Certifiant ISM-ATEX 2 E-M", cat_hse, 4, 32, Decimal("130000.00")),
            ("Gestion de Conflits", cat_hse, 6, 48, Decimal("80000.00")),
            ("Habilitation Électrique", cat_hse, 4, 32, Decimal("45000.00")),
            ("Superviseur HSE + IOSH MS", cat_hse, 1, 8, Decimal("60000.00")),
            (
                "Habilitation Conduite des Chariots Élévateurs",
                cat_met,
                1,
                8,
                Decimal("22000.00"),
            ),
            ("Formation de conduite de pont roulant", cat_hse, 5, 40, Decimal("80000.00")),
            ("Excel et Word Avancés", cat_hse, 3, 24, Decimal("60000.00")),
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
            f"  ✓ Catégorie MET + HSE — {created} formations créées, "
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
                "alphas_services",
                dict(
                    name="EURL ALPHAS SERVICES",
                    client_type=E,
                    forme_juridique=fj_eurl,
                    address="Cité 2038 Logts, Bt 35, Bab Ezzouar, Alger",
                    city="Alger",
                    activity_sector="Maintenance et Montage des Pompes Hydrauliques",
                    rc="22B1050983-00/16",
                    nif="002216105098376",
                    nis="002216210218558",
                    article_imposition="061014515192",
                ),
            ),
            (
                "riadh_el_feth",
                dict(
                    name="SARL GROUPE RIADH EL-FETH",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="BD Beggag Bouzid Cité Financière Sétif",
                    city="Sétif",
                    activity_sector="Fabrication de Câbles Électriques et Téléphoniques",
                    rc="97 B 0082016-00/19",
                    nif="09971900820164600000",
                    nis="099719010778514",
                    article_imposition="",
                ),
            ),
            (
                "eimi_transfo",
                dict(
                    name="SARL EIMI TRANSFO",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="Ain Mousse n°764 Bâtiment F03, Sétif",
                    city="Sétif",
                    activity_sector="Maintenance des Transformateurs",
                    rc="24 B 0096096-00/19",
                    nif="002419009609655",
                    nis="002419010105563",
                    article_imposition="19010317643",
                ),
            ),
            (
                "pro_tam_steel",
                dict(
                    name="EURL PRO TAM STEEL",
                    client_type=E,
                    forme_juridique=fj_eurl,
                    address="Parc Industriel Section 09 Groupe 243 Lots N°66, Ouled Sabor, Sétif",
                    city="Sétif",
                    activity_sector="Transformation et Fabrication des Métaux Ferreux et Non Ferreux",
                    rc="22 B 0095041-00/19",
                    nif="00221900950414019001",
                    nis="002219010072555",
                    article_imposition="19470020852",
                ),
            ),
            (
                "bait_el_outour",
                dict(
                    name="EURL BAIT EL OUTOUR EL ALAMIA",
                    client_type=E,
                    forme_juridique=fj_eurl,
                    address="Cité Kaabob Coop Belle Vue Section 07 Grp 911 RDC Sétif",
                    city="Sétif",
                    activity_sector="Fabrication de Produits",
                    rc="16 B 0092089-00/19",
                    nif="001619009208992",
                    nis="001619010011762",
                    article_imposition="19018604901",
                ),
            ),
            (
                "inspecta_international",
                dict(
                    name="SARL INSPECTA INTERNATIONAL ALGERIA",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="N°83 B, 1ère Étage BAT A, Arzew, Oran",
                    city="Oran",
                    activity_sector="Asset Integrity Management & Well Services",
                    rc="22 B1017586-31/00",
                    nif="002216101758634",
                    nis="002216520019258",
                    article_imposition="31061445031",
                ),
            ),
            (
                "mof_vet",
                dict(
                    name="SARL MOF VET",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="63 Lots N°12 Ain Azel 19007, Wilaya de Sétif",
                    city="Ain Azel",
                    activity_sector="Fabrication de Produits pour l'Alimentation des Animaux",
                    rc="08B0087148-06/19",
                    nif="00081900871483119006",
                    nis="",
                    article_imposition="19402981055",
                ),
            ),
            (
                "halliburton",
                dict(
                    name="HALLIBURTON ENERGY SERVICES INC ALGERIA DIVISION",
                    client_type=E,
                    forme_juridique=fj_sarl,
                    address="Résidence Noor 10 Rue Yahia Ben Hayet, Hydra, Alger",
                    city="Alger",
                    activity_sector="Service Pétrolier",
                    rc="02/2023",
                    nif="308029000015471",
                    nis="099916451138515",
                    article_imposition="16450140481",
                ),
            ),
        ]

        clients = {}
        for key, defaults in specs:
            client, _ = Client.objects.get_or_create(
                name=defaults["name"], defaults=defaults
            )
            clients[key] = client

        self.stdout.write(f"  ✓ {len(clients)} clients P2")
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
            # ── 027 / EURL ALPHAS SERVICES — Certifiant ISM-ATEX ───────
            dict(
                target_number=27,
                date=datetime.date(2026, 5, 12),
                client=C["alphas_services"],
                bc="",
                mode="Chèque",
                amount_ht=D("520000.00"),
                amount_tva=D("46800.00"),
                amount_ttc=D("566800.00"),
                items=[
                    (
                        1,
                        "Formation Certifiant ISM-ATEX (2 E-M, 01 P, 04 P)",
                        PP,
                        D("4"),
                        D("1"),
                        D("130000.00"),
                    ),
                ],
            ),
            # ── 028 / RIADH EL-FETH — Gestion de Conflit ────────────────
            dict(
                target_number=28,
                date=datetime.date(2026, 5, 14),
                client=C["riadh_el_feth"],
                bc="",
                mode="Chèque ou virement",
                amount_ht=D("742800.00"),
                amount_tva=D("66852.00"),
                amount_ttc=D("809852.00"),
                items=[
                    (
                        1,
                        "Formation Gestion de Conflit",
                        PD,
                        D("1"),
                        D("6"),
                        D("80000.00"),
                    ),
                    (2, "Frais pédagogique", PD, D("1"), D("6"), D("43800.00")),
                ],
            ),
            # ── 029 / EIMI TRANSFO — Habilitation Électrique ───────────
            dict(
                target_number=29,
                date=datetime.date(2026, 5, 14),
                client=C["eimi_transfo"],
                bc="PO2605-0023",
                mode="Chèque ou virement",
                amount_ht=D("180000.00"),
                amount_tva=D("16200.00"),
                amount_ttc=D("196200.00"),
                items=[
                    (
                        1,
                        "Formation Habilitation Électrique",
                        PP,
                        D("4"),
                        D("1"),
                        D("45000.00"),
                    ),
                ],
            ),
            # ── 030 / PRO TAM STEEL — Superviseur HSE + IOSH MS ────────
            dict(
                target_number=30,
                date=datetime.date(2026, 5, 20),
                client=C["pro_tam_steel"],
                bc="",
                mode="Chèque ou virement",
                amount_ht=D("60000.00"),
                amount_tva=D("5400.00"),
                amount_ttc=D("65400.00"),
                items=[
                    (
                        1,
                        "Formation Superviseur HSE + IOSH MS",
                        FF,
                        D("1"),
                        D("1"),
                        D("60000.00"),
                    ),
                ],
            ),
            # ── 031 / BAIT EL OUTOUR — IOSH MS + Superviseurs HSE ──────
            dict(
                target_number=31,
                date=datetime.date(2026, 5, 21),
                client=C["bait_el_outour"],
                bc="",
                mode="",
                amount_ht=D("130000.00"),
                amount_tva=D("11700.00"),
                amount_ttc=D("141700.00"),
                items=[
                    (
                        1,
                        "Formation IOSH MS + Superviseurs HSE (02 candidats)",
                        PD,
                        D("1"),
                        D("5"),
                        D("26000.00"),
                    ),
                ],
            ),
            # ── 032 / INSPECTA INTERNATIONAL — Habilitation Électrique ─
            dict(
                target_number=32,
                date=datetime.date(2026, 5, 31),
                client=C["inspecta_international"],
                bc="021-2026",
                mode="",
                amount_ht=D("150000.00"),
                amount_tva=D("13500.00"),
                amount_ttc=D("163500.00"),
                items=[
                    (
                        1,
                        "Formation Habilitation Électrique",
                        PD,
                        D("1"),
                        D("3"),
                        D("50000.00"),
                    ),
                ],
            ),
            # ── 033 / MOF VET — Habilitation Conduite Chariots ─────────
            dict(
                target_number=33,
                date=datetime.date(2026, 5, 31),
                client=C["mof_vet"],
                bc="141/2026 du 24/05/2026",
                mode="",
                amount_ht=D("220000.00"),
                amount_tva=D("19800.00"),
                amount_ttc=D("239800.00"),
                items=[
                    (
                        1,
                        "Formation Habilitation de Conduite des Chariots Élévateurs",
                        PP,
                        D("10"),
                        D("1"),
                        D("22000.00"),
                    ),
                ],
            ),
            # ── 034 / HALLIBURTON — Overhead Crane Training ────────────
            dict(
                target_number=34,
                date=datetime.date(2026, 6, 13),
                client=C["halliburton"],
                bc="4201892143 DU: 18/01/2026",
                mode="",
                amount_ht=D("400000.00"),
                amount_tva=D("36000.00"),
                amount_ttc=D("436000.00"),
                items=[
                    (1, "Overhead Crane Training", PD, D("1"), D("5"), D("80000.00")),
                ],
            ),
            # ── 035 / HALLIBURTON — Advanced Excel Training ────────────
            dict(
                target_number=35,
                date=datetime.date(2026, 6, 25),
                client=C["halliburton"],
                bc="4201927994 DU: 07/06/2026",
                mode="",
                amount_ht=D("1118500.00"),
                amount_tva=D("100665.00"),
                amount_ttc=D("1219165.00"),
                items=[
                    (1, "Advanced Excel Training", PD, D("1"), D("3"), D("60000.00")),
                    (
                        2,
                        "Single room for candidates (29)",
                        FF,
                        D("1"),
                        D("1"),
                        D("768000.00"),
                    ),
                    (3, "Coffee break (27)", FF, D("1"), D("1"), D("54000.00")),
                    (
                        4,
                        "Restauration for candidates (29)",
                        FF,
                        D("1"),
                        D("1"),
                        D("116000.00"),
                    ),
                ],
            ),
        ]

        created = 0
        for spec in specs:
            client = spec["client"]

            # Guardrail: skip if this invoice already exists (re-run safe)
            if Invoice.objects.filter(
                client=client,
                bon_commande_number=spec["bc"],
                invoice_date=spec["date"],
            ).exists():
                continue

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
