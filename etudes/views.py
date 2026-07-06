# etudes/views.py

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.utils import admin_required, login_and_active_required
from etudes.forms import (
    DeliverableApproveForm,
    PhaseReorderForm,
    PhaseStatusForm,
    ProjectCancelForm,
    ProjectCloseForm,
    ProjectDeliverableForm,
    ProjectPhaseForm,
    StudyProjectFilterForm,
    StudyProjectForm,
)
from etudes.models import ProjectDeliverable, ProjectPhase, StudyProject


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _is_receptionist(user):
    return hasattr(user, "profile") and user.profile.is_receptionist


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@login_and_active_required
def project_list(request):
    qs = StudyProject.objects.select_related("client").all()
    form = StudyProjectFilterForm(request.GET or None)

    if form.is_valid():
        q = form.cleaned_data.get("q")
        status = form.cleaned_data.get("status")
        priority = form.cleaned_data.get("priority")
        overdue_only = form.cleaned_data.get("overdue_only")

        if q:
            from django.db.models import Q

            qs = qs.filter(
                Q(title__icontains=q)
                | Q(client__name__icontains=q)
                | Q(project_type__icontains=q)
                | Q(reference__icontains=q)
            )
        if status:
            qs = qs.filter(status=status)
        if priority:
            qs = qs.filter(priority=priority)
        if overdue_only:
            today = timezone.now().date()
            qs = qs.filter(
                status=StudyProject.STATUS_IN_PROGRESS,
                end_date__lt=today,
            )

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "etudes/project_list.html",
        {"page_obj": page_obj, "filter_form": form},
    )


@login_and_active_required
def project_detail(request, pk):
    project = get_object_or_404(StudyProject.objects.select_related("client"), pk=pk)
    phases = project.phases.prefetch_related("deliverables").order_by("order")
    return render(
        request,
        "etudes/project_detail.html",
        {"project": project, "phases": phases},
    )


@login_and_active_required
def project_print(request, pk):
    """
    Printable / PDF-friendly A4 project sheet for a study project.
    Includes header (institute + bureau info), KPIs, phases table,
    and financial summary — all from the database (nothing hard-coded).
    """
    from core.models import BureauEtudeInfo

    project = get_object_or_404(StudyProject.objects.select_related("client"), pk=pk)
    phases = project.phases.order_by("order")

    bureau = BureauEtudeInfo.get_instance()  # singleton — never None

    return render(
        request,
        "etudes/project_print.html",
        {
            "project": project,
            "phases": phases,
            "bureau": bureau,
            # `institute` is already injected by the context_processors.institute_info
            # processor, so it is available in the template automatically.
        },
    )


@login_and_active_required
def project_create(request):
    is_rec = _is_receptionist(request.user)
    form = StudyProjectForm(request.POST or None, is_receptionist=is_rec)

    if request.method == "POST" and form.is_valid():
        project = form.save()
        messages.success(request, f"Projet « {project.title} » créé.")
        return redirect("etudes:project_detail", pk=project.pk)

    return render(
        request,
        "etudes/project_form.html",
        {"form": form, "action": "Nouveau projet"},
    )


