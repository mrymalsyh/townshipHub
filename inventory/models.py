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
        return max(0, self.total_quantity - self.out_of_service - self.on_loan)

    @property
    def damaged_returns(self):
        return self.loans.filter(return_condition="damaged").count()

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
