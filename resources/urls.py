# ============================================================
# resources/urls.py
# ============================================================

from django.urls import path
from resources import views

app_name = "resources"

urlpatterns = [
    # --- Trainers ---
    path("trainers/", views.trainer_list, name="trainer_list"),
    path("trainers/create/", views.trainer_create, name="trainer_create"),
    path("trainers/<int:pk>/", views.trainer_detail, name="trainer_detail"),
    path("trainers/<int:pk>/edit/", views.trainer_edit, name="trainer_edit"),
    path(
        "trainers/<int:pk>/deactivate/",
        views.trainer_deactivate,
        name="trainer_deactivate",
    ),
    # --- Rooms ---
    path("rooms/", views.room_list, name="room_list"),
    path("rooms/create/", views.room_create, name="room_create"),
    path("rooms/<int:pk>/", views.room_detail, name="room_detail"),
    path("rooms/<int:pk>/edit/", views.room_edit, name="room_edit"),
    path("rooms/<int:pk>/deactivate/", views.room_deactivate, name="room_deactivate"),
    path(
        "rooms/<int:pk>/availability/",
        views.room_availability,
        name="room_availability",
    ),  # JsonResponse
    # --- Equipment ---
    path("equipment/", views.equipment_list, name="equipment_list"),
    path("equipment/create/", views.equipment_create, name="equipment_create"),
    path("equipment/<int:pk>/", views.equipment_detail, name="equipment_detail"),
    path("equipment/<int:pk>/edit/", views.equipment_edit, name="equipment_edit"),
    path(
        "equipment/<int:pk>/status/",
        views.equipment_update_status,
        name="equipment_update_status",
    ),
    # Equipment usage log
    path("equipment/<int:equipment_pk>/usages/add/", views.usage_add, name="usage_add"),
    path(
        "equipment/<int:equipment_pk>/usages/<int:pk>/edit/",
        views.usage_edit,
        name="usage_edit",
    ),
    path(
        "equipment/<int:equipment_pk>/usages/<int:pk>/delete/",
        views.usage_delete,
        name="usage_delete",
    ),
    # Equipment bookings
    path(
        "equipment/<int:equipment_pk>/bookings/add/",
        views.booking_add,
        name="booking_add",
    ),
    path(
        "equipment/<int:equipment_pk>/bookings/<int:pk>/edit/",
        views.booking_edit,
        name="booking_edit",
    ),
    path(
        "equipment/<int:equipment_pk>/bookings/<int:pk>/delete/",
        views.booking_delete,
        name="booking_delete",
    ),
    # Maintenance logs
    path(
        "equipment/<int:equipment_pk>/maintenance/add/",
        views.maintenance_add,
        name="maintenance_add",
    ),
    path(
        "equipment/<int:equipment_pk>/maintenance/<int:pk>/edit/",
        views.maintenance_edit,
        name="maintenance_edit",
    ),
    path(
        "equipment/<int:equipment_pk>/maintenance/<int:pk>/delete/",
        views.maintenance_delete,
        name="maintenance_delete",
    ),
    # --- Analytics ---
    path("equipment/analytics/", views.equipment_analytics, name="equipment_analytics"),
    path(
        "equipment/analytics/utilization/",
        views.utilization_report,
        name="utilization_report",
    ),
    path(
        "equipment/analytics/idle/",
        views.idle_equipment_report,
        name="idle_equipment_report",
    ),
    path(
        "equipment/availability-check/",
        views.equipment_availability_check,
        name="equipment_availability_check",
    ),  # JsonResponse
]
