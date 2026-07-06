# =============================================================================
# formations/apps.py
# =============================================================================

from django.apps import AppConfig


class FormationsConfig(AppConfig):
    name = "formations"
    verbose_name = "Formations"

    def ready(self):
        import formations.signals  # noqa: F401
