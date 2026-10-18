from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class TownshipUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Township", {"fields": ("role", "unit", "phone", "is_vulnerable", "points")}),
    )
    list_display = ("username", "first_name", "last_name", "role", "unit", "is_vulnerable")
    list_filter = UserAdmin.list_filter + ("role", "is_vulnerable")
