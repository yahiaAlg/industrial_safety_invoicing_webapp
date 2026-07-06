# formations/views.py  — v3.1
# CHANGE vs v3.0: session_create only:
#   1. Accepts ?client=<pk> GET param → pre-fills client (from client_create redirect)
#   2. Post-save redirects to /financial/invoices/create/?session=<pk>
#      instead of session_detail (guided workflow step 3)

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from core.utils import admin_required, login_and_active_required
from formations.forms import (
    AttestationIssueForm,
    FormationCategoryForm,
    FormationForm,
    ParticipantForm,
    ParticipantImportForm,
    SessionCancelForm,
    SessionFilterForm,
    SessionForm,
    SessionStatusForm,
)
from formations.models import (
    Attestation,
    Formation,
    FormationCategory,
    Participant,
    Session,
    Trainer,
)
from formations.utils import (
    bulk_enroll_participants,
    issue_attestations_bulk,
    parse_participant_csv,
    parse_participant_excel,
)


# ---------------------------------------------------------------------------
# Formation catalog
# ---------------------------------------------------------------------------


@admin_required
def formation_list(request):
    qs = Formation.objects.select_related("category").all()
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category")
    is_active = request.GET.get("is_active")

    if q:
        from django.db.models import Q

        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
    if category:
        qs = qs.filter(category_id=category)
    if is_active == "1":
        qs = qs.filter(is_active=True)
    elif is_active == "0":
        qs = qs.filter(is_active=False)

    categories = FormationCategory.objects.all()
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "formations/formation_list.html",
        {"page_obj": page_obj, "categories": categories},
    )


@admin_required
def formation_detail(request, pk):
    formation = get_object_or_404(Formation.objects.select_related("category"), pk=pk)
    sessions = formation.sessions.select_related("client", "trainer").order_by(
        "-date_start"
    )[:10]

    all_active = formation.sessions.exclude(status=Session.STATUS_CANCELLED)
    used_days = sum(
        (s.date_end - s.date_start).days + 1
        for s in all_active
        if s.date_start and s.date_end
    )
    duration_reached = bool(
        formation.duration_days and used_days >= formation.duration_days
    )
    remaining_days = max(0, (formation.duration_days or 0) - used_days)

    active_sessions_list = list(
        formation.sessions.filter(
            status__in=[Session.STATUS_PLANNED, Session.STATUS_IN_PROGRESS]
        )
        .values("pk", "date_start", "capacity")
        .order_by("date_start")
    )
    capacity_conflicts = [
        {
            "pk": s["pk"],
            "date": s["date_start"].strftime("%d/%m/%Y"),
            "capacity": s["capacity"],
        }
        for s in active_sessions_list
        if s["capacity"] > formation.max_participants
    ]
    max_session_capacity = max((s["capacity"] for s in capacity_conflicts), default=0)

    return render(
        request,
        "formations/formation_detail.html",
        {
            "formation": formation,
            "sessions": sessions,
            "used_days": used_days,
            "remaining_days": remaining_days,
            "duration_reached": duration_reached,
            "capacity_conflicts": capacity_conflicts,
            "max_session_capacity": max_session_capacity,
        },
    )


@admin_required
def formation_create(request):
    form = FormationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        formation = form.save()
        messages.success(
            request,
            f"Formation « {formation.title} » créée. Créez maintenant la facture.",
        )
        client_pk = request.POST.get("client", "")
        url = reverse("financial:invoice_create") + f"?client={client_pk}"
        return redirect(url)
    client_pk = request.GET.get("client", "")
    return render(
        request,
        "formations/formation_form.html",
        {
            "form": form,
            "action": "Nouvelle formation",
            "client_pk": client_pk,
        },
    )


