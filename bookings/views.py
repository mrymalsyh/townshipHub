from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import manager_required

from .forms import BookingForm, MaintenanceForm
from .models import Booking, Facility, MaintenanceBlock
from .services import (
    BookingError, announce_block, bookings_hit_by_blocks, cancel_booking, create_booking,
)


@login_required
def facility_list(request):
    facilities = list(Facility.objects.filter(is_active=True))
    now = timezone.now()
    for f in facilities:
        f.closed_now = f.current_block()
        f.in_use_now = f.bookings.filter(
            status="confirmed", starts_at__lte=now, ends_at__gt=now
        ).exists()
        f.next_block = f.upcoming_blocks().first() if not f.closed_now else None
    return render(request, "bookings/facilities.html", {"facilities": facilities})


@login_required
def facility_detail(request, pk):
    facility = get_object_or_404(Facility, pk=pk)
    now = timezone.now()
    week = now + timedelta(days=7)
    taken = facility.bookings.filter(
        status="confirmed", ends_at__gt=now, starts_at__lt=week
    ).select_related("user")
    blocks = facility.blocks.filter(ends_at__gt=now, starts_at__lt=week)

    form = BookingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            create_booking(
                request.user, facility,
                form.cleaned_data["starts_at"], form.cleaned_data["ends_at"],
                form.cleaned_data["purpose"],
            )
        except BookingError as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, "Booked! See you there.")
            return redirect("my_bookings")
    return render(
        request, "bookings/facility_detail.html",
        {"facility": facility, "taken": taken, "blocks": blocks, "form": form},
    )


@login_required
def my_bookings(request):
    bookings = list(Booking.objects.filter(user=request.user).select_related("facility"))
    bookings.sort(key=lambda b: (not b.is_upcoming, b.starts_at))
    return render(
        request, "bookings/mine.html",
        {"bookings": bookings, "hit": bookings_hit_by_blocks(bookings)},
    )


@login_required
@require_POST
def booking_cancel(request, pk):
    booking = get_object_or_404(Booking, pk=pk, user=request.user)
    cancel_booking(booking)
    messages.success(request, "Booking cancelled.")
    return redirect("my_bookings")


@manager_required
def manage_bookings(request):
    form = MaintenanceForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        block = form.save()
        announce_block(block)
        messages.success(request, "Closure saved. Residents with clashing bookings were notified.")
        return redirect("manage_bookings")
    now = timezone.now()
    return render(
        request, "bookings/manage.html",
        {
            "form": form,
            "blocks": MaintenanceBlock.objects.filter(ends_at__gt=now).select_related("facility"),
            "upcoming": Booking.objects.filter(status="confirmed", ends_at__gt=now)
            .select_related("facility", "user"),
        },
    )


@manager_required
@require_POST
def block_delete(request, pk):
    get_object_or_404(MaintenanceBlock, pk=pk).delete()
    messages.success(request, "Closure removed.")
    return redirect("manage_bookings")
