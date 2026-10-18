from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("reports/", include("reports.urls")),
    path("bookings/", include("bookings.urls")),
    path("items/", include("inventory.urls")),
    path("notifications/", include("notifications.urls")),
    path("manage/insights/", include("insights.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