@admin_required
def formation_edit(request, pk):
    formation = get_object_or_404(Formation, pk=pk)
    initial = {}
    suggest_price = request.GET.get("suggest_base_price")
    if suggest_price and request.method == "GET":
        try:
            from decimal import Decimal

            initial["base_price"] = Decimal(suggest_price).quantize(Decimal("0.01"))
        except Exception:
            pass
    suggest_max = request.GET.get("suggest_max")
    if suggest_max and request.method == "GET":
        try:
            initial["max_participants"] = int(suggest_max)
        except Exception:
            pass

    form = FormationForm(
        request.POST or None, instance=formation, initial=initial or None
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Formation mise à jour.")
        return redirect("formations:formation_detail", pk=pk)

    import json as _json

    active_sessions_list2 = list(
        formation.sessions.filter(
            status__in=[Session.STATUS_PLANNED, Session.STATUS_IN_PROGRESS]
        )
        .values("pk", "date_start", "capacity")
        .order_by("date_start")
    )
    cap_conflicts = [
        {
            "pk": s["pk"],
            "date": s["date_start"].strftime("%d/%m/%Y"),
            "capacity": s["capacity"],
        }
        for s in active_sessions_list2
    ]
    return render(
        request,
        "formations/formation_form.html",
        {
            "form": form,
            "action": "Modifier",
            "formation": formation,
            "session_capacity_conflicts_json": _json.dumps(cap_conflicts),
        },
    )


@admin_required
def formation_deactivate(request, pk):
    if request.method != "POST":
        return redirect("formations:formation_detail", pk=pk)
    formation = get_object_or_404(Formation, pk=pk)
    formation.is_active = not formation.is_active
    formation.save(update_fields=["is_active"])
    state = "activée" if formation.is_active else "désactivée"
    messages.success(request, f"Formation « {formation.title} » {state}.")
    return redirect("formations:formation_detail", pk=pk)


@admin_required
def formation_sync_capacities(request, pk):
    if request.method != "POST":
        return redirect("formations:formation_detail", pk=pk)
    formation = get_object_or_404(Formation, pk=pk)
    updated = formation.sessions.filter(
        status__in=[Session.STATUS_PLANNED, Session.STATUS_IN_PROGRESS],
        capacity__gt=formation.max_participants,
    ).update(capacity=formation.max_participants)
    messages.success(
        request,
        f"{updated} session(s) mise(s) à jour — capacité ramenée à {formation.max_participants}.",
    )
    return redirect("formations:formation_detail", pk=pk)


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


@admin_required
def category_list(request):
    categories = FormationCategory.objects.all()
    return render(request, "formations/category_list.html", {"categories": categories})


@admin_required
def category_create(request):
    form = FormationCategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        category = form.save()
        messages.success(request, f"Catégorie « {category.name} » créée.")
        return redirect("formations:category_list")
    return render(
        request,
        "formations/category_form.html",
        {"form": form, "action": "Nouvelle catégorie"},
    )


@admin_required
def category_edit(request, pk):
    category = get_object_or_404(FormationCategory, pk=pk)
    form = FormationCategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Catégorie mise à jour.")
        return redirect("formations:category_list")
    return render(
        request,
        "formations/category_form.html",
        {"form": form, "action": "Modifier", "category": category},
    )


@admin_required
def category_delete(request, pk):
    if request.method != "POST":
        return redirect("formations:category_list")
    category = get_object_or_404(FormationCategory, pk=pk)
    if category.formations.exists():
        messages.error(
            request,
            f"Impossible de supprimer « {category.name} » : des formations y sont associées.",
        )
        return redirect("formations:category_list")
    category.delete()
    messages.success(request, "Catégorie supprimée.")
    return redirect("formations:category_list")


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@login_and_active_required
def session_list(request):
    qs = Session.objects.select_related("formation", "client", "trainer").all()
    form = SessionFilterForm(request.GET or None)

    if form.is_valid():
        q = form.cleaned_data.get("q")
        status = form.cleaned_data.get("status")
        date_from = form.cleaned_data.get("date_from")
        date_to = form.cleaned_data.get("date_to")
        formation = form.cleaned_data.get("formation")

        if q:
            from django.db.models import Q

            qs = qs.filter(
                Q(formation__title__icontains=q)
                | Q(client__name__icontains=q)
                | Q(trainer__last_name__icontains=q)
                | Q(trainer__first_name__icontains=q)
            )
        if status:
            qs = qs.filter(status=status)
        if date_from:
            qs = qs.filter(date_start__gte=date_from)
        if date_to:
            qs = qs.filter(date_end__lte=date_to)
        if formation:
            qs = qs.filter(formation=formation)

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "formations/session_list.html",
        {"page_obj": page_obj, "filter_form": form},
    )


