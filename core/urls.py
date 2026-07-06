# ============================================================
# core/urls.py
# ============================================================

from django.urls import path
from core import views

app_name = "core"

urlpatterns = [
    # Institute general info
    path("institute/", views.institute_info_edit, name="institute_info"),
    # Formation centre config
    path("formation-info/", views.formation_info_edit, name="formation_info"),
    # Bureau d'étude config
    path("bureau-info/", views.bureau_info_edit, name="bureau_info"),
]
