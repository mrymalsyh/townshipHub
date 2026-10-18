from datetime import datetime, time, timedelta
from math import asin, cos, radians, sin, sqrt
import re

from bookings.models import Booking, Facility, MaintenanceBlock
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Prefetch, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import manager_required
from core.models import Location
from insights.models import Insight
from insights.services import find_hotspots, rule_based_writeup
from notifications.services import managers, notify

from .forms import ReportForm, StatusUpdateForm, TipForm
from .models import Report, ReportConfirmation
from .services import after_report_created, apply_status_update


@login_required
def report_list(request):
    mine = Report.objects.filter(reporter=request.user)
    community = Report.objects.filter(scope="outdoor").open().exclude(reporter=request.user)
    return render(request, "reports/list.html", {"mine": mine, "community": community})


@login_required
def report_create(request):
    initial = {}
    # A QR code on a bench or lift can point to /reports/new/?location=ID to pre-fill the place.
    loc_id = request.GET.get("location")
    if loc_id and Location.objects.filter(pk=loc_id).exists():
        initial["location"] = loc_id
    form = ReportForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        report = form.save(commit=False)
        report.reporter = request.user
        report.save()
        after_report_created(report)
        messages.success(request, "Report sent. You earned 5 care points!")
        return redirect(report)
    return render(request, "reports/form.html", {"form": form})


@login_required
def report_detail(request, pk):
    report = get_object_or_404(Report.objects.visible_to(request.user), pk=pk)
    my_vote = ReportConfirmation.objects.filter(report=report, user=request.user).first()
    context = {
        "report": report,
        "tracker": report.tracker(),
        "updates": report.updates.select_related("author"),
        "tips": report.tips.select_related("author"),
        "tip_form": TipForm(),
        "my_vote": my_vote,
        "can_vote": report.is_outdoor and report.reporter != request.user,
        "broken_count": report.still_broken_count,
        "fixed_count": report.fixed_count,
    }
    if request.user.is_manager:
        context["update_form"] = StatusUpdateForm(
            initial={"status": report.status, "alternative_route": report.alternative_route}
        )
    return render(request, "reports/detail.html", context)


@login_required
@require_POST
def report_confirm(request, pk):
    report = get_object_or_404(Report.objects.visible_to(request.user), pk=pk, scope="outdoor")
    if report.reporter == request.user:
        raise Http404
    still_broken = request.POST.get("answer") == "broken"
    _, created = ReportConfirmation.objects.update_or_create(
        report=report, user=request.user, defaults={"still_broken": still_broken}
    )
    if created:
        request.user.add_points(2)

    link = report.get_absolute_url()
    if not still_broken and report.is_open and report.fixed_count >= 3:
        notify(managers(), f"3+ residents say '{report.title}' looks fixed. Please verify and close.", link)
    if still_broken and not report.is_open:
        notify(managers(), f"A resident says '{report.title}' is STILL BROKEN after being marked resolved.", link)

    messages.success(request, "Thanks for letting us know!")
    return redirect(report)


@login_required
@require_POST
def report_tip(request, pk):
    report = get_object_or_404(Report.objects.visible_to(request.user), pk=pk, scope="outdoor")
    form = TipForm(request.POST)
    if form.is_valid():
        tip = form.save(commit=False)
        tip.report = report
        tip.author = request.user
        tip.save()
        request.user.add_points(3)
        messages.success(request, "Tip shared with your neighbours. +3 care points!")
    return redirect(report)


@manager_required
@require_POST
def report_update(request, pk):
    report = get_object_or_404(Report, pk=pk)
    form = StatusUpdateForm(request.POST)
    if form.is_valid():
        apply_status_update(
            report, request.user,
            form.cleaned_data["status"], form.cleaned_data["note"],
            form.cleaned_data["alternative_route"] if report.is_outdoor else None,
        )
        messages.success(request, "Report updated. The resident has been notified.")
    return redirect(report)


@manager_required
def manage_reports(request):
    qs = Report.objects.select_related("reporter", "location").annotate(
        broken_votes=Count("confirmations", filter=Q(confirmations__still_broken=True))
    )
    scope = request.GET.get("scope")
    if scope in ("indoor", "outdoor"):
        qs = qs.filter(scope=scope)
    show = request.GET.get("show", "open")
    if show == "open":
        qs = qs.open()
    reports = sorted(qs, key=lambda r: (not r.is_open, -r.priority_score, r.created_at))
    return render(request, "reports/manage.html", {"reports": reports, "scope": scope, "show": show})


