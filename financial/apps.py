from django.apps import AppConfig


class FinancialConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "financial"
    verbose_name = "Financier"

    def ready(self):
        import financial.signals  # noqa: F401 — connects all signal receivers
