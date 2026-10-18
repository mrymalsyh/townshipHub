from django.contrib import admin

from .models import Item, ItemLoan


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "total_quantity", "out_of_service")


@admin.register(ItemLoan)
class ItemLoanAdmin(admin.ModelAdmin):
    list_display = ("item", "user", "quantity", "due_at", "returned_at", "return_condition")
    list_filter = ("return_condition",)
