from .models import Notification


def unread_count(request):
    """Makes {{ unread_count }} available in every template (the bell badge)."""
    if request.user.is_authenticated:
        count = Notification.objects.filter(user=request.user, is_read=False).count()
    else:
        count = 0
    return {"unread_count": count}
