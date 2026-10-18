from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "unit", "phone", "is_vulnerable")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.ROLE_RESIDENT  # nobody can make themselves an admin here
        if commit:
            user.save()
        return user


class AdminProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email")
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }
