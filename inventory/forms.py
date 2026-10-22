from pathlib import Path

from django import forms

from .models import ItemLocker, ItemLoan, ItemReturn


class BorrowForm(forms.Form):
    quantity = forms.IntegerField(min_value=1, initial=1)
    due_at = forms.DateTimeField(
        label="I will return it by",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        input_formats=["%Y-%m-%dT%H:%M"],
    )
    purpose = forms.CharField(
        max_length=200, required=False, label="What is it for?",
        widget=forms.TextInput(attrs={"placeholder": "e.g. Neighbourhood gathering"}),
    )


class ReturnRequestForm(forms.Form):
    destination = forms.ChoiceField(choices=ItemReturn.DESTINATION_CHOICES)
    locker = forms.ModelChoiceField(
        queryset=ItemLocker.objects.none(), required=False, empty_label="Choose a locker"
    )
    cleaned = forms.BooleanField(required=False, label="I cleaned the item")
    accessories_included = forms.BooleanField(required=False, label="All accessories are included")
    maintenance_requested = forms.BooleanField(
        required=False, label="This item needs maintenance"
    )
    evidence = forms.FileField(
        label="Photo or video of the returned item",
        help_text="Required for return verification. Maximum file size: 20 MB.",
        widget=forms.ClearableFileInput(attrs={"accept": "image/*,video/mp4,video/quicktime,video/webm"}),
    )

    def __init__(self, *args, lockers=None, has_waitlist=False, **kwargs):
        super().__init__(*args, **kwargs)
        lockers = lockers if lockers is not None else ItemLocker.objects.none()
        self.fields["locker"].queryset = lockers
        if not lockers.exists():
            self.fields["destination"].choices = [
                choice for choice in ItemReturn.DESTINATION_CHOICES
                if choice[0] == ItemReturn.DESTINATION_OFFICE
            ]
        if not has_waitlist:
            self.fields["destination"].choices = [
                choice for choice in self.fields["destination"].choices
                if choice[0] != ItemReturn.DESTINATION_TRANSFER
            ]

    def clean(self):
        cleaned = super().clean()
        destination = cleaned.get("destination")
        locker = cleaned.get("locker")
        if destination in (ItemReturn.DESTINATION_LOCKER, ItemReturn.DESTINATION_TRANSFER) and not locker:
            self.add_error("locker", "Choose a configured locker for this drop-off.")
        if destination == ItemReturn.DESTINATION_OFFICE:
            cleaned["locker"] = None
        evidence = cleaned.get("evidence")
        if evidence:
            allowed = {".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov", ".webm"}
            if Path(evidence.name).suffix.lower() not in allowed:
                self.add_error("evidence", "Upload a photo or supported video file.")
            if evidence.size > 20 * 1024 * 1024:
                self.add_error("evidence", "The file must be no larger than 20 MB.")
        return cleaned


class ReturnReviewForm(forms.Form):
    code = forms.CharField(
        max_length=6, required=False, label="One-time locker code",
        widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "one-time-code"}),
    )
    condition = forms.ChoiceField(choices=ItemLoan.CONDITION_CHOICES, initial="good")
    notes = forms.CharField(
        max_length=300, required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Missing one bit set"}),
    )


class ItemLockerForm(forms.ModelForm):
    class Meta:
        model = ItemLocker
        fields = ["name", "location_description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Clubhouse locker 3"}),
            "location_description": forms.TextInput(
                attrs={"placeholder": "e.g. Ground-floor clubhouse entrance"}
            ),
        }