@login_and_active_required
def session_detail(request, pk):
    session = get_object_or_404(
        Session.objects.select_related("formation", "client", "trainer", "room"), pk=pk
    )
    participants = session.participants.all()
    attestations = (
        session.attestations.select_related("participant")
        if session.status == Session.STATUS_COMPLETED
        else []
    )
    return render(
        request,
        "formations/session_detail.html",
        {
            "session": session,
            "participants": participants,
            "attestations": attestations,
        },
    )


def _session_form_context(exclude_session_pk=None):
    import json
    from django.urls import reverse
    from formations.models import TrainingRoom

    room_capacities = {
        str(r.pk): r.capacity for r in TrainingRoom.objects.filter(is_active=True)
    }

    formation_data = {}
    for f in Formation.objects.filter(is_active=True):
        sessions_qs = f.sessions.exclude(status=Session.STATUS_CANCELLED)
        if exclude_session_pk:
            sessions_qs = sessions_qs.exclude(pk=exclude_session_pk)

        used_days = sum(
            (s.date_end - s.date_start).days + 1
            for s in sessions_qs
            if s.date_start and s.date_end
        )
        existing_price_sum = sum(
            float(s.price_per_participant or f.base_price or 0) for s in sessions_qs
        )
        hours_per_day = (
            float(f.duration_hours) / float(f.duration_days)
            if f.duration_hours and f.duration_days
            else None
        )
        prev_session = (
            f.sessions.exclude(status=Session.STATUS_CANCELLED)
            .order_by("-date_start", "-pk")
            .first()
        )
        prev_client_id = (
            str(prev_session.client_id)
            if prev_session and prev_session.client_id
            else None
        )
        prev_client_name = (
            prev_session.client.name if prev_session and prev_session.client else None
        )
        prev_participant_count = (
            prev_session.participants.count() if prev_session else 0
        )
        prev_session_date = (
            prev_session.date_start.strftime("%d/%m/%Y") if prev_session else None
        )

        formation_data[str(f.pk)] = {
            "duration_days": float(f.duration_days) if f.duration_days else None,
            "duration_hours": float(f.duration_hours) if f.duration_hours else None,
            "hours_per_day": hours_per_day,
            "base_price": float(f.base_price) if f.base_price else None,
            "used_days": used_days,
            "existing_price_sum": round(existing_price_sum, 2),
            "edit_url": reverse("formations:formation_edit", args=[f.pk]),
            "prev_client_id": prev_client_id,
            "prev_client_name": prev_client_name,
            "prev_participant_count": prev_participant_count,
            "prev_session_date": prev_session_date,
        }

    trainer_bookings = {}
    for trainer in Trainer.objects.filter(is_active=True):
        qs = trainer.sessions.filter(
            status__in=[Session.STATUS_PLANNED, Session.STATUS_IN_PROGRESS]
        )
        if exclude_session_pk:
            qs = qs.exclude(pk=exclude_session_pk)
        bookings = [
            {
                "date_start": s.date_start.strftime("%Y-%m-%d"),
                "date_end": s.date_end.strftime("%Y-%m-%d"),
                "label": str(s),
            }
            for s in qs
            if s.date_start and s.date_end
        ]
        if bookings:
            trainer_bookings[str(trainer.pk)] = bookings

    room_bookings = {}
    for room in TrainingRoom.objects.filter(is_active=True):
        qs = room.sessions.filter(
            status__in=[Session.STATUS_PLANNED, Session.STATUS_IN_PROGRESS]
        )
        if exclude_session_pk:
            qs = qs.exclude(pk=exclude_session_pk)
        bookings = [
            {
                "date_start": s.date_start.strftime("%Y-%m-%d"),
                "date_end": s.date_end.strftime("%Y-%m-%d"),
                "label": str(s),
            }
            for s in qs
            if s.date_start and s.date_end
        ]
        if bookings:
            room_bookings[str(room.pk)] = bookings

    return {
        "room_capacities_json": json.dumps(room_capacities),
        "formation_data_json": json.dumps(formation_data),
        "trainer_bookings_json": json.dumps(trainer_bookings),
        "room_bookings_json": json.dumps(room_bookings),
    }


