# resources/views.py

from django import forms
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.utils import admin_required, login_and_active_required
from resources.forms import *
from resources.forms import _BookingForm
from formations.models import Trainer, TrainingRoom
from resources.models import (
    Equipment,
    EquipmentBooking,
    EquipmentUsage,
    MaintenanceLog,
)
from resources.utils import (
    booking_conflicts_for_period,
    compute_cost_per_use_ranking,
    equipment_idle_list,
    equipment_maintenance_due_list,
)

# ---------------------------------------------------------------------------
# Trainers
# ---------------------------------------------------------------------------


@admin_required
def trainer_list(request):
    qs = Trainer.objects.all()
    q = request.GET.get("q", "").strip()
    is_active = request.GET.get("is_active", "")

    if q:
        from django.db.models import Q

        qs = qs.filter(
            Q(first_name__icontains=q)
            | Q(last_name__icontains=q)
            | Q(specialty__icontains=q)
        )
    if is_active == "1":
        qs = qs.filter(is_active=True)
    elif is_active == "0":
        qs = qs.filter(is_active=False)

    return render(request, "resources/trainer_list.html", {"trainers": qs})


@admin_required
def trainer_detail(request, pk):
    trainer = get_object_or_404(Trainer, pk=pk)
    sessions = trainer.sessions.select_related("formation").order_by("-date_start")[:10]

    # Linked beneficiary (auto-created on save for external trainers)
    beneficiary = None
    beneficiary_accounts = []
    recent_expenses = []
    try:
        from financial.models import Beneficiary, Expense

        beneficiary = trainer.beneficiary  # OneToOneField reverse
        beneficiary_accounts = beneficiary.accounts.order_by(
            "-is_default", "account_type"
        )
        recent_expenses = (
            Expense.objects.filter(beneficiary=beneficiary)
            .select_related("category")
            .order_by("-date")[:10]
        )
    except Exception:
        pass

    return render(
        request,
        "resources/trainer_detail.html",
        {
            "trainer": trainer,
            "sessions": sessions,
            "beneficiary": beneficiary,
            "beneficiary_accounts": beneficiary_accounts,
            "recent_expenses": recent_expenses,
        },
    )


@admin_required
def trainer_create(request):
    form = TrainerForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        trainer = form.save()
        messages.success(request, f"Formateur « {trainer.full_name} » créé.")
        return redirect("resources:trainer_detail", pk=trainer.pk)
    return render(
        request,
        "resources/trainer_form.html",
        {"form": form, "action": "Nouveau formateur"},
    )


