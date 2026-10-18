from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render

from accounts.decorators import manager_required

from .forms import AdminProfileForm, RegisterForm


def register(request):
    if request.user.is_authenticated:
        return redirect("home")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f"Welcome, {user.first_name or user.username}!")
        return redirect("home")
    return render(request, "accounts/register.html", {"form": form})


@manager_required
def manage_profile(request):
    form = AdminProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile settings saved.")
        return redirect("manage_profile")
    return render(request, "accounts/profile.html", {"form": form})
