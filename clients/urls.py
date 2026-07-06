# clients/urls.py  —  v3.1
# Added: forme-juridique management routes (admin only)

from django.urls import path
from clients import views

app_name = "clients"

urlpatterns = [
    # ── Clients CRUD ─────────────────────────────────────────────────── #
    path("", views.client_list, name="client_list"),
    path("create/", views.client_create, name="client_create"),
    path("<int:pk>/", views.client_detail, name="client_detail"),
    path("<int:pk>/edit/", views.client_edit, name="client_edit"),
    path("<int:pk>/deactivate/", views.client_deactivate, name="client_deactivate"),
    path("<int:pk>/delete/", views.client_delete, name="client_delete"),
    # ── Contacts ─────────────────────────────────────────────────────── #
    path("<int:client_pk>/contacts/add/", views.contact_add, name="contact_add"),
    path(
        "<int:client_pk>/contacts/<int:pk>/edit/",
        views.contact_edit,
        name="contact_edit",
    ),
    path(
        "<int:client_pk>/contacts/<int:pk>/delete/",
        views.contact_delete,
        name="contact_delete",
    ),
    # ── Activity history ─────────────────────────────────────────────── #
    path("<int:pk>/history/", views.client_history, name="client_history"),
    # ── Forme juridique management (admin only) ───────────────────────  #
    path("formes-juridiques/", views.forme_juridique_list, name="forme_juridique_list"),
    path(
        "formes-juridiques/create/",
        views.forme_juridique_create,
        name="forme_juridique_create",
    ),
    path(
        "formes-juridiques/<int:pk>/edit/",
        views.forme_juridique_edit,
        name="forme_juridique_edit",
    ),
    path(
        "formes-juridiques/<int:pk>/delete/",
        views.forme_juridique_delete,
        name="forme_juridique_delete",
    ),
    # ── AJAX ─────────────────────────────────────────────────────────── #
    path("search/", views.client_search_ajax, name="client_search_ajax"),
]
