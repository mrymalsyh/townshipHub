from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse


class ReportQuerySet(models.QuerySet):
    def visible_to(self, user):
        """Managers see everything. Residents see every OUTDOOR report plus their own indoor ones."""
        if user.is_manager:
            return self
        return self.filter(Q(scope="outdoor") | Q(reporter=user))

    def open(self):
        return self.exclude(status="resolved")


class Report(models.Model):
    SCOPE_INDOOR = "indoor"
    SCOPE_OUTDOOR = "outdoor"
    SCOPE_CHOICES = [
        (SCOPE_INDOOR, "Inside my home / building (private)"),
        (SCOPE_OUTDOOR, "Outside, in a shared area (everyone can see)"),
    ]

    CATEGORY_CHOICES = [
        ("plumbing", "Plumbing / leak"),
        ("electrical", "Electrical"),
        ("pathway", "Pathway / road damage"),
        ("lighting", "Street light"),
        ("drainage", "Drain / flooding"),
        ("lift", "Lift"),
        ("cleanliness", "Rubbish / cleanliness"),
        ("pest", "Pests"),
        ("safety", "Safety hazard"),
        ("other", "Other"),
    ]

    URGENCY_CHOICES = [("low", "Low"), ("medium", "Medium"), ("high", "High - urgent")]

    STATUS_RECEIVED = "received"
    STATUS_VERIFIED = "verified"
    STATUS_ASSIGNED = "assigned"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = [
        (STATUS_RECEIVED, "Received"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_ASSIGNED, "Assigned to a team"),
        (STATUS_IN_PROGRESS, "Work in progress"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports"
    )
    location = models.ForeignKey("core.Location", on_delete=models.PROTECT, related_name="reports")
    spot_detail = models.CharField(
        "Exact spot", max_length=120, blank=True, help_text="e.g. Level 3 bathroom, or near the bench"
    )
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    scope = models.CharField(max_length=10, choices=SCOPE_CHOICES, default=SCOPE_OUTDOOR)
    urgency = models.CharField(max_length=10, choices=URGENCY_CHOICES, default="medium")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RECEIVED)
    photo = models.ImageField(upload_to="reports/", blank=True)
    alternative_route = models.TextField(
        blank=True, help_text="Official advice from management: what to do / where to go instead"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    objects = ReportQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"#{self.pk} {self.title}"

    def get_absolute_url(self):
        return reverse("report_detail", args=[self.pk])

    # ----- helpers -------------------------------------------------------
    @property
    def is_open(self):
        return self.status != self.STATUS_RESOLVED

    @property
    def is_outdoor(self):
        return self.scope == self.SCOPE_OUTDOOR

    @property
    def still_broken_count(self):
        if hasattr(self, "broken_votes"):  # filled in by an annotate() for speed
            return self.broken_votes
        return self.confirmations.filter(still_broken=True).count()

    @property
    def fixed_count(self):
        return self.confirmations.filter(still_broken=False).count()

    @property
    def priority_score(self):
        """Higher = handle sooner. Urgency + vulnerable resident + how many neighbours confirm it."""
        base = {"low": 10, "medium": 20, "high": 30}[self.urgency]
        if self.reporter.is_vulnerable:
            base += 15
        return base + 2 * self.still_broken_count

    def tracker(self):
        """Steps for the parcel-style progress bar."""
        keys = [k for k, _ in self.STATUS_CHOICES]
        current = keys.index(self.status)
        return [
            {"key": k, "label": label, "done": i <= current, "current": i == current}
            for i, (k, label) in enumerate(self.STATUS_CHOICES)
        ]


class ReportUpdate(models.Model):
    """One line of the public timeline: 'Assigned to plumbing team'."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="updates")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=Report.STATUS_CHOICES)
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class ReportConfirmation(models.Model):
    """A neighbour says 'still broken' or 'looks fixed'."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="confirmations")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    still_broken = models.BooleanField()
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["report", "user"], name="one_vote_per_user_per_report")
        ]


class ReportTip(models.Model):
    """A neighbour's tip, e.g. 'Use the back path behind Block B instead'."""

    report = models.ForeignKey(Report, on_delete=models.CASCADE, related_name="tips")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    text = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
