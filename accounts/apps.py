# =============================================================================
# accounts/apps.py
# =============================================================================

from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "accounts"
    verbose_name = "Comptes utilisateurs"

    def ready(self):
        import accounts.signals  # noqa: F401
