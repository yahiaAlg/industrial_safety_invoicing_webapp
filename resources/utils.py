# =============================================================================
# resources/utils.py  —  Equipment analytics helpers
# =============================================================================

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum


def equipment_idle_list(threshold_days=90):
    """Return equipment items that haven't been used within threshold_days."""
    from resources.models import Equipment

    cutoff = date.today() - timedelta(days=threshold_days)
    # Equipment with no usage at all, or last usage older than cutoff
    from django.db.models import Max, Q

    return (
        Equipment.objects.filter(status=Equipment.STATUS_ACTIVE)
        .annotate(last_use=Max("usages__date"))
        .filter(Q(last_use__lt=cutoff) | Q(last_use__isnull=True))
        .order_by("last_use")
    )


def equipment_maintenance_due_list():
    """Return equipment where next_maintenance_due <= today."""
    from resources.models import Equipment

    today = date.today()
    # Annotate with last maintenance date then filter in Python
    # (next_maintenance_due is a @property — cannot filter directly)
    active = Equipment.objects.filter(
        status__in=[Equipment.STATUS_ACTIVE, Equipment.STATUS_RESERVED]
    ).prefetch_related("maintenance_logs")
    return [e for e in active if e.is_maintenance_due]


def booking_conflicts_for_period(date_from, date_to, exclude_booking_pk=None):
    """
    Return a dict {equipment_pk: [conflicting booking PKs]} for the given range.
    Used by the booking form's availability-check JsonResponse endpoint.
    """
    from resources.models import EquipmentBooking

    qs = EquipmentBooking.objects.filter(
        date_from__lte=date_to,
        date_to__gte=date_from,
    )
    if exclude_booking_pk:
        qs = qs.exclude(pk=exclude_booking_pk)

    conflicts = {}
    for booking in qs.select_related("equipment"):
        conflicts.setdefault(booking.equipment_id, []).append(booking.pk)
    return conflicts


def compute_cost_per_use_ranking():
    """
    Return all active equipment sorted by cost_per_use ascending (best ROI first).
    Evaluated in Python since cost_per_use is a model property, not a DB expression.
    """
    from resources.models import Equipment

    items = list(
        Equipment.objects.filter(status=Equipment.STATUS_ACTIVE).prefetch_related(
            "usages", "maintenance_logs"
        )
    )
    return sorted(items, key=lambda e: e.cost_per_use)


# ── Column-sort helper (used by sortable list-view <th> headers) ────────── #


def apply_sorting(qs, request, field_map, default):
    """
    Apply a whitelisted ?sort=<key>&dir=asc|desc from the request to a queryset.

    field_map: {url_key: orm_field_path} — only keys present here are honored,
    so arbitrary/unknown fields can never reach order_by().
    default: fallback ordering (e.g. "name") used when 'sort' is absent or
             not in field_map.

    Same helper as financial.utils.apply_sorting / formations.utils.apply_sorting
    — kept as a local copy so resources doesn't depend on the other apps.
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
