# financial/management/commands/seed_expenses.py
"""
Load expense entries from a JSON file into the database.

Usage:
  python manage.py seed_expenses                          # loads default file
  python manage.py seed_expenses --file path/to/file.json
  python manage.py seed_expenses --dry-run                # preview only
  python manage.py seed_expenses --file expenses_janvier_2026_batch1.json \
                                 --G50=01-01-2026 \
                                 --upload_from="expenses_01_2026"

  --G50            : First day of the G50 declaration month (DD-MM-YYYY).
                     Sets g50_month on every created Expense and determines
                     the receipts/YYYY/MM/ sub-folder used for scans.
  --upload_from    : Path to a folder containing the scan images referenced
                     by scan_filename in the JSON.  Each file is copied into
                     MEDIA_ROOT/receipts/YYYY/MM/<filename> and the Expense's
                     receipt field is set accordingly.
"""

import json
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

DEFAULT_FILE = (
    Path(__file__).resolve().parent.parent.parent.parent / "expenses_janvier_2026.json"
)


def _parse_g50(raw: str) -> date:
    """Parse DD-MM-YYYY → date object (first day of the G50 month)."""
    try:
        day, month, year = raw.strip().split("-")
        return date(int(year), int(month), int(day))
    except (ValueError, AttributeError):
        raise CommandError(
            f"Invalid --G50 value '{raw}'. Expected format: DD-MM-YYYY (e.g. 01-01-2026)."
        )


