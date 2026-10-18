from django.db import models


class Location(models.Model):
    """A named place in the township. Reports and hotspots are grouped by this."""

    KIND_CHOICES = [
        ("building", "Building / block"),
        ("pathway", "Pathway / road"),
        ("park", "Park / playground"),
        ("facility", "Facility"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default="other")
    latitude = models.FloatField(help_text="Used to place the pin on the map")
    longitude = models.FloatField()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