@admin_required
def trainer_edit(request, pk):
    trainer = get_object_or_404(Trainer, pk=pk)
    form = TrainerForm(request.POST or None, request.FILES or None, instance=trainer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Formateur mis à jour.")
        return redirect("resources:trainer_detail", pk=pk)
    return render(
        request,
        "resources/trainer_form.html",
        {"form": form, "action": "Modifier", "trainer": trainer},
    )


@admin_required
def trainer_deactivate(request, pk):
    if request.method != "POST":
        return redirect("resources:trainer_detail", pk=pk)
    trainer = get_object_or_404(Trainer, pk=pk)
    trainer.is_active = not trainer.is_active
    trainer.save(update_fields=["is_active"])
    state = "activé" if trainer.is_active else "désactivé"
    messages.success(request, f"Formateur « {trainer.full_name} » {state}.")
    return redirect("resources:trainer_detail", pk=pk)


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------


@admin_required
def room_list(request):
    rooms = TrainingRoom.objects.all()
    return render(request, "resources/room_list.html", {"rooms": rooms})


@admin_required
def room_detail(request, pk):
    room = get_object_or_404(TrainingRoom, pk=pk)
    upcoming = (
        room.sessions.select_related("formation")
        .filter(
            date_start__gte=timezone.now().date(),
            status__in=["planned", "in_progress"],
        )
        .order_by("date_start")[:10]
    )
    return render(
        request,
        "resources/room_detail.html",
        {"room": room, "upcoming_sessions": upcoming},
    )


@admin_required
def room_create(request):
    form = TrainingRoomForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        room = form.save()
        messages.success(request, f"Salle « {room.name} » créée.")
        return redirect("resources:room_detail", pk=room.pk)
    return render(
        request, "resources/room_form.html", {"form": form, "action": "Nouvelle salle"}
    )


@admin_required
def room_edit(request, pk):
    room = get_object_or_404(TrainingRoom, pk=pk)
    form = TrainingRoomForm(request.POST or None, instance=room)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Salle mise à jour.")
        return redirect("resources:room_detail", pk=pk)
    return render(
        request,
        "resources/room_form.html",
        {"form": form, "action": "Modifier", "room": room},
    )


@admin_required
def room_deactivate(request, pk):
    if request.method != "POST":
        return redirect("resources:room_detail", pk=pk)
    room = get_object_or_404(TrainingRoom, pk=pk)
    room.is_active = not room.is_active
    room.save(update_fields=["is_active"])
    state = "activée" if room.is_active else "désactivée"
    messages.success(request, f"Salle « {room.name} » {state}.")
    return redirect("resources:room_detail", pk=pk)


@login_and_active_required
def room_availability(request, pk):
    """AJAX — check room availability for a given date range."""
    room = get_object_or_404(TrainingRoom, pk=pk)
    date_start = request.GET.get("date_start")
    date_end = request.GET.get("date_end")
    exclude_session = request.GET.get("exclude_session")

    if not date_start or not date_end:
        return JsonResponse(
            {"error": "date_start and date_end are required."}, status=400
        )

    try:
        from datetime import date

        ds = date.fromisoformat(date_start)
        de = date.fromisoformat(date_end)
    except ValueError:
        return JsonResponse(
            {"error": "Invalid date format. Use YYYY-MM-DD."}, status=400
        )

    from formations.models import Session

    exclude = None
    if exclude_session:
        try:
            exclude = Session.objects.get(pk=int(exclude_session))
        except (Session.DoesNotExist, ValueError):
            pass

    available = room.is_available(ds, de, exclude_session=exclude)
    return JsonResponse({"available": available, "room": room.name})


# ---------------------------------------------------------------------------
# Equipment
# ---------------------------------------------------------------------------


@admin_required
def equipment_list(request):
    qs = Equipment.objects.all()
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    condition = request.GET.get("condition", "")
    maintenance_due = request.GET.get("maintenance_due", "")

    if q:
        from django.db.models import Q

        qs = qs.filter(
            Q(name__icontains=q) | Q(category__icontains=q) | Q(location__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)
    if condition:
        qs = qs.filter(condition=condition)

    if maintenance_due == "1":
        # is_maintenance_due is a property — filter in Python
        qs = [e for e in qs if e.is_maintenance_due]

    return render(
        request,
        "resources/equipment_list.html",
        {
            "equipment_list": qs,
            "status_choices": Equipment.STATUS_CHOICES,
            "condition_choices": Equipment.CONDITION_CHOICES,
        },
    )


@admin_required
def equipment_detail(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    usages = equipment.usages.select_related(
        "assigned_to_session__formation", "assigned_to_project__client"
    ).order_by("-date")[:20]
    maintenance_logs = equipment.maintenance_logs.order_by("-date")[:10]
    bookings = equipment.bookings.order_by("-date_from")[:10]
    return render(
        request,
        "resources/equipment_detail.html",
        {
            "equipment": equipment,
            "usages": usages,
            "maintenance_logs": maintenance_logs,
            "bookings": bookings,
        },
    )


@admin_required
def equipment_create(request):
    form = EquipmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        equipment = form.save()
        messages.success(request, f"Équipement « {equipment.name} » créé.")
        return redirect("resources:equipment_detail", pk=equipment.pk)
    return render(
        request,
        "resources/equipment_form.html",
        {"form": form, "action": "Nouvel équipement"},
    )


@admin_required
def equipment_edit(request, pk):
    equipment = get_object_or_404(Equipment, pk=pk)
    form = EquipmentForm(request.POST or None, instance=equipment)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Équipement mis à jour.")
        return redirect("resources:equipment_detail", pk=pk)
    return render(
        request,
        "resources/equipment_form.html",
        {"form": form, "action": "Modifier", "equipment": equipment},
    )


@admin_required
def equipment_update_status(request, pk):
    if request.method != "POST":
        return redirect("resources:equipment_detail", pk=pk)
    equipment = get_object_or_404(Equipment, pk=pk)
    new_status = request.POST.get("status")
    valid_statuses = [s for s, _ in Equipment.STATUS_CHOICES]
    if new_status not in valid_statuses:
        messages.error(request, "Statut invalide.")
        return redirect("resources:equipment_detail", pk=pk)
    equipment.status = new_status
    equipment.save(update_fields=["status"])
    messages.success(request, f"Statut mis à jour : {equipment.get_status_display()}.")
    return redirect("resources:equipment_detail", pk=pk)


# ---------------------------------------------------------------------------
# Equipment Usage
# ---------------------------------------------------------------------------


@admin_required
def usage_add(request, equipment_pk):
    equipment = get_object_or_404(Equipment, pk=equipment_pk)
    form = EquipmentUsageForm(request.POST or None, equipment=equipment)
    if request.method == "POST" and form.is_valid():
        usage = form.save(commit=False)
        usage.equipment = equipment
        usage.save()
        messages.success(request, "Utilisation enregistrée.")
        return redirect("resources:equipment_detail", pk=equipment_pk)
    return render(
        request,
        "resources/usage_form.html",
        {"form": form, "equipment": equipment, "action": "Ajouter une utilisation"},
    )


@admin_required
def usage_edit(request, equipment_pk, pk):
    equipment = get_object_or_404(Equipment, pk=equipment_pk)
    usage = get_object_or_404(EquipmentUsage, pk=pk, equipment=equipment)
    form = EquipmentUsageForm(request.POST or None, instance=usage, equipment=equipment)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Utilisation mise à jour.")
        return redirect("resources:equipment_detail", pk=equipment_pk)
    return render(
        request,
        "resources/usage_form.html",
        {"form": form, "equipment": equipment, "action": "Modifier"},
    )


@admin_required
def usage_delete(request, equipment_pk, pk):
    if request.method != "POST":
        return redirect("resources:equipment_detail", pk=equipment_pk)
    usage = get_object_or_404(EquipmentUsage, pk=pk, equipment_id=equipment_pk)
    usage.delete()
    messages.success(request, "Utilisation supprimée.")
    return redirect("resources:equipment_detail", pk=equipment_pk)


# ---------------------------------------------------------------------------
# Equipment Bookings
# ---------------------------------------------------------------------------


@admin_required
def booking_add(request, equipment_pk):
    from resources.forms import (
        EquipmentForm,
    )  # reuse inline or add dedicated form below

    equipment = get_object_or_404(Equipment, pk=equipment_pk)
    form = _BookingForm(request.POST or None, equipment=equipment)
    if request.method == "POST" and form.is_valid():
        booking = form.save(commit=False)
        booking.equipment = equipment
        booking.save()
        messages.success(request, "Réservation enregistrée.")
        return redirect("resources:equipment_detail", pk=equipment_pk)
    return render(
        request,
        "resources/booking_form.html",
        {"form": form, "equipment": equipment, "action": "Nouvelle réservation"},
    )


@admin_required
def booking_edit(request, equipment_pk, pk):
    equipment = get_object_or_404(Equipment, pk=equipment_pk)
    booking = get_object_or_404(EquipmentBooking, pk=pk, equipment=equipment)
    form = _BookingForm(request.POST or None, instance=booking, equipment=equipment)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Réservation mise à jour.")
        return redirect("resources:equipment_detail", pk=equipment_pk)
    return render(
        request,
        "resources/booking_form.html",
        {"form": form, "equipment": equipment, "action": "Modifier"},
    )


@admin_required
def booking_delete(request, equipment_pk, pk):
    if request.method != "POST":
        return redirect("resources:equipment_detail", pk=equipment_pk)
    booking = get_object_or_404(EquipmentBooking, pk=pk, equipment_id=equipment_pk)
    booking.delete()
    messages.success(request, "Réservation supprimée.")
    return redirect("resources:equipment_detail", pk=equipment_pk)


# ---------------------------------------------------------------------------
# Maintenance Logs
# ---------------------------------------------------------------------------


@admin_required
def maintenance_add(request, equipment_pk):
    equipment = get_object_or_404(Equipment, pk=equipment_pk)
    form = MaintenanceLogForm(request.POST or None, equipment=equipment)
    if request.method == "POST" and form.is_valid():
        log = form.save(commit=False)
        log.equipment = equipment
        log.save()
        messages.success(request, "Maintenance enregistrée.")
        return redirect("resources:equipment_detail", pk=equipment_pk)
    return render(
        request,
        "resources/maintenance_form.html",
        {"form": form, "equipment": equipment, "action": "Ajouter une maintenance"},
    )


@admin_required
def maintenance_edit(request, equipment_pk, pk):
    equipment = get_object_or_404(Equipment, pk=equipment_pk)
    log = get_object_or_404(MaintenanceLog, pk=pk, equipment=equipment)
    form = MaintenanceLogForm(request.POST or None, instance=log, equipment=equipment)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Maintenance mise à jour.")
        return redirect("resources:equipment_detail", pk=equipment_pk)
    return render(
        request,
        "resources/maintenance_form.html",
        {"form": form, "equipment": equipment, "action": "Modifier"},
    )


@admin_required
def maintenance_delete(request, equipment_pk, pk):
    if request.method != "POST":
        return redirect("resources:equipment_detail", pk=equipment_pk)
    log = get_object_or_404(MaintenanceLog, pk=pk, equipment_id=equipment_pk)
    log.delete()
    messages.success(request, "Maintenance supprimée.")
    return redirect("resources:equipment_detail", pk=equipment_pk)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@admin_required
def equipment_analytics(request):
    from django.db.models import Count, Sum

    total = Equipment.objects.count()
    by_status = {
        s: Equipment.objects.filter(status=s).count()
        for s, _ in Equipment.STATUS_CHOICES
    }
    by_condition = {
        c: Equipment.objects.filter(condition=c).count()
        for c, _ in Equipment.CONDITION_CHOICES
    }
    maintenance_due = equipment_maintenance_due_list()
    total_purchase_value = (
        Equipment.objects.aggregate(total=Sum("purchase_cost"))["total"] or 0
    )
    total_current_value = (
        Equipment.objects.aggregate(total=Sum("current_value"))["total"] or 0
    )

    return render(
        request,
        "resources/equipment_analytics.html",
        {
            "total": total,
            "by_status": by_status,
            "by_condition": by_condition,
            "maintenance_due": maintenance_due,
            "total_purchase_value": total_purchase_value,
            "total_current_value": total_current_value,
        },
    )


@admin_required
def utilization_report(request):
    ranked = compute_cost_per_use_ranking()
    return render(
        request,
        "resources/utilization_report.html",
        {"equipment_list": ranked},
    )


@admin_required
def idle_equipment_report(request):
    from django.conf import settings

    threshold = int(
        request.GET.get("days", getattr(settings, "EQUIPMENT_IDLE_THRESHOLD_DAYS", 90))
    )
    idle = equipment_idle_list(threshold_days=threshold)
    return render(
        request,
        "resources/idle_equipment.html",
        {"idle_equipment": idle, "threshold_days": threshold},
    )


@admin_required
def equipment_availability_check(request):
    """
    AJAX — returns booking conflicts for a given date range.
    GET params: date_from, date_to, exclude_booking (optional pk)
    """
    date_from_str = request.GET.get("date_from")
    date_to_str = request.GET.get("date_to")
    exclude_pk = request.GET.get("exclude_booking")

    if not date_from_str or not date_to_str:
        return JsonResponse(
            {"error": "date_from and date_to are required."}, status=400
        )

    try:
        from datetime import date

        date_from = date.fromisoformat(date_from_str)
        date_to = date.fromisoformat(date_to_str)
    except ValueError:
        return JsonResponse(
            {"error": "Invalid date format. Use YYYY-MM-DD."}, status=400
        )

    exclude_booking_pk = (
        int(exclude_pk) if exclude_pk and exclude_pk.isdigit() else None
    )
    conflicts = booking_conflicts_for_period(date_from, date_to, exclude_booking_pk)
    return JsonResponse({"conflicts": conflicts})


# ---------------------------------------------------------------------------
# Internal — EquipmentBooking form (no dedicated forms.py entry provided)
# ---------------------------------------------------------------------------
