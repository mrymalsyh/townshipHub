from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.decorators import manager_required
from core.models import Location
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
    """Public map of open outdoor problems. Several reports at one place share one pin."""
    pins = {}
    for r in Report.objects.filter(scope="outdoor").open().select_related("location"):
        pin = pins.setdefault(
            r.location_id,
            {"name": r.location.name, "lat": r.location.latitude, "lng": r.location.longitude, "reports": []},
        )
        pin["reports"].append(
            {"title": r.title, "urgency": r.urgency, "url": r.get_absolute_url()}
        )
    return render(request, "reports/map.html", {"pins": list(pins.values())})
