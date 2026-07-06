# clients/views.py  —  v3.2
# Changed: client_create redirects to formations:session_create?client={pk}
#          to support the guided create workflow.

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from clients.forms import (
    ClientContactForm,
    ClientFilterForm,
    ClientForm,
    FormeJuridiqueForm,
)
from clients.models import Client, ClientContact, FormeJuridique
from core.utils import admin_required, login_and_active_required


# ─────────────────────────────────────────────────────────────────────────── #
# Clients — CRUD
# ─────────────────────────────────────────────────────────────────────────── #


@login_and_active_required
def client_list(request):
    qs = Client.objects.select_related("forme_juridique").all()
    form = ClientFilterForm(request.GET or None)

    if form.is_valid():
        q = form.cleaned_data.get("q")
        client_type = form.cleaned_data.get("client_type")
        is_active = form.cleaned_data.get("is_active")
        is_tva_exempt = form.cleaned_data.get("is_tva_exempt")

        if q:
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(city__icontains=q)
                | Q(activity_sector__icontains=q)
                | Q(contact_name__icontains=q)
                | Q(nif__icontains=q)
                | Q(rc__icontains=q)
            )
        if client_type:
            qs = qs.filter(client_type=client_type)
        if is_active == "1":
            qs = qs.filter(is_active=True)
        elif is_active == "0":
            qs = qs.filter(is_active=False)
        if is_tva_exempt == "1":
            qs = qs.filter(is_tva_exempt=True)
        elif is_tva_exempt == "0":
            qs = qs.filter(is_tva_exempt=False)

        has_balance = form.cleaned_data.get("has_balance")
        if has_balance == "yes":
            qs = [c for c in qs if c.has_outstanding_balance]
        elif has_balance == "no":
            qs = [c for c in qs if not c.has_outstanding_balance]

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    return render(
        request, "clients/client_list.html", {"page_obj": page_obj, "filter_form": form}
    )


@login_and_active_required
def client_detail(request, pk):
    client = get_object_or_404(Client.objects.select_related("forme_juridique"), pk=pk)
    contacts = client.contacts.all()
    return render(
        request,
        "clients/client_detail.html",
        {
            "client": client,
            "contacts": contacts,
            "missing_fields": client.missing_fields_for_invoice(),
        },
    )


@login_and_active_required
def client_create(request):
    form = ClientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        client = form.save()
        messages.success(
            request, f"Client « {client.name} » créé. Créez maintenant une formation."
        )
        url = reverse("formations:formation_create") + f"?client={client.pk}"
        return redirect(url)
    return render(
        request, "clients/client_form.html", {"form": form, "action": "Nouveau client"}
    )


@login_and_active_required
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    form = ClientForm(request.POST or None, instance=client)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Client mis à jour.")
        return redirect("clients:client_detail", pk=pk)
    return render(
        request,
        "clients/client_form.html",
        {"form": form, "action": "Modifier", "client": client},
    )


@admin_required
def client_deactivate(request, pk):
    if request.method != "POST":
        return redirect("clients:client_detail", pk=pk)
    client = get_object_or_404(Client, pk=pk)
    client.is_active = not client.is_active
    client.save(update_fields=["is_active"])
    state = "activé" if client.is_active else "désactivé"
    messages.success(request, f"Client « {client.name} » {state}.")
    return redirect("clients:client_detail", pk=pk)


@admin_required
def client_delete(request, pk):
    client = get_object_or_404(Client, pk=pk)

    from financial.models import Invoice
    from formations.models import Session
    from etudes.models import StudyProject

    invoice_count = Invoice.objects.filter(client=client).count()
    session_count = Session.objects.filter(client=client).count()
    project_count = StudyProject.objects.filter(client=client).count()
    has_related = invoice_count or session_count or project_count

    if request.method == "POST":
        name = client.name
        client.delete()
        messages.success(request, f"Client « {name} » supprimé définitivement.")
        return redirect("clients:client_list")

    return render(
        request,
        "clients/client_delete_confirm.html",
        {
            "client": client,
            "invoice_count": invoice_count,
            "session_count": session_count,
            "project_count": project_count,
            "has_related": has_related,
        },
    )


# ─────────────────────────────────────────────────────────────────────────── #
# Contacts — sub-resource
# ─────────────────────────────────────────────────────────────────────────── #


@login_and_active_required
def contact_add(request, client_pk):
    client = get_object_or_404(Client, pk=client_pk)
    form = ClientContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        contact = form.save(commit=False)
        contact.client = client
        contact.save()
        messages.success(request, "Contact ajouté.")
        return redirect("clients:client_detail", pk=client_pk)
    return render(
        request,
        "clients/contact_form.html",
        {"form": form, "client": client, "action": "Ajouter un contact"},
    )