class Command(BaseCommand):
    help = "Seed Expense entries from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=str(DEFAULT_FILE),
            help="Path to the JSON file (default: expenses_janvier_2026.json next to manage.py).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Parse and validate without writing to the database.",
        )
        parser.add_argument(
            "--G50",
            dest="g50",
            default=None,
            metavar="DD-MM-YYYY",
            help=(
                "First day of the G50 declaration month (DD-MM-YYYY). "
                "Sets g50_month on every Expense and determines the "
                "receipts/YYYY/MM/ upload sub-folder."
            ),
        )
        parser.add_argument(
            "--upload_from",
            dest="upload_from",
            default=None,
            metavar="PATH",
            help=(
                "Path to the folder containing the scan images listed in "
                "scan_filename. Files are copied into "
                "MEDIA_ROOT/receipts/YYYY/MM/<filename> (derived from --G50)."
            ),
        )

    def handle(self, *args, **options):
        from django.conf import settings

        from financial.models import Expense, ExpenseCategory

        # ── Parse --G50 ────────────────────────────────────────────────
        g50_date: date | None = None
        receipt_subdir: str | None = None  # e.g. "receipts/2026/01"
        media_receipt_dir: Path | None = None  # absolute path inside MEDIA_ROOT

        if options["g50"]:
            g50_date = _parse_g50(options["g50"])
            receipt_subdir = f"receipts/{g50_date.year}/{g50_date.month:02d}"
            media_root = Path(getattr(settings, "MEDIA_ROOT", "media"))
            media_receipt_dir = media_root / receipt_subdir
            self.stdout.write(
                f"  G50 month : {g50_date}  →  media sub-folder: {receipt_subdir}"
            )

        # ── Resolve --upload_from ──────────────────────────────────────
        upload_src: Path | None = None
        if options["upload_from"]:
            upload_src = Path(options["upload_from"])
            if not upload_src.is_dir():
                raise CommandError(
                    f"--upload_from path does not exist or is not a directory: {upload_src}"
                )
            if media_receipt_dir is None:
                raise CommandError(
                    "--upload_from requires --G50 to be set so the destination "
                    "sub-folder can be determined."
                )
            self.stdout.write(f"  Scan source : {upload_src}")
            self.stdout.write(f"  Scan dest   : {media_receipt_dir}")

        # ── Load JSON ──────────────────────────────────────────────────
        filepath = Path(options["file"])
        if not filepath.exists():
            raise CommandError(f"File not found: {filepath}")

        with filepath.open(encoding="utf-8") as f:
            entries = json.load(f)

        dry = options["dry_run"]
        created = skipped = flagged = 0

        # ── Ensure destination folder exists (skip in dry-run) ─────────
        if not dry and media_receipt_dir is not None:
            media_receipt_dir.mkdir(parents=True, exist_ok=True)

        for i, row in enumerate(entries, 1):
            # ── Resolve category ────────────────────────────────────────
            cat_name = row.get("category", "Divers")
            try:
                category = ExpenseCategory.objects.get(name=cat_name)
            except ExpenseCategory.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(
                        f"  [{i}] Category '{cat_name}' not found — skipped."
                    )
                )
                skipped += 1
                continue

            # ── Parse date ──────────────────────────────────────────────
            raw_date = row.get("date")
            entry_date = date.fromisoformat(raw_date) if raw_date else None

            raw_amount = row.get("amount")
            needs_review = (
                row.get("needs_review", False)
                or entry_date is None
                or raw_amount is None
            )

            # ── Resolve receipt file path ────────────────────────────────
            scan_filename: str | None = row.get("scan_filename")
            receipt_relative: str = (
                ""  # stored in Expense.receipt (relative to MEDIA_ROOT)
            )

            if scan_filename and receipt_subdir:
                receipt_relative = f"{receipt_subdir}/{scan_filename}"

            # ── Preview line ────────────────────────────────────────────
            label = row.get("description") or row.get("vendor_name") or "—"
            amount_display = (
                f"{raw_amount:>12,.2f}" if raw_amount is not None else "        N/A "
            )
            receipt_tag = f"📎 {scan_filename}" if scan_filename else "  (no scan)"
            self.stdout.write(
                f"  [{i:>2}] {'[DRY] ' if dry else ''}"
                f"{str(entry_date):10}  {amount_display} DZD  "
                f"{'⚠ ' if needs_review else '  '}"
                f"{cat_name[:28]}  —  {label[:45]}  {receipt_tag}"
            )

            if dry:
                continue

            # ── Copy scan file into MEDIA_ROOT ───────────────────────────
            if scan_filename and upload_src and media_receipt_dir:
                src_file = upload_src / scan_filename
                dst_file = media_receipt_dir / scan_filename
                if src_file.exists():
                    if not dst_file.exists():
                        shutil.copy2(src_file, dst_file)
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"       ↳ copied {scan_filename} → {dst_file}"
                            )
                        )
                    else:
                        self.stdout.write(
                            f"       ↳ {scan_filename} already exists at destination — skipped copy."
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"       ↳ scan not found in source folder: {src_file}"
                        )
                    )
                    receipt_relative = ""  # don't store a broken path

            # ── Map old JSON fields → Expense v4.0 fields ──────────────
            #
            # vendor_name / beneficiary_name → supplier (free-text fallback)
            # invoice_number                 → payment_reference
            # amount_ht                      → gross_amount (pre-tax amount;
            #                                  IRG will be 0 for these entries)
            # needs_review / missing date    → approval_status = PENDING
            # scan_filename absent           → receipt_missing = True
            # vendor_nif, payment_method,
            #   tva_rate                     → folded into notes (no model field)
            # (no session/project context)   → is_overhead = True
            # g50_date (from --G50)          → g50_month

            supplier = row.get("vendor_name") or row.get("beneficiary_name") or ""

            # Build notes from fields that have no direct column
            note_parts = []
            if row.get("vendor_nif"):
                note_parts.append(f"NIF fournisseur : {row['vendor_nif']}")
            if row.get("payment_method"):
                note_parts.append(f"Mode de paiement : {row['payment_method']}")
            if row.get("tva_rate") is not None:
                note_parts.append(f"TVA : {row['tva_rate']}%")
            if row.get("scan_filename"):
                note_parts.append(f"Scan : {row['scan_filename']}")

            kwargs = dict(
                date=entry_date or date.today(),
                amount=(
                    Decimal(str(raw_amount)) if raw_amount is not None else Decimal("0")
                ),
                category=category,
                description=row.get("description") or "",
                supplier=supplier,
                payment_reference=row.get("invoice_number") or "",
                is_overhead=True,
                approval_status=Expense.ApprovalStatus.PENDING,
                receipt_missing=not bool(receipt_relative),
                notes="\n".join(note_parts),
                # G50 declaration month — None when --G50 is not supplied
                g50_month=g50_date,
            )

            # gross_amount: use amount_ht when present; model save() will set
            # irg_amount=0 and confirm amount = gross_amount (no IRG on these entries)
            if row.get("amount_ht") is not None:
                kwargs["gross_amount"] = Decimal(str(row["amount_ht"]))

            expense = Expense.objects.create(**kwargs)

            # Assign receipt path directly (bypasses re-upload, sets DB field only)
            if receipt_relative:
                Expense.objects.filter(pk=expense.pk).update(receipt=receipt_relative)

            created += 1
            if needs_review:
                flagged += 1

        # ── Summary ─────────────────────────────────────────────────────
        if dry:
            self.stdout.write(
                self.style.WARNING(
                    f"\n[Dry run] {len(entries)} entries parsed — nothing written."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✓ {created} created, {skipped} skipped, {flagged} flagged for review."
                )
            )
            if g50_date:
                self.stdout.write(
                    f"  G50 month set to {g50_date} on all {created} expense(s)."
                )
            if upload_src and media_receipt_dir:
                self.stdout.write(f"  Scans stored under: {media_receipt_dir}")
