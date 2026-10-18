from django.contrib.auth import get_user_model
from django.db.models import Q

from .models import Notification


def notify(users, message, link=""):
    """Send one in-app notification to each user in `users` (duplicates ignored)."""
    unique = {u.pk: u for u in users}.values()
    Notification.objects.bulk_create(
        [Notification(user=u, message=message[:300], link=link) for u in unique]
    )


def managers():
    User = get_user_model()
    return User.objects.filter(Q(role="admin") | Q(is_superuser=True)).distinct()


def residents(exclude=None):
    User = get_user_model()
    qs = User.objects.filter(role="resident", is_superuser=False)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs
