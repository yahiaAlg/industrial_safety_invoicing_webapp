from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("reporting.urls", namespace="reporting")),
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("clients/", include("clients.urls", namespace="clients")),
    path("formations/", include("formations.urls", namespace="formations")),
    path("etudes/", include("etudes.urls", namespace="etudes")),
    path("financial/", include("financial.urls", namespace="financial")),
    path("resources/", include("resources.urls", namespace="resources")),
    path("core/", include("core.urls", namespace="core")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


if settings.DEBUG:
    import debug_toolbar

    urlpatterns = [
        path("__debug__/", include(debug_toolbar.urls)),
    ] + urlpatterns