@login_and_active_required
def project_edit(request, pk):
    project = get_object_or_404(StudyProject, pk=pk)
    is_rec = _is_receptionist(request.user)
    form = StudyProjectForm(
        request.POST or None, instance=project, is_receptionist=is_rec
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Projet mis à jour.")
        return redirect("etudes:project_detail", pk=pk)

    return render(
        request,
        "etudes/project_form.html",
        {"form": form, "action": "Modifier", "project": project},
    )


@admin_required
def project_close(request, pk):
    project = get_object_or_404(StudyProject, pk=pk)

    if not project.can_be_closed():
        messages.error(
            request,
            "Toutes les phases doivent être terminées avant de clôturer le projet.",
        )
        return redirect("etudes:project_detail", pk=pk)

    form = ProjectCloseForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        project.status = StudyProject.STATUS_COMPLETED
        project.actual_end_date = form.cleaned_data["actual_end_date"]
        if form.cleaned_data.get("notes"):
            project.notes = (project.notes + "\n" + form.cleaned_data["notes"]).strip()
        project.save(update_fields=["status", "actual_end_date", "notes"])
        messages.success(request, f"Projet « {project.title} » clôturé.")
        return redirect("etudes:project_detail", pk=pk)

    return render(
        request,
        "etudes/project_close.html",
        {"form": form, "project": project},
    )


@admin_required
def project_cancel(request, pk):
    project = get_object_or_404(StudyProject, pk=pk)
    form = ProjectCancelForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        project.status = StudyProject.STATUS_CANCELLED
        reason = form.cleaned_data["reason"]
        project.notes = (project.notes + "\nAnnulation: " + reason).strip()
        project.save(update_fields=["status", "notes"])
        messages.success(request, f"Projet « {project.title} » annulé.")
        return redirect("etudes:project_detail", pk=pk)

    return render(
        request,
        "etudes/project_cancel.html",
        {"form": form, "project": project},
    )


# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------


@admin_required
def phase_add(request, project_pk):
    project = get_object_or_404(StudyProject, pk=project_pk)
    form = ProjectPhaseForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        phase = form.save(commit=False)
        phase.project = project
        phase.save()
        messages.success(request, f"Phase « {phase.name} » ajoutée.")
        return redirect("etudes:project_detail", pk=project_pk)

    return render(
        request,
        "etudes/phase_form.html",
        {"form": form, "project": project, "action": "Ajouter une phase"},
    )


@admin_required
def phase_edit(request, project_pk, pk):
    project = get_object_or_404(StudyProject, pk=project_pk)
    phase = get_object_or_404(ProjectPhase, pk=pk, project=project)
    form = ProjectPhaseForm(request.POST or None, instance=phase)

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Phase mise à jour.")
        return redirect("etudes:project_detail", pk=project_pk)

    return render(
        request,
        "etudes/phase_form.html",
        {"form": form, "project": project, "action": "Modifier la phase"},
    )


@admin_required
def phase_update_status(request, project_pk, pk):
    project = get_object_or_404(StudyProject, pk=project_pk)
    phase = get_object_or_404(ProjectPhase, pk=pk, project=project)
    form = PhaseStatusForm(request.POST or None, current_status=phase.status)

    if request.method == "POST" and form.is_valid():
        phase.status = form.cleaned_data["status"]
        if form.cleaned_data.get("completion_date"):
            phase.completion_date = form.cleaned_data["completion_date"]
        if form.cleaned_data.get("actual_hours") is not None:
            phase.actual_hours = form.cleaned_data["actual_hours"]
        phase.save()
        messages.success(request, f"Statut de la phase mis à jour.")
        return redirect("etudes:project_detail", pk=project_pk)

    return render(
        request,
        "etudes/phase_status_form.html",
        {"form": form, "project": project, "phase": phase},
    )


@admin_required
def phase_delete(request, project_pk, pk):
    if request.method != "POST":
        return redirect("etudes:project_detail", pk=project_pk)

    phase = get_object_or_404(ProjectPhase, pk=pk, project_id=project_pk)
    phase.delete()
    messages.success(request, "Phase supprimée.")
    return redirect("etudes:project_detail", pk=project_pk)


@admin_required
def phase_reorder(request, project_pk):
    """AJAX POST — reorder phases by accepting a comma-separated list of PKs."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed."}, status=405)

    form = PhaseReorderForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"error": form.errors}, status=400)

    ordered_ids = form.cleaned_data["ordered_ids"]
    project = get_object_or_404(StudyProject, pk=project_pk)

    # Validate all PKs belong to this project
    phases = list(ProjectPhase.objects.filter(project=project, pk__in=ordered_ids))
    if len(phases) != len(ordered_ids):
        return JsonResponse({"error": "Phases invalides."}, status=400)

    id_to_phase = {p.pk: p for p in phases}
    for order, phase_id in enumerate(ordered_ids, start=1):
        p = id_to_phase[phase_id]
        if p.order != order:
            p.order = order
            p.save(update_fields=["order"])

    return JsonResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Deliverables
# ---------------------------------------------------------------------------


@admin_required
def deliverable_add(request, project_pk, phase_pk):
    project = get_object_or_404(StudyProject, pk=project_pk)
    phase = get_object_or_404(ProjectPhase, pk=phase_pk, project=project)
    form = ProjectDeliverableForm(request.POST or None, request.FILES or None)

    if request.method == "POST" and form.is_valid():
        deliverable = form.save(commit=False)
        deliverable.phase = phase
        deliverable.save()
        messages.success(request, f"Livrable « {deliverable.title} » ajouté.")
        return redirect("etudes:project_detail", pk=project_pk)

    return render(
        request,
        "etudes/deliverable_form.html",
        {"form": form, "project": project, "phase": phase, "action": "Ajouter"},
    )


@admin_required
def deliverable_edit(request, project_pk, phase_pk, pk):
    project = get_object_or_404(StudyProject, pk=project_pk)
    phase = get_object_or_404(ProjectPhase, pk=phase_pk, project=project)
    deliverable = get_object_or_404(ProjectDeliverable, pk=pk, phase=phase)
    form = ProjectDeliverableForm(
        request.POST or None, request.FILES or None, instance=deliverable
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Livrable mis à jour.")
        return redirect("etudes:project_detail", pk=project_pk)

    return render(
        request,
        "etudes/deliverable_form.html",
        {"form": form, "project": project, "phase": phase, "action": "Modifier"},
    )


@admin_required
def deliverable_delete(request, project_pk, phase_pk, pk):
    if request.method != "POST":
        return redirect("etudes:project_detail", pk=project_pk)

    deliverable = get_object_or_404(
        ProjectDeliverable, pk=pk, phase__project_id=project_pk
    )
    deliverable.delete()
    messages.success(request, "Livrable supprimé.")
    return redirect("etudes:project_detail", pk=project_pk)


@admin_required
def deliverable_approve(request, project_pk, phase_pk, pk):
    project = get_object_or_404(StudyProject, pk=project_pk)
    phase = get_object_or_404(ProjectPhase, pk=phase_pk, project=project)
    deliverable = get_object_or_404(ProjectDeliverable, pk=pk, phase=phase)
    form = DeliverableApproveForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        deliverable.client_approved = form.cleaned_data["client_approved"] == "true"
        if form.cleaned_data.get("notes"):
            deliverable.notes = (
                deliverable.notes + "\n" + form.cleaned_data["notes"]
            ).strip()
        deliverable.save(update_fields=["client_approved", "notes"])
        decision = "approuvé" if deliverable.client_approved else "refusé"
        messages.success(request, f"Livrable {decision} par le client.")
        return redirect("etudes:project_detail", pk=project_pk)

    return render(
        request,
        "etudes/deliverable_approve.html",
        {
            "form": form,
            "project": project,
            "phase": phase,
            "deliverable": deliverable,
        },
    )


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


@admin_required
def etudes_analytics(request):
    from django.db.models import Avg, Count, Sum

    projects = StudyProject.objects.select_related("client").all()

    total = projects.count()
    by_status = projects.values("status").annotate(count=Count("id"))
    by_priority = projects.values("priority").annotate(count=Count("id"))

    in_progress = projects.filter(status=StudyProject.STATUS_IN_PROGRESS)
    overdue = [p for p in in_progress if p.is_overdue]

    budget_total = projects.aggregate(total=Sum("budget"))["total"] or 0

    return render(
        request,
        "etudes/analytics.html",
        {
            "total": total,
            "by_status": by_status,
            "by_priority": by_priority,
            "overdue": overdue,
            "budget_total": budget_total,
            "projects": projects,
        },
    )


# ─── ADD THESE TO etudes/views.py ────────────────────────────────────────── #

from django.http import JsonResponse
from django.views.decorators.http import require_GET


@admin_required
@require_GET
def api_project_list(request):
    """
    Return active study projects for the line-item source selector.
    Optionally filter by ?q= for live search.
    """
    q = request.GET.get("q", "").strip()
    qs = (
        StudyProject.objects.select_related("client")
        .filter(status=StudyProject.STATUS_IN_PROGRESS)
        .order_by("title")
    )
    if q:
        from django.db.models import Q

        qs = qs.filter(Q(title__icontains=q) | Q(client__name__icontains=q))

    data = [
        {
            "id": p.pk,
            "title": p.title,
            "client": p.client.name,
            "label": f"{p.title} — {p.client.name}",
            "description": p.title,
            "budget": str(p.budget),
            "project_type": p.project_type,
        }
        for p in qs
    ]
    return JsonResponse({"results": data})


@admin_required
@require_GET
def api_project_detail(request, pk):
    """Return a single project's prepopulation data."""
    p = get_object_or_404(StudyProject, pk=pk)
    return JsonResponse(
        {
            "id": p.pk,
            "title": p.title,
            "client": p.client.name,
            "description": p.title,
            "budget": str(p.budget),
            "project_type": p.project_type,
        }
    )
