from django.db.models import Prefetch

from .models import Credit


def with_display_data(queryset, prefix=""):
    """Prefetch everything the film serializers read, avoiding N+1 queries."""
    return queryset.prefetch_related(
        f"{prefix}translations",
        f"{prefix}genres__translations",
        Prefetch(f"{prefix}credits", queryset=Credit.objects.select_related("person")),
    )
