from django.conf import settings
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def health(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("films.urls")),
    path("api/v1/", include("suggestions.urls")),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/v1/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]

if settings.DEBUG and getattr(settings, "MEDIA_URL", None):
    from .media import serve_media

    # Local audio files in development; production uses Spaces.
    urlpatterns.append(
        path(f"{settings.MEDIA_URL.lstrip('/')}<path:path>", serve_media)
    )