# ── PATCHED v3.1 ─────────────────────────────────────────────────────────── #
def session_create(request):
    import math
    from datetime import date, timedelta
    from decimal import Decimal, ROUND_HALF_UP

    prefill_formation = None
    initial = {}

    # Step 2 of guided workflow: ?client=<pk> comes from clients:client_create
    client_pk = request.GET.get("client")
    if client_pk:
        initial["client"] = client_pk

    formation_pk = request.GET.get("formation")
    if formation_pk:
        try:
            prefill_formation = Formation.objects.get(pk=formation_pk, is_active=True)
            initial["formation"] = prefill_formation.pk
            initial["capacity"] = int(prefill_formation.max_participants)

            if prefill_formation.duration_days:
                today = date.today()
                duration = max(1, math.ceil(float(prefill_formation.duration_days)))
                initial["date_start"] = today.strftime("%Y-%m-%d")
                initial["date_end"] = (today + timedelta(days=duration - 1)).strftime(
                    "%Y-%m-%d"
                )

            if prefill_formation.duration_hours:
                initial["session_hours"] = (
                    format(prefill_formation.duration_hours, "f")
                    .rstrip("0")
                    .rstrip(".")
                )

            if prefill_formation.base_price and prefill_formation.duration_hours:
                sh = float(prefill_formation.duration_hours)
                dh = float(prefill_formation.duration_hours)
                price = (
                    Decimal(str(prefill_formation.base_price))
                    * Decimal(str(sh))
                    / Decimal(str(dh))
                )
                price = price.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                initial["price_per_participant"] = str(price)
            elif prefill_formation.base_price:
                initial["price_per_participant"] = (
                    format(prefill_formation.base_price, "f").rstrip("0").rstrip(".")
                )

        except Formation.DoesNotExist:
            pass

    prev_session = None
    if prefill_formation:
        prev_session = (
            prefill_formation.sessions.exclude(status=Session.STATUS_CANCELLED)
            .order_by("-date_start", "-pk")
            .first()
        )
        # Only fall back to prev_session client if no ?client= was passed
        if prev_session and "client" not in initial and prev_session.client_id:
            initial["client"] = prev_session.client_id

    form = SessionForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        session = form.save()

        # Copy participants from previous session
        if prev_session and prev_session.participants.exists():
            copied = 0
            for p in prev_session.participants.all():
                try:
                    session.participants.create(
                        first_name=p.first_name,
                        last_name=p.last_name,
                        employer=p.employer,
                        employer_client=p.employer_client,
                        phone=p.phone,
                        email=p.email,
                        job_title=p.job_title,
                        attended=True,
                        notes=p.notes,
                    )
                    copied += 1
                except Exception:
                    pass
            if copied:
                prev_date = prev_session.date_start.strftime("%d/%m/%Y")
                messages.info(
                    request,
                    f"{copied} participant(s) repris de la session précédente ({prev_date}). "
                    "Vérifiez et ajustez la liste si nécessaire.",
                )

        messages.success(
            request, "Session créée. Créez maintenant la facture proforma."
        )
        # Step 3 of guided workflow: go straight to invoice creation
        return redirect(f"/financial/invoices/create/?session={session.pk}")

    ctx = _session_form_context()
    ctx.update(
        {
            "form": form,
            "action": "Nouvelle session",
            "prefill_formation": prefill_formation,
            "prev_session": prev_session,
        }
    )
    return render(request, "formations/session_form.html", ctx)