@login_and_active_required
def contact_edit(request, client_pk, pk):
    client = get_object_or_404(Client, pk=client_pk)
    contact = get_object_or_404(ClientContact, pk=pk, client=client)
    form = ClientContactForm(request.POST or None, instance=contact)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Contact mis à jour.")
        return redirect("clients:client_detail", pk=client_pk)
    return render(
        request,
        "clients/contact_form.html",
        {"form": form, "client": client, "action": "Modifier le contact"},
    )


@login_and_active_required
def contact_delete(request, client_pk, pk):
    if request.method != "POST":
        return redirect("clients:client_detail", pk=client_pk)
    contact = get_object_or_404(ClientContact, pk=pk, client_id=client_pk)
    contact.delete()
    messages.success(request, "Contact supprimé.")
    return redirect("clients:client_detail", pk=client_pk)


# ─────────────────────────────────────────────────────────────────────────── #
# Forme juridique management  (admin only)
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def forme_juridique_list(request):
    formes = FormeJuridique.objects.all()
    return render(request, "clients/forme_juridique_list.html", {"formes": formes})


_COMMON_FORMS = [
    ("SPA", "Société par Actions"),
    ("SARL", "Société à Responsabilité Limitée"),
    ("EURL", "Entreprise Unipersonnelle à Responsabilité Limitée"),
    ("GIE", "Groupement d'Intérêt Économique"),
    ("SNC", "Société en Nom Collectif"),
    ("SNCI", "Société en Nom Collectif et en Industrie"),
    ("SCS", "Société en Commandite Simple"),
    ("SA", "Société Anonyme"),
]


def _fj_context(extra=None):
    ctx = {"common_forms_static": _COMMON_FORMS}
    if extra:
        ctx.update(extra)
    return ctx


@admin_required
def forme_juridique_create(request):
    form = FormeJuridiqueForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        fj = form.save()
        messages.success(request, f"Forme juridique « {fj.name} » ajoutée.")
        return redirect("clients:forme_juridique_list")
    return render(
        request,
        "clients/forme_juridique_form.html",
        _fj_context({"form": form, "action": "Nouvelle forme juridique"}),
    )


@admin_required
def forme_juridique_edit(request, pk):
    fj = get_object_or_404(FormeJuridique, pk=pk)
    form = FormeJuridiqueForm(request.POST or None, instance=fj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Forme juridique « {fj.name} » mise à jour.")
        return redirect("clients:forme_juridique_list")
    return render(
        request,
        "clients/forme_juridique_form.html",
        _fj_context({"form": form, "action": f"Modifier — {fj.name}", "fj": fj}),
    )


@admin_required
def forme_juridique_delete(request, pk):
    if not request.user.is_superuser:
        messages.error(request, "Action réservée aux super-administrateurs.")
        return redirect("clients:forme_juridique_list")

    fj = get_object_or_404(FormeJuridique, pk=pk)

    if fj.name == "Autre":
        messages.error(
            request,
            "La forme « Autre » est une valeur système et ne peut pas être supprimée.",
        )
        return redirect("clients:forme_juridique_list")

    client_count = fj.clients.count()

    if request.method == "POST":
        name = fj.name
        fj.delete()
        messages.success(request, f"Forme juridique « {name} » supprimée.")
        return redirect("clients:forme_juridique_list")

    return render(
        request,
        "clients/forme_juridique_delete_confirm.html",
        {"fj": fj, "client_count": client_count},
    )


# ─────────────────────────────────────────────────────────────────────────── #
# Activity history  (admin only)
# ─────────────────────────────────────────────────────────────────────────── #


@admin_required
def client_history(request, pk):
    client = get_object_or_404(Client, pk=pk)

    from financial.models import Invoice
    from formations.models import Session
    from etudes.models import StudyProject

    invoices = Invoice.objects.filter(
        client=client, phase=Invoice.Phase.FINALE
    ).order_by("-invoice_date")
    sessions = Session.objects.filter(client=client).order_by("-date_start")
    projects = StudyProject.objects.filter(client=client).order_by("-start_date")

    return render(
        request,
        "clients/client_history.html",
        {
            "client": client,
            "invoices": invoices,
            "sessions": sessions,
            "projects": projects,
        },
    )


# ─────────────────────────────────────────────────────────────────────────── #
# AJAX
# ─────────────────────────────────────────────────────────────────────────── #


@login_and_active_required
def client_search_ajax(request):
    q = request.GET.get("q", "").strip()
    if len(q) < 2:
        return JsonResponse({"results": []})
    clients = Client.objects.filter(name__icontains=q, is_active=True).values(
        "id", "name", "city", "client_type", "is_tva_exempt"
    )[:20]
    return JsonResponse({"results": list(clients)})