@login_required
def report_map(request):
    """Public map of outdoor reports, clustered into interactive hotspots."""
    reports = list(
        Report.objects.filter(scope=Report.SCOPE_OUTDOOR)
        .select_related("location")
        .prefetch_related(
            Prefetch(
                "confirmations",
                queryset=ReportConfirmation.objects.filter(user=request.user),
                to_attr="map_user_confirmations",
            )
        )
        .order_by("-created_at")
    )
    pins = [
        {
            "id": report.pk,
            "name": report.location.name,
            "lat": report.location.latitude,
            "lng": report.location.longitude,
            "title": report.title,
            "spot": report.spot_detail,
            "category": report.category,
            "category_label": report.get_category_display(),
            "status": report.status,
            "status_label": report.get_status_display(),
            "urgency": report.urgency,
            "url": report.get_absolute_url(),
            "vote_url": reverse("report_confirm", args=[report.pk]),
            "can_vote": report.reporter_id != request.user.pk,
            "user_vote": (
                report.map_user_confirmations[0].still_broken
                if report.map_user_confirmations
                else None
            ),
            "route": report.alternative_route,
        }
        for report in reports
    ]

    alerts = _nearby_predictive_alerts(reports) if request.user.is_manager else []
    quick_zones = _map_quick_zones(request.user)
    announcements = _map_announcements()
    route_locations = {
        location.pk: {
            "id": location.pk,
            "name": location.name,
            "lat": location.latitude,
            "lng": location.longitude,
        }
        for location in Location.objects.filter(
            Q(reports__scope=Report.SCOPE_OUTDOOR)
            | Q(facility__is_active=True, facility__location__isnull=False)
        ).distinct().order_by("name")
    }
    return render(
        request,
        "reports/map.html",
        {
            "pins": pins,
            "predictive_alerts": alerts,
            "quick_zones": quick_zones,
            "announcements": announcements,
            "route_locations": list(route_locations.values()),
        },
    )


def _map_quick_zones(user):
    locations = list(Location.objects.filter(
        Q(reports__scope=Report.SCOPE_OUTDOOR)
        | Q(facility__is_active=True, facility__location__isnull=False)
    ).distinct().order_by("name"))
    facilities = list(
        Facility.objects.filter(is_active=True, location__isnull=False)
        .select_related("location")
        .prefetch_related("blocks")
        .order_by("name")
    )
    now = timezone.now()
    local_day = timezone.localdate()
    day_start = timezone.make_aware(datetime.combine(local_day, time.min))
    day_end = day_start + timedelta(days=1)
    today_blocks = list(
        MaintenanceBlock.objects.filter(starts_at__lt=day_end, ends_at__gt=day_start)
        .select_related("facility")
    )
    today_bookings = Booking.objects.filter(
        status=Booking.STATUS_CONFIRMED,
        starts_at__lt=day_end,
        ends_at__gt=day_start,
    )

    location_facilities = {}
    for facility in facilities:
        active_block = next(
            (block for block in facility.blocks.all() if block.starts_at <= now < block.ends_at),
            None,
        )
        blocks_today = [
            block for block in today_blocks
            if block.facility_id == facility.pk
        ]
        location_facilities.setdefault(facility.location_id, []).append({
            "name": facility.name,
            "url": reverse("facility_detail", args=[facility.pk]),
            "status": "Closed for maintenance" if active_block else "Open",
            "booking_count": today_bookings.filter(facility=facility).count(),
            "maintenance": [
                f"{block.reason}, {timezone.localtime(block.starts_at):%H:%M}–"
                f"{timezone.localtime(block.ends_at):%H:%M}"
                for block in blocks_today
            ],
        })

    block_match = re.search(r"\bBlock\s+([A-Za-z0-9-]+)", user.unit or "", re.IGNORECASE)
    block_name = f"Block {block_match.group(1)}" if block_match else ""
    resident_block = (
        Location.objects.filter(name__iexact=block_name).first()
        if block_name
        else None
    )
    definitions = [
        ("my-block", "🏠 My Block", lambda loc: bool(block_name) and loc.name.casefold() == block_name.casefold()),
        (
            "clubhouse-pool", "🏊 Clubhouse & Pool",
            lambda loc: "pool" in loc.name.casefold() or "clubhouse" in loc.name.casefold(),
        ),
        (
            "central-park", "🌳 Central Park",
            lambda loc: loc.kind == "park" or "central park" in loc.name.casefold(),
        ),
        (
            "commercial-center", "🛍️ Commercial Center",
            lambda loc: "commercial" in loc.name.casefold() or "shopping" in loc.name.casefold(),
        ),
        (
            "school-zone", "🏫 School Zone",
            lambda loc: "school" in loc.name.casefold(),
        ),
    ]

    zones = []
    for key, label, matches in definitions:
        location = next((candidate for candidate in locations if matches(candidate)), None)
        if key == "my-block" and location is None:
            location = resident_block
        zones.append({
            "key": key,
            "label": label,
            "available": location is not None,
            "lat": location.latitude if location else None,
            "lng": location.longitude if location else None,
            "location_name": location.name if location else "",
            "facilities": location_facilities.get(location.pk, []) if location else [],
        })
    return zones


