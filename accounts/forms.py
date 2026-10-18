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
