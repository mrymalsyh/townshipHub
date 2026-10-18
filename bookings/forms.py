from django import forms

from .models import MaintenanceBlock

DT = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


class BookingForm(forms.Form):
    starts_at = forms.DateTimeField(
        label="From", widget=DT, input_formats=["%Y-%m-%dT%H:%M"]
    )
    ends_at = forms.DateTimeField(
        label="Until", widget=DT, input_formats=["%Y-%m-%dT%H:%M"]
    )
    purpose = forms.CharField(
        label="What is it for?", max_length=200, required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Birthday party"}),
    )


class MaintenanceForm(forms.ModelForm):
    class Meta:
        model = MaintenanceBlock
        fields = ["facility", "starts_at", "ends_at", "reason"]
        widgets = {"starts_at": DT, "ends_at": DT}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ("starts_at", "ends_at"):
            self.fields[f].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean(self):
        data = super().clean()
        if data.get("starts_at") and data.get("ends_at") and data["ends_at"] <= data["starts_at"]:
            raise forms.ValidationError("The end time must be after the start time.")
        return data
