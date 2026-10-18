from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone

from bookings.models import Booking, MaintenanceBlock
from reports.models import Report


@login_required
def home(request):
    if request.user.is_manager:
        return redirect("dashboard")
    now = timezone.now()
    rank = {"high": 0, "medium": 1, "low": 2}
    shared = sorted(
        Report.objects.filter(scope="outdoor").open().exclude(reporter=request.user)
        .select_related("location"),
        key=lambda r: (rank[r.urgency], -r.created_at.timestamp()),
    )
    return render(
        request, "core/home.html",
        {
            "my_open": Report.objects.filter(reporter=request.user).open()[:5],
            "alerts": shared[:3],
            "more_alerts": max(0, len(shared) - 3),
            "my_bookings": Booking.objects.filter(
                user=request.user, status="confirmed", ends_at__gt=now
            ).select_related("facility")[:4],
            "closures": MaintenanceBlock.objects.filter(ends_at__gt=now).select_related("facility")[:4],
        },
    )
