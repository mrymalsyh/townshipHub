from django.contrib import admin

from .models import Booking, Facility, MaintenanceBlock


@admin.register(Facility)
class FacilityAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity", "is_active")


@admin.register(MaintenanceBlock)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("facility", "reason", "starts_at", "ends_at")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("facility", "user", "starts_at", "ends_at", "status")
    list_filter = ("facility", "status")
