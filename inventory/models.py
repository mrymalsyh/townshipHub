from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class Item(models.Model):
    """Something management lends out: tables, chairs, projector, ladder..."""

    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=300, blank=True)
    total_quantity = models.PositiveIntegerField(default=1, help_text="Units owned")
    out_of_service = models.PositiveIntegerField(
        default=0, help_text="Units currently broken / being repaired"
    )
    replacement_cost = models.DecimalField(
        "Cost to replace one (RM)", max_digits=9, decimal_places=2, default=0
    )
    repair_cost = models.DecimalField(
        "Typical repair cost (RM)", max_digits=9, decimal_places=2, default=0
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def on_loan(self):
        total = self.loans.filter(returned_at__isnull=True).aggregate(s=Sum("quantity"))["s"]
        return total or 0

    @property
    def available(self):
        return max(
            0,
            self.total_quantity
            - self.out_of_service
            - self.on_loan
            - self.queue_entries.filter(status=ItemWaitlist.STATUS_READY).count(),
        )

    @property
    def damaged_returns(self):
        return self.loans.filter(return_condition="damaged").count()

    @property
    def borrow_count(self):
        return self.loans.count()

    @property
    def advice(self):
        """Simple repair-or-replace hint for management, built from the return history."""
        n = self.damaged_returns
        if n < 2:
            return ""
        repairs = n * self.repair_cost
        if self.replacement_cost and repairs >= self.replacement_cost:
            return (f"Damaged {n} times. Repairs so far (about RM {repairs:.0f}) cost as much as "
                    f"a new one (RM {self.replacement_cost:.0f}). Consider REPLACING.")
        return f"Damaged {n} times. Keep an eye on it; repair is still cheaper than replacing."


class ItemLoan(models.Model):
    CONDITION_CHOICES = [
        ("good", "Returned OK"),
        ("needs_cleaning", "Needs cleaning"),
        ("damaged", "Damaged / broken"),
        ("missing", "Missing / not returned"),
        ("unused", "Unused (never opened)"),
    ]

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="loans")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="loans"
    )
    quantity = models.PositiveIntegerField(default=1)
    purpose = models.CharField(max_length=200, blank=True)
    borrowed_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField()
    returned_at = models.DateTimeField(null=True, blank=True)
    extension_count = models.PositiveSmallIntegerField(default=0)
    return_condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, blank=True)
    admin_notes = models.CharField(max_length=300, blank=True)
    return_photo = models.ImageField(upload_to="returns/", blank=True)

    class Meta:
        ordering = ["-borrowed_at"]

    def __str__(self):
        return f"{self.quantity} x {self.item} to {self.user}"

    @property
    def is_returned(self):
        return self.returned_at is not None

    @property
    def is_overdue(self):
        return not self.is_returned and self.due_at < timezone.now()


class ItemLocker(models.Model):
    """A return locker configured by management; no hardware integration is implied."""

    name = models.CharField(max_length=80, unique=True)
    location_description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ItemWaitlist(models.Model):
    STATUS_WAITING = "waiting"
    STATUS_READY = "ready"
    STATUS_FULFILLED = "fulfilled"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_WAITING, "Waiting"),
        (STATUS_READY, "Ready for collection"),
        (STATUS_FULFILLED, "Collected"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="queue_entries")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="item_waitlist_entries"
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_WAITING)
    locker = models.ForeignKey(
        ItemLocker, on_delete=models.SET_NULL, null=True, blank=True, related_name="transfers"
    )
    pickup_code = models.CharField(max_length=6, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ready_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["item", "user"],
                condition=models.Q(status__in=["waiting", "ready"]),
                name="one_active_item_queue_per_user",
            )
        ]

    def __str__(self):
        return f"{self.item} for {self.user} ({self.get_status_display()})"


class ItemReturn(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_FLAGGED = "flagged"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending admin inspection"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_FLAGGED, "Flagged for follow-up"),
    ]
    DESTINATION_OFFICE = "office"
    DESTINATION_LOCKER = "locker"
    DESTINATION_TRANSFER = "transfer"
    DESTINATION_CHOICES = [
        (DESTINATION_OFFICE, "Management desk"),
        (DESTINATION_LOCKER, "Smart locker / return box"),
        (DESTINATION_TRANSFER, "Next-in-line locker transfer"),
    ]

    loan = models.OneToOneField(ItemLoan, on_delete=models.CASCADE, related_name="return_ticket")
    destination = models.CharField(max_length=12, choices=DESTINATION_CHOICES)
    locker = models.ForeignKey(
        ItemLocker, on_delete=models.SET_NULL, null=True, blank=True, related_name="returns"
    )
    return_code = models.CharField(max_length=6, blank=True)
    cleaned = models.BooleanField(default=False)
    accessories_included = models.BooleanField(default=False)
    maintenance_requested = models.BooleanField(default=False)
    evidence = models.FileField(upload_to="returns/evidence/")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_PENDING)
    condition = models.CharField(max_length=20, choices=ItemLoan.CONDITION_CHOICES, blank=True)
    notes = models.CharField(max_length=300, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="verified_item_returns",
    )

    class Meta:
        ordering = ["submitted_at"]

    def __str__(self):
        return f"Return #{self.pk}: {self.loan.item}"


class ItemMaintenance(models.Model):
    STATUS_OPEN = "open"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = [(STATUS_OPEN, "Open"), (STATUS_RESOLVED, "Resolved")]

    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="maintenance_issues")
    loan = models.ForeignKey(
        ItemLoan, on_delete=models.SET_NULL, null=True, blank=True, related_name="maintenance_issues"
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="item_issues"
    )
    description = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.item}: {self.get_status_display()}"
