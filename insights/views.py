from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import manager_required
from core.models import Location
from inventory.models import ItemLoan
from reports.models import Report

from .services import (
    CATEGORY_LABEL, find_hotspots, hotspots_with_insights, refresh_insight,
)


def _params(request):
    try:
        days = max(7, min(365, int(request.GET.get("days", 60))))
        threshold = max(2, min(20, int(request.GET.get("min", 3))))
    except ValueError:
        days, threshold = 60, 3
    return days, threshold


@manager_required
def insights_home(request):
    days, threshold = _params(request)
    return render(
        request, "insights/home.html",
        {"hotspots": hotspots_with_insights(days, threshold), "days": days, "threshold": threshold},
    )


@manager_required
@require_POST
def analyse(request):
    """'Analyse now': write a fresh conclusion for every hotspot."""
    days, threshold = _params(request)
    spots = find_hotspots(days, threshold)
    for h in spots:
        refresh_insight(h)
    messages.success(request, f"Analysed {len(spots)} hotspot(s).")
    return redirect(f"/manage/insights/?days={days}&min={threshold}")


@manager_required
def proposal(request, location_id, category):
    """A printable, evidence-backed upgrade proposal for one hotspot."""
    days, threshold = _params(request)
    location = get_object_or_404(Location, pk=location_id)
    hot = [h for h in find_hotspots(days, 1)
           if h["location_id"] == location.pk and h["category"] == category]
    if not hot:
        messages.error(request, "No reports found for that place and problem.")
        return redirect("insights_home")
    h = hot[0]
    insight = refresh_insight(h) if request.GET.get("refresh") else None
    if insight is None:
        from .models import Insight
        insight = Insight.objects.filter(location=location, category=category).first() or refresh_insight(h)
    reports = Report.objects.filter(location=location, category=category).select_related("reporter")
    return render(
        request, "insights/proposal.html",
        {"h": h, "insight": insight, "reports": reports, "location": location,
         "category_label": CATEGORY_LABEL.get(category, category)},
    )


@manager_required
def dashboard(request):
    """Township health at a glance (managers' home page)."""
    all_reports = Report.objects.all()
    total = all_reports.count()
    resolved = all_reports.filter(status="resolved")
    resolved_n = resolved.count()
    durations = [(r.resolved_at - r.created_at).total_seconds() / 3600
                 for r in resolved if r.resolved_at]
    avg_hours = round(sum(durations) / len(durations), 1) if durations else None

    by_location = {}
    for r in all_reports.filter(status__in=["received", "verified", "assigned", "in_progress"]).select_related("location"):
        by_location[r.location.name] = by_location.get(r.location.name, 0) + 1
    top_places = sorted(by_location.items(), key=lambda kv: -kv[1])[:6]
    most = top_places[0][1] if top_places else 1

    overdue = [l for l in ItemLoan.objects.filter(returned_at__isnull=True) if l.is_overdue]
    return render(
        request, "insights/dashboard.html",
        {
            "total": total,
            "open_n": total - resolved_n,
            "resolved_n": resolved_n,
            "resolve_rate": round(100 * resolved_n / total) if total else 0,
            "avg_hours": avg_hours,
            "priority_open": [r for r in all_reports.exclude(status="resolved") if r.reporter.is_vulnerable],
            "hotspot_count": len(find_hotspots()),
            "top_places": [(n, c, round(100 * c / most)) for n, c in top_places],
            "overdue": overdue,
        },
    )
