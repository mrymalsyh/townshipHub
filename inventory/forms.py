from django import forms

from .models import ItemLoan


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


class ReturnForm(forms.Form):
    condition = forms.ChoiceField(choices=ItemLoan.CONDITION_CHOICES, initial="good")
    notes = forms.CharField(
        max_length=300, required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. Leg is bent, needs repair"}),
    )
    photo = forms.ImageField(required=False, label="Photo of the item (optional)")
