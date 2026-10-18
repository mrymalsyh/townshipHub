"""The 'what happens next' rules for reports live here, away from the views."""
from django.urls import reverse
from django.utils import timezone

from notifications.services import managers, notify, residents

from .models import Report, ReportUpdate


def after_report_created(report):
    """Called once, right after a resident submits a report."""
    link = reverse("report_detail", args=[report.pk])

    ReportUpdate.objects.create(
        report=report, author=report.reporter, status=Report.STATUS_RECEIVED,
        note="Report submitted",
    )
    report.reporter.add_points(5)

    # Management always hears about it. Vulnerable residents get flagged.
    flag = " [PRIORITY RESIDENT]" if report.reporter.is_vulnerable else ""
    notify(managers(), f"New {report.get_urgency_display().lower()} report: {report.title} "
                       f"at {report.location.name}{flag}", link)

    # Outdoor problems are a community alert: tell every other resident.
    if report.is_outdoor:
        notify(
            residents(exclude=report.reporter),
            f"Heads-up: {report.title} at {report.location.name}. Check the page for tips.",
            link,
        )


def apply_status_update(report, author, status, note="", alternative_route=None):
    """Management changes the status (and optionally posts an official alternative route)."""
    link = reverse("report_detail", args=[report.pk])
    route_changed = (
        alternative_route is not None
        and alternative_route.strip() != report.alternative_route.strip()
    )

    report.status = status
    if route_changed:
        report.alternative_route = alternative_route.strip()
    report.resolved_at = timezone.now() if status == Report.STATUS_RESOLVED else None
    report.save()

    ReportUpdate.objects.create(report=report, author=author, status=status, note=note)

    if report.reporter != author:
        notify([report.reporter], f"Update on your report '{report.title}': "
                                   f"{report.get_status_display()}", link)

    if report.is_outdoor:
        if status == Report.STATUS_RESOLVED:
            notify(residents(exclude=report.reporter),
                   f"Fixed: {report.title} at {report.location.name}", link)
        elif route_changed and report.alternative_route:
            notify(residents(),
                   f"New route advice for {report.location.name}: {report.alternative_route[:120]}",
                   link)
