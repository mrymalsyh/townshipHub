from django.contrib import admin

from .models import Item, ItemLocker, ItemLoan, ItemMaintenance, ItemReturn, ItemWaitlist


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "total_quantity", "out_of_service")


@admin.register(ItemLoan)
class ItemLoanAdmin(admin.ModelAdmin):
    list_display = (
        "item", "user", "quantity", "due_at", "returned_at", "return_condition",
        "extension_count",
    )
    list_filter = ("return_condition",)


@admin.register(ItemLocker)
class ItemLockerAdmin(admin.ModelAdmin):
    list_display = ("name", "location_description", "is_active")
    list_filter = ("is_active",)


@admin.register(ItemReturn)
class ItemReturnAdmin(admin.ModelAdmin):
    list_display = ("loan", "destination", "status", "submitted_at", "verified_by")
    list_filter = ("status", "destination", "maintenance_requested")
    readonly_fields = ("return_code", "submitted_at", "verified_at")


@admin.register(ItemWaitlist)
class ItemWaitlistAdmin(admin.ModelAdmin):
    list_display = ("item", "user", "status", "created_at", "ready_at", "locker")
    list_filter = ("status",)
    readonly_fields = ("pickup_code",)


@admin.register(ItemMaintenance)
class ItemMaintenanceAdmin(admin.ModelAdmin):
    list_display = ("item", "reported_by", "status", "created_at", "resolved_at")
    list_filter = ("status",)