def _map_announcements():
    now = timezone.now()
    local_day = timezone.localdate()
    day_start = timezone.make_aware(datetime.combine(local_day, time.min))
    day_end = day_start + timedelta(days=1)
    announcements = []

    for block in MaintenanceBlock.objects.filter(
        starts_at__lt=day_end, ends_at__gt=day_start
    ).select_related("facility", "facility__location").order_by("starts_at"):
        facility = block.facility
        when = "today"
        if block.starts_at > now:
            when = f"today, {timezone.localtime(block.starts_at):%H:%M}–{timezone.localtime(block.ends_at):%H:%M}"
        elif block.ends_at <= now:
            when = f"earlier today, until {timezone.localtime(block.ends_at):%H:%M}"
        announcements.append({
            "text": f"Maintenance at {facility.name} {when}: {block.reason}.",
            "url": reverse("facility_detail", args=[facility.pk]),
            "kind": "facility",
            "target_label": "View facility schedule",
            "lat": facility.location.latitude if facility.location_id else None,
            "lng": facility.location.longitude if facility.location_id else None,
        })

    for report in Report.objects.filter(
        scope=Report.SCOPE_OUTDOOR,
        alternative_route__gt="",
    ).open().select_related("location").order_by("-created_at")[:5]:
        announcements.append({
            "text": f"Detour notice at {report.location.name}: {report.alternative_route}",
            "url": report.get_absolute_url(),
            "kind": "report",
            "target_label": "View report and detour advice",
            "lat": report.location.latitude,
            "lng": report.location.longitude,
        })
    return announcements


def _distance_meters(first, second):
    radius = 6_371_000
    lat1, lat2 = radians(first.latitude), radians(second.latitude)
    delta_lat = lat2 - lat1
    delta_lng = radians(second.longitude - first.longitude)
    value = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lng / 2) ** 2
    return 2 * radius * asin(sqrt(value))


def _nearby_predictive_alerts(reports):
    since = timezone.now() - timedelta(days=14)
    recent = [report for report in reports if report.created_at >= since]
    if not recent:
        return []

    hotspots = [hotspot for hotspot in find_hotspots(days=14, threshold=3)
                if hotspot["scope"] == Report.SCOPE_OUTDOOR]
    if not hotspots:
        return []

    locations = {}
    for report in recent:
        locations.setdefault(report.location_id, report.location)

    hotspot_keys = {(hotspot["location_id"], hotspot["category"]) for hotspot in hotspots}
    insight_map = {
        (insight.location_id, insight.category): insight
        for insight in Insight.objects.filter(
            location_id__in=locations,
            category__in={category for _, category in hotspot_keys},
        )
    }

    candidates = []
    for center in locations.values():
        nearby_ids = {
            location_id
            for location_id, location in locations.items()
            if _distance_meters(center, location) <= 50
        }
        nearby_reports = [report for report in recent if report.location_id in nearby_ids]
        if len(nearby_reports) < 3:
            continue
        nearby_hotspots = [
            hotspot for hotspot in hotspots
            if hotspot["location_id"] in nearby_ids
        ]
        if not nearby_hotspots:
            continue
        nearby_hotspots.sort(key=lambda hotspot: hotspot["total"], reverse=True)
        top = nearby_hotspots[0]
        insight = insight_map.get((top["location_id"], top["category"]))
        action = insight.suggested_action if insight else rule_based_writeup(top)[1]
        candidates.append({
            "name": center.name,
            "count": len(nearby_reports),
            "action": action,
            "location_ids": nearby_ids,
        })

    candidates.sort(key=lambda alert: alert["count"], reverse=True)
    alerts = []
    covered_locations = set()
    for alert in candidates:
        new_locations = alert["location_ids"] - covered_locations
        if not new_locations:
            continue
        covered_locations.update(alert["location_ids"])
        alerts.append({
            "name": alert["name"],
            "count": alert["count"],
            "action": alert["action"],
        })
    return alerts
