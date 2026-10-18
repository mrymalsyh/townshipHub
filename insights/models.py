from django.db import models


class Insight(models.Model):
    """The saved write-up for one hotspot, so we do not call the AI on every page load."""

    location = models.ForeignKey("core.Location", on_delete=models.CASCADE, related_name="insights")
    category = models.CharField(max_length=20)
    window_days = models.PositiveIntegerField(default=60)
    report_count = models.PositiveIntegerField(default=0)
    summary = models.TextField()
    suggested_action = models.TextField()
    source = models.CharField(max_length=10, default="rules")  # "ai" or "rules"
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["location", "category"], name="one_insight_per_hotspot")
        ]
        ordering = ["-generated_at"]

    def __str__(self):
        return f"{self.location} / {self.category}"
