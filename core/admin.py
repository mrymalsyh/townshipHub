from django.contrib import admin

from .models import Location


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "latitude", "longitude")
    list_filter = ("kind",)
    search_fields = ("name",)
