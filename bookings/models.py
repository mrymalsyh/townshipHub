from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import DateTimeRangeField, RangeOperators
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Facility(models.Model):
    """A space people can book: hall, BBQ pit, pool, badminton court..."""

    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=300, blank=True)
    capacity = models.PositiveIntegerField(default=10)
    location = models.ForeignKey(
        "core.Location", on_delete=models.SET_NULL, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "facilities"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def current_block(self):
        """Is there maintenance/cleaning happening right now?"""
        now = timezone.now()
        return self.blocks.filter(starts_at__lte=now, ends_at__gt=now).first()

    def upcoming_blocks(self):
        return self.blocks.filter(ends_at__gt=timezone.now()).order_by("starts_at")[:5]


class MaintenanceBlock(models.Model):
    """Pool cleaning, repainting... nobody can book while this is active."""

    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="blocks")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=200, default="Cleaning")

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return f"{self.facility}: {self.reason}"


class Booking(models.Model):
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    facility = models.ForeignKey(Facility, on_delete=models.CASCADE, related_name="bookings")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings"
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    purpose = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_CONFIRMED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["starts_at"]
        constraints = [
            # The database itself refuses two confirmed bookings that overlap
            # on the same facility. Even two people clicking at the same
            # instant cannot double-book.
            ExclusionConstraint(
                name="no_double_booking",
                expressions=[
                    (
                        models.Func(
                            "starts_at", "ends_at", function="tstzrange",
                            output_field=DateTimeRangeField(),
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                    ("facility", RangeOperators.EQUAL),
                ],
                condition=Q(status="confirmed"),
            ),
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")), name="booking_ends_after_start"
            ),
        ]

    def __str__(self):
        return f"{self.facility} {self.starts_at:%d %b %H:%M}"

    @property
    def is_upcoming(self):
        return self.status == self.STATUS_CONFIRMED and self.ends_at > timezone.now()