# ── END PATCH ────────────────────────────────────────────────────────────── #


@admin_required
def session_edit(request, pk):
    session = get_object_or_404(Session, pk=pk)
    form = SessionForm(request.POST or None, instance=session)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Session mise à jour.")
        return redirect("formations:session_detail", pk=pk)

    ctx = _session_form_context(exclude_session_pk=pk)
    ctx.update({"form": form, "action": "Modifier", "session": session})
    return render(request, "formations/session_form.html", ctx)


@admin_required
def session_update_status(request, pk):
    session = get_object_or_404(Session, pk=pk)
    form = SessionStatusForm(request.POST or None, current_status=session.status)

    if request.method == "POST" and form.is_valid():
        new_status = form.cleaned_data["status"]
        session.status = new_status
        if new_status == Session.STATUS_CANCELLED:
            session.cancellation_reason = form.cleaned_data["cancellation_reason"]
        session.save()
        messages.success(
            request, f"Statut mis à jour : {session.get_status_display()}."
        )
        return redirect("formations:session_detail", pk=pk)

    return render(
        request,
        "formations/session_status_form.html",
        {"form": form, "session": session},
    )


@admin_required
def session_cancel(request, pk):
    session = get_object_or_404(Session, pk=pk)
    if session.status not in [Session.STATUS_PLANNED, Session.STATUS_IN_PROGRESS]:
        messages.error(request, "Cette session ne peut plus être annulée.")
        return redirect("formations:session_detail", pk=pk)

    form = SessionCancelForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        session.status = Session.STATUS_CANCELLED
        session.cancellation_reason = form.cleaned_data["cancellation_reason"]
        session.save(update_fields=["status", "cancellation_reason"])
        messages.success(request, "Session annulée.")
        return redirect("formations:session_detail", pk=pk)

    return render(
        request, "formations/session_cancel.html", {"form": form, "session": session}
    )


# ---------------------------------------------------------------------------
# Participants
# ---------------------------------------------------------------------------


@login_and_active_required
def participant_add(request, session_pk):
    session = get_object_or_404(Session, pk=session_pk)
    if session.is_full:
        messages.error(request, "La session est complète.")
        return redirect("formations:session_detail", pk=session_pk)

    form = ParticipantForm(request.POST or None, session=session)
    if request.method == "POST" and form.is_valid():
        participant = form.save(commit=False)
        participant.session = session
        participant.save()
        messages.success(request, f"Participant « {participant.full_name} » inscrit.")
        return redirect("formations:session_detail", pk=session_pk)

    return render(
        request,
        "formations/participant_form.html",
        {"form": form, "session": session, "action": "Inscrire un participant"},
    )


@login_and_active_required
def participant_edit(request, session_pk, pk):
    session = get_object_or_404(Session, pk=session_pk)
    participant = get_object_or_404(Participant, pk=pk, session=session)
    form = ParticipantForm(request.POST or None, instance=participant, session=session)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Participant mis à jour.")
        return redirect("formations:session_detail", pk=session_pk)

    return render(
        request,
        "formations/participant_form.html",
        {"form": form, "session": session, "action": "Modifier le participant"},
    )


@login_and_active_required
def participant_delete(request, session_pk, pk):
    if request.method != "POST":
        return redirect("formations:session_detail", pk=session_pk)
    participant = get_object_or_404(Participant, pk=pk, session_id=session_pk)
    participant.delete()
    messages.success(request, "Participant supprimé.")
    return redirect("formations:session_detail", pk=session_pk)


