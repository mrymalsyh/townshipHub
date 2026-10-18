from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import manager_required

from .forms import BorrowForm, ReturnForm
from .models import Item, ItemLoan
from .services import LoanError, borrow_item, mark_repaired, record_return


@login_required
def item_list(request):
    return render(request, "inventory/items.html", {"items": Item.objects.all()})


@login_required
def item_detail(request, pk):
    item = get_object_or_404(Item, pk=pk)
    form = BorrowForm(request.POST or None, initial={"due_at": (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")})
    if request.method == "POST" and form.is_valid():
        try:
            borrow_item(
                request.user, item.pk, form.cleaned_data["quantity"],
                form.cleaned_data["due_at"], form.cleaned_data["purpose"],
            )
        except LoanError as e:
            form.add_error(None, str(e))
        else:
            messages.success(request, "Item reserved. Please collect it from the management office.")
            return redirect("my_loans")
    return render(request, "inventory/item_detail.html", {"item": item, "form": form})


@login_required
def my_loans(request):
    loans = ItemLoan.objects.filter(user=request.user).select_related("item")
    return render(request, "inventory/mine.html", {"loans": loans})


@manager_required
def manage_inventory(request):
    outstanding = ItemLoan.objects.filter(returned_at__isnull=True).select_related("item", "user")
    recent = ItemLoan.objects.filter(returned_at__isnull=False).select_related("item", "user")[:15]
    return render(
        request, "inventory/manage.html",
        {
            "outstanding": outstanding,
            "recent": recent,
            "items": Item.objects.all(),
            "return_form": ReturnForm(),
        },
    )


@manager_required
@require_POST
def loan_return(request, pk):
    loan = get_object_or_404(ItemLoan, pk=pk, returned_at__isnull=True)
    form = ReturnForm(request.POST, request.FILES)
    if form.is_valid():
        record_return(
            loan, form.cleaned_data["condition"], form.cleaned_data["notes"],
            form.cleaned_data.get("photo"),
        )
        messages.success(request, "Return recorded.")
    else:
        messages.error(request, "Could not record the return. Please check the form.")
    return redirect("manage_inventory")


@manager_required
@require_POST
def item_repaired(request, pk):
    item = get_object_or_404(Item, pk=pk)
    mark_repaired(item)
    messages.success(request, f"One {item.name} is back in service.")
    return redirect("manage_inventory")
