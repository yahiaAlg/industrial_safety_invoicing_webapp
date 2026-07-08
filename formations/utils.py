# =============================================================================
# formations/utils.py  —  Participant import, attestation bulk issue
# =============================================================================

import csv
import io
from decimal import Decimal

from django.db import transaction


def parse_participant_csv(file_obj):
    """
    Parse a CSV file and return a list of dicts ready for Participant creation.
    Expected columns (case-insensitive): Prénom, Nom, Employeur, Email, Téléphone, Fonction.
    Returns (rows: list[dict], errors: list[str]).
    """
    FIELD_MAP = {
        "prénom": "first_name",
        "prenom": "first_name",
        "nom": "last_name",
        "employeur": "employer",
        "email": "email",
        "téléphone": "phone",
        "telephone": "phone",
        "fonction": "job_title",
    }

    try:
        text = file_obj.read().decode("utf-8-sig")
    except UnicodeDecodeError:
        file_obj.seek(0)
        text = file_obj.read().decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    rows, errors = [], []

    for i, raw_row in enumerate(reader, start=2):  # row 1 = header
        row = {
            FIELD_MAP.get(k.strip().lower(), k.strip().lower()): v.strip()
            for k, v in raw_row.items()
        }
        if not row.get("first_name") and not row.get("last_name"):
            errors.append(f"Ligne {i} : prénom et nom manquants — ignorée.")
            continue
        rows.append(row)

    return rows, errors


def parse_participant_excel(file_obj):
    """
    Parse an Excel (.xlsx/.xls) file into the same dict format as parse_participant_csv.
    Requires openpyxl (already a Django dependency via django-import-export).
    """
    try:
        import openpyxl
    except ImportError:
        return [], ["openpyxl non disponible — utilisez le format CSV."]

    FIELD_MAP = {
        "prénom": "first_name",
        "prenom": "first_name",
        "nom": "last_name",
        "employeur": "employer",
        "email": "email",
        "téléphone": "phone",
        "telephone": "phone",
        "fonction": "job_title",
    }

    try:
        wb = openpyxl.load_workbook(file_obj, read_only=True, data_only=True)
        ws = wb.active
        rows_iter = iter(ws.iter_rows(values_only=True))
        header = [str(c).strip().lower() if c else "" for c in next(rows_iter)]
        mapped_header = [FIELD_MAP.get(h, h) for h in header]
    except Exception as exc:
        return [], [f"Impossible de lire le fichier Excel : {exc}"]

    rows, errors = [], []
    for i, raw_row in enumerate(rows_iter, start=2):
        row = {
            mapped_header[j]: (str(v).strip() if v is not None else "")
            for j, v in enumerate(raw_row)
        }
        if not row.get("first_name") and not row.get("last_name"):
            errors.append(f"Ligne {i} : prénom et nom manquants — ignorée.")
            continue
        rows.append(row)

    return rows, errors


@transaction.atomic
def bulk_enroll_participants(session, rows):
    """
    Create Participant objects from a list of dicts (parsed from import).
    Skips duplicates (same session + name + email).
    Returns (created_count, skipped_count, errors).
    """
    from formations.models import Participant

    created, skipped, errors = 0, 0, []

    for row in rows:
        if session.is_full:
            errors.append("Session complète — inscriptions interrompues.")
            break
        try:
            _, was_created = Participant.objects.get_or_create(
                session=session,
                first_name=row.get("first_name", ""),
                last_name=row.get("last_name", ""),
                email=row.get("email", ""),
                defaults={
                    "employer": row.get("employer", ""),
                    "phone": row.get("phone", ""),
                    "job_title": row.get("job_title", ""),
                    "attended": True,
                },
            )
            if was_created:
                created += 1
            else:
                skipped += 1
        except Exception as exc:
            errors.append(f"{row.get('first_name')} {row.get('last_name')}: {exc}")

    return created, skipped, errors


@transaction.atomic
def issue_attestations_bulk(session, participant_ids, issue_date):
    """
    Issue attestations for a list of participant PKs in a completed session.
    Returns (issued_count, skipped_already_issued).
    """
    from formations.models import Attestation, Participant

    issued, skipped = 0, 0
    participants = Participant.objects.filter(
        pk__in=participant_ids, session=session, attended=True
    )

    for participant in participants:
        if participant.has_attestation:
            skipped += 1
            continue
        Attestation.objects.create(
            participant=participant,
            session=session,
            issue_date=issue_date,
        )
        issued += 1

    return issued, skipped


# ── Column-sort helper (used by sortable list-view <th> headers) ────────── #


def apply_sorting(qs, request, field_map, default):
    """
    Apply a whitelisted ?sort=<key>&dir=asc|desc from the request to a queryset.

    field_map: {url_key: orm_field_path} — only keys present here are honored,
    so arbitrary/unknown fields can never reach order_by().
    default: fallback ordering (e.g. "title") used when 'sort' is absent or
             not in field_map.

    Same helper as financial.utils.apply_sorting — kept as a local copy so
    formations doesn't depend on the financial app.
    """
    sort_key = request.GET.get("sort")
    direction = request.GET.get("dir", "asc")
    if sort_key and sort_key in field_map:
        order_field = field_map[sort_key]
        if direction == "desc":
            order_field = f"-{order_field}"
        return qs.order_by(order_field)
    default_fields = [default] if isinstance(default, str) else list(default)
    return qs.order_by(*default_fields)