@admin_required
def participant_toggle_attendance(request, session_pk, pk):
    if request.method != "POST":
        return redirect("formations:session_detail", pk=session_pk)
    participant = get_object_or_404(Participant, pk=pk, session_id=session_pk)
    participant.attended = not participant.attended
    participant.save(update_fields=["attended"])
    state = "présent" if participant.attended else "absent"
    messages.success(request, f"« {participant.full_name} » marqué {state}.")
    return redirect("formations:session_detail", pk=session_pk)


@login_and_active_required
def participant_import(request, session_pk):
    session = get_object_or_404(Session, pk=session_pk)
    form = ParticipantImportForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        uploaded = form.cleaned_data["file"]
        name = uploaded.name.lower()

        if name.endswith(".csv"):
            rows, parse_errors = parse_participant_csv(uploaded)
        else:
            rows, parse_errors = parse_participant_excel(uploaded)

        if parse_errors:
            for err in parse_errors:
                messages.warning(request, err)

        created, skipped, enroll_errors = bulk_enroll_participants(session, rows)
        for err in enroll_errors:
            messages.warning(request, err)

        messages.success(
            request,
            f"{created} participant(s) importé(s), {skipped} ignoré(s) (doublons).",
        )
        return redirect("formations:session_detail", pk=session_pk)

    return render(
        request,
        "formations/participant_import.html",
        {"form": form, "session": session},
    )


# ---------------------------------------------------------------------------
# Attestations
# ---------------------------------------------------------------------------


@admin_required
def attestation_issue_bulk(request, session_pk):
    session = get_object_or_404(Session, pk=session_pk)
    if session.status != Session.STATUS_COMPLETED:
        messages.error(
            request,
            "Les attestations ne peuvent être émises que pour une session terminée.",
        )
        return redirect("formations:session_detail", pk=session_pk)

    form = AttestationIssueForm(request.POST or None, session=session)
    if request.method == "POST" and form.is_valid():
        issue_date = form.cleaned_data["issue_date"]
        participant_ids = form.cleaned_data["participant_ids"].values_list(
            "pk", flat=True
        )
        issued, skipped = issue_attestations_bulk(session, participant_ids, issue_date)
        messages.success(
            request,
            f"{issued} attestation(s) émise(s), {skipped} ignorée(s) (déjà émises).",
        )
        return redirect("formations:session_detail", pk=session_pk)

    return render(
        request, "formations/attestation_issue.html", {"form": form, "session": session}
    )


@login_and_active_required
def attestation_detail(request, pk):
    attestation = get_object_or_404(
        Attestation.objects.select_related(
            "participant", "session__formation", "session__trainer"
        ),
        pk=pk,
    )
    return render(
        request, "formations/attestation_detail.html", {"attestation": attestation}
    )


@admin_required
def attestation_print(request, pk):
    from core.models import FormationInfo, InstituteInfo

    attestation = get_object_or_404(
        Attestation.objects.select_related(
            "participant", "session__formation__category", "session__trainer"
        ),
        pk=pk,
    )
    return render(
        request,
        "formations/attestation_print.html",
        {
            "attestation": attestation,
            "institute": InstituteInfo.get_instance(),
            "formation_info": FormationInfo.get_instance(),
        },
    )


@admin_required
def attestation_revoke(request, pk):
    if request.method != "POST":
        return redirect("formations:attestation_detail", pk=pk)
    attestation = get_object_or_404(Attestation, pk=pk)
    session_pk = attestation.session_id
    attestation.is_issued = False
    attestation.save(update_fields=["is_issued"])
    messages.success(request, f"Attestation {attestation.reference} révoquée.")
    return redirect("formations:session_detail", pk=session_pk)


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@admin_required
def formation_analytics(request):
    from django.db.models import Count

    sessions = Session.objects.select_related("formation", "trainer")
    completed = sessions.filter(status=Session.STATUS_COMPLETED)

    return render(
        request,
        "formations/analytics.html",
        {
            "total_sessions": sessions.count(),
            "total_completed": completed.count(),
            "total_participants": Participant.objects.filter(
                session__status=Session.STATUS_COMPLETED
            ).count(),
            "total_attended": Participant.objects.filter(
                session__status=Session.STATUS_COMPLETED, attended=True
            ).count(),
            "total_attestations": Attestation.objects.filter(is_issued=True).count(),
            "revenue": sum(s.total_revenue for s in completed),
            "top_formations": Formation.objects.annotate(
                session_count=Count("sessions")
            ).order_by("-session_count")[:5],
        },
    )


