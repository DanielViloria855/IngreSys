"""Rutas raíz de ingreSys."""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "ingreSys · Administración"
admin.site.site_title = "ingreSys"
admin.site.index_title = "Gestión del sistema"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.infrastructure.urls")),
    path("staff/", include("apps.accounts.infrastructure.staff_urls")),
    path("entries/", include("apps.entries.infrastructure.urls")),
    path("analytics/", include("apps.analytics.infrastructure.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
