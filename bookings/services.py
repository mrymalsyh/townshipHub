from django.db import IntegrityError, transaction
from django.urls import reverse

from notifications.services import notify, residents

from .models import Booking, MaintenanceBlock


class BookingError(Exception):
    """A friendly message that can be shown straight to the resident."""


def create_booking(user, facility, starts_at, ends_at, purpose=""):
    if ends_at <= starts_at:
        raise BookingError("The end time must be after the start time.")
    if not facility.is_active:
        raise BookingError("This facility is not open for booking.")

    clash = facility.blocks.filter(starts_at__lt=ends_at, ends_at__gt=starts_at).first()
    if clash:
        raise BookingError(
            f"{facility.name} is closed for {clash.reason.lower()} "
            f"({clash.starts_at:%d %b %H:%M} to {clash.ends_at:%d %b %H:%M})."
        )

    try:
        # atomic() so a refused insert does not break the rest of the request
        with transaction.atomic():
            return Booking.objects.create(
                facility=facility, user=user, starts_at=starts_at, ends_at=ends_at, purpose=purpose
            )
    except IntegrityError:
        raise BookingError("Sorry, someone already booked that time. Please pick another slot.")


def cancel_booking(booking):
    booking.status = Booking.STATUS_CANCELLED
    booking.save(update_fields=["status"])


def announce_block(block):
    """Pool cleaning etc: warn people who already booked, and tell everyone else."""
    link = reverse("facility_detail", args=[block.facility_id])
    when = f"{block.starts_at:%d %b %H:%M} to {block.ends_at:%d %b %H:%M}"

    affected = Booking.objects.filter(
        facility=block.facility, status=Booking.STATUS_CONFIRMED,
        starts_at__lt=block.ends_at, ends_at__gt=block.starts_at,
    ).select_related("user")
    notify(
        [b.user for b in affected],
        f"Your booking at {block.facility.name} clashes with {block.reason.lower()} ({when}). "
        f"Please cancel it and pick a new time.",
        link,
    )
    affected_ids = {b.user_id for b in affected}
    notify(
        [u for u in residents() if u.pk not in affected_ids],
        f"{block.facility.name} will be closed for {block.reason.lower()}: {when}",
        link,
    )


def bookings_hit_by_blocks(bookings):
    """Which of these bookings now overlap a maintenance block? (shown as a warning)"""
    hit = set()
    for b in bookings:
        if b.is_upcoming and MaintenanceBlock.objects.filter(
            facility=b.facility, starts_at__lt=b.ends_at, ends_at__gt=b.starts_at
        ).exists():
            hit.add(b.pk)
    return hit
