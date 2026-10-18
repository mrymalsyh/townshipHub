from django import forms

from .models import Report, ReportTip


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = [
            "scope", "location", "spot_detail", "category",
            "urgency", "title", "description", "photo",
        ]
        widgets = {
            "scope": forms.RadioSelect,
            "description": forms.Textarea(attrs={"rows": 4}),
        }


class StatusUpdateForm(forms.Form):
    status = forms.ChoiceField(choices=Report.STATUS_CHOICES)
    note = forms.CharField(
        max_length=300, required=False, label="Note for the resident",
        widget=forms.TextInput(attrs={"placeholder": "e.g. Plumber visiting tomorrow 10am"}),
    )
    alternative_route = forms.CharField(
        required=False, label="Official alternative route / advice (outdoor reports)",
        widget=forms.Textarea(attrs={"rows": 2, "placeholder": "e.g. Please use the back path behind Block B"}),
    )


class TipForm(forms.ModelForm):
    class Meta:
        model = ReportTip
        fields = ["text"]
        labels = {"text": "Suggest a way around (or any helpful tip)"}
        widgets = {"text": forms.TextInput(attrs={"placeholder": "e.g. Use the side gate near the playground"})}
