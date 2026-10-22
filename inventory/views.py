from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.decorators import manager_required

from .forms import BorrowForm, ItemLockerForm, ReturnRequestForm, ReturnReviewForm
from .models import Item, ItemLocker, ItemLoan, ItemMaintenance, ItemReturn, ItemWaitlist
from .services import (
    LoanError, borrow_item, join_waitlist, mark_repaired, request_extension, submit_return,
    verify_return,
)


@login_required
def item_list(request):
    return render(request, "inventory/items.html", {"items": Item.objects.all()})


@login_required
def item_detail(request, pk):
    item = get_object_or_404(Item, pk=pk)
    reservation = ItemWaitlist.objects.filter(
        item=item, user=request.user, status=ItemWaitlist.STATUS_READY
    ).first()
    form = BorrowForm(
        request.POST or None,
        initial={"due_at": (timezone.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")},
    )
    if request.method == "POST" and form.is_valid():
        reservation_id = request.POST.get("reservation_id") or None
        try:
            borrow_item(
                request.user, item.pk, form.cleaned_data["quantity"],
                form.cleaned_data["due_at"], form.cleaned_data["purpose"], reservation_id,
            )
        except LoanError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "Item checked out. Please collect it from the location shown.")
            return redirect("my_loans")
    return render(
        request, "inventory/item_detail.html",
        {"item": item, "form": form, "reservation": reservation},
    )


@login_required
@require_POST
def item_waitlist(request, pk):
    item = get_object_or_404(Item, pk=pk)
    try:
        entry = join_waitlist(request.user, item.pk)
    except LoanError as error:
        messages.info(request, str(error))
    else:
        messages.success(request, f"You are in line for {item.name}. We will notify you when it is ready.")
    return redirect("item_detail", pk=item.pk)


@login_required
def my_loans(request):
    loans = list(ItemLoan.objects.filter(user=request.user).select_related("item"))
    waitlist = ItemWaitlist.objects.filter(user=request.user).select_related(
        "item", "locker"
    ).exclude(status__in=[ItemWaitlist.STATUS_FULFILLED, ItemWaitlist.STATUS_CANCELLED])
    lockers = ItemLocker.objects.filter(is_active=True)
    loan_entries = []
    for loan in loans:
        has_waitlist = ItemWaitlist.objects.filter(
            item=loan.item, status=ItemWaitlist.STATUS_WAITING
        ).exists()
        loan_entries.append(
            {
                "loan": loan,
                "has_waitlist": has_waitlist,
                "return_form": ReturnRequestForm(
                    lockers=lockers, has_waitlist=has_waitlist
                ),
            }
        )
    return render(
        request, "inventory/mine.html",
        {
            "loan_entries": loan_entries,
            "waitlist": waitlist,
            "care_points": request.user.points,
        },
    )


@login_required
@require_POST
def request_return(request, pk):
    loan = get_object_or_404(
        ItemLoan.objects.select_related("item"), pk=pk, user=request.user, returned_at__isnull=True
    )
    lockers = ItemLocker.objects.filter(is_active=True)
    has_waitlist = ItemWaitlist.objects.filter(
        item=loan.item, status=ItemWaitlist.STATUS_WAITING
    ).exists()
    form = ReturnRequestForm(
        request.POST, request.FILES, lockers=lockers, has_waitlist=has_waitlist
    )
    if not form.is_valid():
        for error in form.non_field_errors():
            messages.error(request, error)
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
        return redirect("my_loans")
    try:
        ticket = submit_return(loan, form.cleaned_data)
    except LoanError as error:
        messages.error(request, str(error))
    else:
        if ticket.return_code:
            messages.success(
                request,
                f"Return request submitted for admin inspection. Your one-time locker code is "
                f"{ticket.return_code}. This app does not unlock physical lockers.",
            )
        else:
            messages.success(request, "Return request submitted for admin inspection.")
    return redirect("my_loans")


@login_required
@require_POST
def loan_extension(request, pk):
    loan = get_object_or_404(ItemLoan, pk=pk, user=request.user)
    try:
        updated = request_extension(loan)
    except LoanError as error:
        messages.warning(request, str(error))
    else:
        messages.success(request, f"One-hour extension approved. New due time: {updated.due_at:%d %b %H:%M}.")
    return redirect("my_loans")


@manager_required
def manage_inventory(request):
    outstanding = ItemLoan.objects.filter(returned_at__isnull=True).select_related(
        "item", "user"
    ).prefetch_related("return_ticket")
    pending_returns = ItemReturn.objects.filter(status=ItemReturn.STATUS_PENDING).select_related(
        "loan__item", "loan__user", "locker"
    )
    recent = ItemReturn.objects.exclude(status=ItemReturn.STATUS_PENDING).select_related(
        "loan__item", "loan__user", "verified_by"
    )[:15]
    issues = ItemMaintenance.objects.filter(status=ItemMaintenance.STATUS_OPEN).select_related(
        "item", "reported_by", "loan"
    )
    return render(
        request, "inventory/manage.html",
        {
            "outstanding": outstanding,
            "pending_returns": pending_returns,
            "recent": recent,
            "issues": issues,
            "items": Item.objects.all(),
            "lockers": ItemLocker.objects.all(),
            "locker_form": ItemLockerForm(),
            "review_form": ReturnReviewForm(),
        },
    )


@manager_required
@require_POST
def add_locker(request):
    form = ItemLockerForm(request.POST)
    if form.is_valid():
        locker = form.save()
        messages.success(request, f"{locker.name} added to return locations.")
    else:
        messages.error(request, "Could not save the locker. Check that its name is unique.")
    return redirect("manage_inventory")


@manager_required
@require_POST
def toggle_locker(request, pk):
    locker = get_object_or_404(ItemLocker, pk=pk)
    locker.is_active = not locker.is_active
    locker.save(update_fields=["is_active"])
    state = "available" if locker.is_active else "inactive"
    messages.success(request, f"{locker.name} is now {state} for new returns.")
    return redirect("manage_inventory")


@manager_required
@require_POST
def loan_return(request, pk):
    ticket = get_object_or_404(
        ItemReturn.objects.select_related("loan__item", "loan__user"),
        pk=pk, status=ItemReturn.STATUS_PENDING,
    )
    form = ReturnReviewForm(request.POST)
    action = request.POST.get("action")
    if not form.is_valid() or action not in ("approve", "flag"):
        messages.error(request, "Could not review the return. Please check the form.")
        return redirect("manage_inventory")
    try:
        verify_return(
            ticket, request.user, form.cleaned_data["condition"], form.cleaned_data["notes"],
            code=form.cleaned_data["code"],
            flag=(action == "flag"),
        )
    except LoanError as error:
        messages.error(request, str(error))
    else:
        if action == "flag":
            messages.warning(request, "Return flagged for follow-up and the item was moved to maintenance.")
        else:
            messages.success(request, "Return approved.")
    return redirect("manage_inventory")


@manager_required
@require_POST
def item_repaired(request, pk):
    item = get_object_or_404(Item, pk=pk)
    mark_repaired(item)
    messages.success(request, f"One {item.name} is back in service.")
    return redirect("manage_inventory")
