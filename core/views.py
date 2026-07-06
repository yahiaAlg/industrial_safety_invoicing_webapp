# core/views.py

from django.contrib import messages
from django.shortcuts import redirect, render

from core.forms import BureauEtudeInfoForm, FormationInfoForm, InstituteInfoForm
from core.models import BureauEtudeInfo, FormationInfo, InstituteInfo
from core.utils import admin_required


@admin_required
def institute_info_edit(request):
    instance = InstituteInfo.get_instance()
    form = InstituteInfoForm(
        request.POST or None, request.FILES or None, instance=instance
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Informations de l'institut mises à jour.")
        return redirect("core:institute_info")

    return render(
        request,
        "core/institute_info.html",
        {"form": form, "title": "Informations de l'Institut"},
    )


@admin_required
def formation_info_edit(request):
    instance = FormationInfo.get_instance()
    form = FormationInfoForm(
        request.POST or None, request.FILES or None, instance=instance
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Configuration du centre de formation mise à jour.")
        return redirect("core:formation_info")

    return render(
        request,
        "core/formation_info.html",
        {"form": form, "title": "Centre de Formation — Configuration"},
    )


@admin_required
def bureau_info_edit(request):
    instance = BureauEtudeInfo.get_instance()
    form = BureauEtudeInfoForm(
        request.POST or None, request.FILES or None, instance=instance
    )

    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Configuration du bureau d'étude mise à jour.")
        return redirect("core:bureau_info")

    return render(
        request,
        "core/bureau_info.html",
        {"form": form, "title": "Bureau d'Étude — Configuration"},
    )
