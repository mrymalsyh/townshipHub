from django.contrib import admin

from .models import Report, ReportConfirmation, ReportTip, ReportUpdate


class UpdateInline(admin.TabularInline):
    model = ReportUpdate
    extra = 0


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "scope", "category", "location", "urgency", "status", "created_at")
    list_filter = ("scope", "category", "status", "urgency", "location")
    search_fields = ("title", "description")
    inlines = [UpdateInline]


admin.site.register(ReportConfirmation)
admin.site.register(ReportTip)