@admin_required
def session_fill_rates(request):
    sessions = (
        Session.objects.select_related("formation", "trainer")
        .filter(
            status__in=[
                Session.STATUS_COMPLETED,
                Session.STATUS_IN_PROGRESS,
                Session.STATUS_PLANNED,
            ]
        )
        .order_by("-date_start")
    )
    data = [
        {
            "session": s,
            "fill_rate": s.fill_rate,
            "participant_count": s.participant_count,
            "available_spots": s.available_spots,
        }
        for s in sessions
    ]
    return render(request, "formations/fill_rates.html", {"data": data})


@admin_required
def trainer_utilization(request):
    from resources.models import Trainer

    trainers = Trainer.objects.filter(is_active=True).prefetch_related("sessions")
    data = [
        {
            "trainer": t,
            "session_count": t.session_count,
            "total_earnings": t.total_earnings,
            "upcoming": t.upcoming_sessions[:3],
        }
        for t in trainers
    ]
    return render(request, "formations/trainer_utilization.html", {"data": data})


# ---------------------------------------------------------------------------
# AJAX
# ---------------------------------------------------------------------------


@login_and_active_required
def sessions_calendar_feed(request):
    qs = Session.objects.select_related("formation").exclude(
        status=Session.STATUS_CANCELLED
    )
    start = request.GET.get("start")
    end = request.GET.get("end")
    if start:
        qs = qs.filter(date_end__gte=start)
    if end:
        qs = qs.filter(date_start__lte=end)

    STATUS_COLORS = {
        Session.STATUS_PLANNED: "#3B82F6",
        Session.STATUS_IN_PROGRESS: "#F59E0B",
        Session.STATUS_COMPLETED: "#10B981",
        Session.STATUS_CANCELLED: "#EF4444",
    }

    events = [
        {
            "id": s.pk,
            "title": s.formation.title,
            "start": s.date_start.isoformat(),
            "end": s.date_end.isoformat(),
            "color": STATUS_COLORS.get(s.status, "#6B7280"),
            "url": f"/formations/sessions/{s.pk}/",
            "extendedProps": {
                "status": s.status,
                "participant_count": s.participant_count,
                "capacity": s.capacity,
            },
        }
        for s in qs
    ]
    return JsonResponse(events, safe=False)


from django.views.decorators.http import require_GET


@admin_required
@require_GET
def api_formation_list(request):
    q = request.GET.get("q", "").strip()
    qs = Formation.objects.filter(is_active=True).order_by("title")
    if q:
        qs = qs.filter(title__icontains=q)

    data = [
        {
            "id": f.pk,
            "title": f.title,
            "duration_days": getattr(f, "duration_days", None)
            or getattr(f, "duration", None),
            "base_price": str(
                getattr(f, "base_price", None)
                or getattr(f, "price_per_person", None)
                or ""
            ),
            "description": f.title,
        }
        for f in qs
    ]
    return JsonResponse({"results": data})


@admin_required
@require_GET
def api_formation_detail(request, pk):
    f = get_object_or_404(Formation, pk=pk)
    return JsonResponse(
        {
            "id": f.pk,
            "title": f.title,
            "description": f.title,
            "duration_days": getattr(f, "duration_days", None)
            or getattr(f, "duration", None),
            "base_price": str(
                getattr(f, "base_price", None)
                or getattr(f, "price_per_person", None)
                or ""
            ),
        }
    )
