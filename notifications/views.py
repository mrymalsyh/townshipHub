from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def notification_list(request):
    items = list(Notification.objects.filter(user=request.user)[:100])
    return render(request, "notifications/list.html", {"items": items})


@login_required
@require_POST
def mark_all_read(request):
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return redirect("notification_list")


@login_required
def badge(request):
    """Tiny JSON endpoint; the page asks it every 30 seconds for new alerts."""
    count = Notification.objects.filter(user=request.user, is_read=False).count()
    latest = Notification.objects.filter(user=request.user, is_read=False).first()
    return JsonResponse(
        {"count": count, "latest": latest.message if latest else "", "link": latest.link if latest else ""}
    )
