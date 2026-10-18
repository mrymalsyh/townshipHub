from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from notifications.services import notify

from .models import Item, ItemLoan


class LoanError(Exception):
    """A friendly message that can be shown straight to the resident."""


def borrow_item(user, item_id, quantity, due_at, purpose=""):
    if quantity < 1:
        raise LoanError("Please ask for at least 1.")
    if due_at <= timezone.now():
        raise LoanError("The return date must be in the future.")
    with transaction.atomic():
        # Lock this item's row so two people cannot take the last unit together.
        item = Item.objects.select_for_update().get(pk=item_id)
        if quantity > item.available:
            raise LoanError(f"Only {item.available} x {item.name} available right now.")
        return ItemLoan.objects.create(
            item=item, user=user, quantity=quantity, due_at=due_at, purpose=purpose
        )


# Care points: reward careful returns, gently discourage careless ones.
POINTS_FOR = {"good": 3, "needs_cleaning": 0, "unused": 1, "damaged": -3, "missing": -8}


def record_return(loan, condition, notes="", photo=None):
    """Management checks the item back in and grades it."""
    with transaction.atomic():
        item = Item.objects.select_for_update().get(pk=loan.item_id)
        loan.returned_at = timezone.now()
        loan.return_condition = condition
        loan.admin_notes = notes
        if photo:
            loan.return_photo = photo
        loan.save()

        if condition == "damaged":
            item.out_of_service = min(item.total_quantity, item.out_of_service + loan.quantity)
            item.save(update_fields=["out_of_service"])
        elif condition == "missing":
            item.total_quantity = max(0, item.total_quantity - loan.quantity)
            item.out_of_service = min(item.out_of_service, item.total_quantity)
            item.save(update_fields=["total_quantity", "out_of_service"])

    loan.user.add_points(POINTS_FOR.get(condition, 0))
    notify(
        [loan.user],
        f"Your return of {loan.quantity} x {loan.item.name} was checked in: "
        f"{loan.get_return_condition_display()}.",
        reverse("my_loans"),
    )


def mark_repaired(item, quantity=1):
    item.out_of_service = max(0, item.out_of_service - quantity)
    item.save(update_fields=["out_of_service"])
