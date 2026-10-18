from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """A resident or a township manager (admin)."""

    ROLE_RESIDENT = "resident"
    ROLE_ADMIN = "admin"
    ROLE_CHOICES = [
        (ROLE_RESIDENT, "Resident"),
        (ROLE_ADMIN, "Township management"),
    ]

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=ROLE_RESIDENT)
    unit = models.CharField(
        "Unit / house", max_length=50, blank=True, help_text="e.g. Block C, 3-12"
    )
    phone = models.CharField(max_length=30, blank=True)
    is_vulnerable = models.BooleanField(
        "I would like priority help",
        default=False,
        help_text="Elderly, living alone, or special needs. Your urgent reports are handled first.",
    )
    points = models.PositiveIntegerField("Community care points", default=0)

    @property
    def is_manager(self):
        return self.role == self.ROLE_ADMIN or self.is_superuser

    def add_points(self, amount):
        """Give care points (never below zero)."""
        self.points = max(0, self.points + amount)
        self.save(update_fields=["points"])

    def __str__(self):
        return self.get_full_name() or self.username
