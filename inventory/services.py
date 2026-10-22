import secrets
from datetime import timedelta

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from notifications.services import managers, notify

from .models import Item, ItemLocker, ItemLoan, ItemMaintenance, ItemReturn, ItemWaitlist


class LoanError(Exception):
    """A friendly message that can be shown straight to the resident."""


POINTS_FOR = {"good": 3, "needs_cleaning": 0, "unused": 1, "damaged": -3, "missing": -8}


def _new_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def borrow_item(user, item_id, quantity, due_at, purpose="", reservation_id=None):
    if quantity < 1:
        raise LoanError("Please ask for at least 1.")
    if due_at <= timezone.now():
        raise LoanError("The return date must be in the future.")
    with transaction.atomic():
        item = Item.objects.select_for_update().get(pk=item_id)
        reservation = None
        if reservation_id:
            reservation = ItemWaitlist.objects.select_for_update().filter(
                pk=reservation_id, item=item, user=user, status=ItemWaitlist.STATUS_READY
            ).first()
            if reservation is None:
                raise LoanError("That item is no longer reserved for you.")
            if quantity != 1:
                raise LoanError("A next-in-line reservation is for one unit.")
        if reservation:
            physically_available = item.total_quantity - item.out_of_service - item.on_loan
            if physically_available < 1:
                raise LoanError("The reserved item is still being checked in.")
        elif quantity > item.available:
            raise LoanError(f"Only {item.available} x {item.name} available right now.")
        loan = ItemLoan.objects.create(
            item=item, user=user, quantity=quantity, due_at=due_at, purpose=purpose
        )
        if reservation:
            reservation.status = ItemWaitlist.STATUS_FULFILLED
            reservation.pickup_code = ""
            reservation.save(update_fields=["status", "pickup_code"])
        return loan


def join_waitlist(user, item_id):
    with transaction.atomic():
        item = Item.objects.select_for_update().get(pk=item_id)
        if item.available:
            raise LoanError(f"{item.name} is available now; borrow it directly.")
        if ItemWaitlist.objects.filter(
            item=item, user=user,
            status__in=[ItemWaitlist.STATUS_WAITING, ItemWaitlist.STATUS_READY],
        ).exists():
            raise LoanError("You are already in line for this item.")
        return ItemWaitlist.objects.create(item=item, user=user)


def submit_return(loan, values):
    with transaction.atomic():
        locked_loan = ItemLoan.objects.select_for_update().get(pk=loan.pk)
        if locked_loan.returned_at:
            raise LoanError("This loan has already been returned.")
        if ItemReturn.objects.filter(loan=locked_loan).exists():
            raise LoanError("A return request is already awaiting management inspection.")
        destination = values["destination"]
        locker = values.get("locker")
        if destination in (ItemReturn.DESTINATION_LOCKER, ItemReturn.DESTINATION_TRANSFER):
            if locker is None or not locker.is_active:
                raise LoanError("Choose an active return locker.")
        else:
            locker = None
        waiting = ItemWaitlist.objects.filter(
            item=locked_loan.item, status=ItemWaitlist.STATUS_WAITING
        ).exists()
        if destination == ItemReturn.DESTINATION_TRANSFER and not waiting:
            raise LoanError("There is no resident waiting for this item to transfer to.")
        code = _new_code() if destination in (
            ItemReturn.DESTINATION_LOCKER, ItemReturn.DESTINATION_TRANSFER
        ) else ""
        ticket = ItemReturn.objects.create(
            loan=locked_loan,
            destination=destination,
            locker=locker,
            return_code=code,
            cleaned=values["cleaned"],
            accessories_included=values["accessories_included"],
            maintenance_requested=values["maintenance_requested"],
            evidence=values["evidence"],
        )
        notify(
            managers(),
            f"Return pending inspection: {locked_loan.quantity} x {locked_loan.item.name}.",
            reverse("manage_inventory"),
        )
        return ticket


def request_extension(loan):
    with transaction.atomic():
        locked_loan = ItemLoan.objects.select_for_update().get(pk=loan.pk)
        if locked_loan.returned_at:
            raise LoanError("This item has already been returned.")
        if locked_loan.extension_count:
            raise LoanError("The one-hour grace extension has already been used.")
        queue_exists = ItemWaitlist.objects.filter(
            item=locked_loan.item,
            status__in=[ItemWaitlist.STATUS_WAITING, ItemWaitlist.STATUS_READY],
        ).exists()
        if queue_exists:
            locker_names = ", ".join(
                ItemLocker.objects.filter(is_active=True).values_list("name", flat=True)[:3]
            )
            where = f" Use a configured drop-off locker ({locker_names}) or the management desk." if locker_names else " Return it to the management desk."
            raise LoanError(
                "A neighbour is waiting, so the extension was not approved." + where
            )
        locked_loan.due_at = max(locked_loan.due_at, timezone.now()) + timedelta(hours=1)
        locked_loan.extension_count += 1
        locked_loan.save(update_fields=["due_at", "extension_count"])
        notify(
            [locked_loan.user],
            f"Your one-hour extension for {locked_loan.item.name} was approved automatically.",
            reverse("my_loans"),
        )
        return locked_loan


def _dispatch_next_waiter(item, locker=None):
    next_entry = ItemWaitlist.objects.select_for_update().filter(
        item=item, status=ItemWaitlist.STATUS_WAITING
    ).select_related("user").order_by("created_at", "pk").first()
    if not next_entry or item.available < 1:
        return None
    next_entry.status = ItemWaitlist.STATUS_READY
    next_entry.locker = locker
    next_entry.pickup_code = _new_code() if locker else ""
    next_entry.ready_at = timezone.now()
    next_entry.save(update_fields=["status", "locker", "pickup_code", "ready_at"])
    details = f" in {locker.name}" if locker else " at the management desk"
    code_text = f" Your one-time collection code is {next_entry.pickup_code}." if locker else ""
    notify(
        [next_entry.user],
        f"Your reserved {item.name} is ready{details}.{code_text}",
        reverse("item_detail", args=[item.pk]),
    )
    return next_entry


def _dispatch_waiters(item, transfer_locker=None):
    dispatched = _dispatch_next_waiter(item, transfer_locker)
    while item.available > 0:
        next_entry = _dispatch_next_waiter(item)
        if next_entry is None:
            break
        if dispatched is None:
            dispatched = next_entry
    return dispatched


def verify_return(ticket, manager, condition, notes="", code="", flag=False):
    """Close a resident return after inspection and update stock/maintenance."""
    with transaction.atomic():
        locked_ticket = ItemReturn.objects.select_for_update().select_related(
            "loan", "loan__item", "loan__user"
        ).get(pk=ticket.pk)
        if locked_ticket.status != ItemReturn.STATUS_PENDING:
            raise LoanError("This return has already been reviewed.")
        if locked_ticket.return_code and not secrets.compare_digest(
            locked_ticket.return_code, code.strip()
        ):
            raise LoanError("The one-time locker code does not match.")
        loan = ItemLoan.objects.select_for_update().get(pk=locked_ticket.loan_id)
        item = Item.objects.select_for_update().get(pk=loan.item_id)
        issue_reported = locked_ticket.maintenance_requested or flag
        condition = "damaged" if issue_reported else condition
        now = timezone.now()
        loan.returned_at = now
        loan.return_condition = condition
        loan.admin_notes = notes[:300]
        loan.save(update_fields=["returned_at", "return_condition", "admin_notes"])

        if condition == "damaged" or issue_reported:
            item.out_of_service = min(item.total_quantity, item.out_of_service + loan.quantity)
            item.save(update_fields=["out_of_service"])
            ItemMaintenance.objects.create(
                item=item,
                loan=loan,
                reported_by=loan.user,
                description=notes or "Resident reported that the item needs maintenance.",
            )
        elif condition == "missing":
            item.total_quantity = max(0, item.total_quantity - loan.quantity)
            item.out_of_service = min(item.out_of_service, item.total_quantity)
            item.save(update_fields=["total_quantity", "out_of_service"])

        locked_ticket.condition = condition
        locked_ticket.notes = notes[:300]
        locked_ticket.status = ItemReturn.STATUS_FLAGGED if flag else ItemReturn.STATUS_APPROVED
        locked_ticket.verified_at = now
        locked_ticket.verified_by = manager
        locked_ticket.return_code = ""
        locked_ticket.save(
            update_fields=[
                "condition", "notes", "status", "verified_at", "verified_by", "return_code"
            ]
        )

        earned = (
            not flag
            and not issue_reported
            and condition in ("good", "unused")
            and locked_ticket.cleaned
            and locked_ticket.accessories_included
            and now <= loan.due_at
        )
        if earned:
            loan.user.add_points(15)

        transfer_locker = (
            locked_ticket.locker
            if locked_ticket.destination == ItemReturn.DESTINATION_TRANSFER
            and not issue_reported and condition in ("good", "unused")
            else None
        )
        next_entry = _dispatch_waiters(item, transfer_locker)
        feedback = " Your +15 care points have been added." if earned else ""
        condition_label = dict(ItemLoan.CONDITION_CHOICES).get(condition, condition)
        notify(
            [loan.user],
            f"Your return of {loan.quantity} x {item.name} was "
            f"{'flagged for follow-up' if flag else 'verified'} ({condition_label})."
            + feedback,
            reverse("my_loans"),
        )
        return next_entry


def record_return(loan, condition, notes="", photo=None):
    """Legacy management check-in helper; resident returns use the inspection workflow."""
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
    with transaction.atomic():
        item = Item.objects.select_for_update().get(pk=item.pk)
        item.out_of_service = max(0, item.out_of_service - quantity)
        item.save(update_fields=["out_of_service"])
        issue = item.maintenance_issues.filter(status=ItemMaintenance.STATUS_OPEN).first()
        if issue:
            issue.status = ItemMaintenance.STATUS_RESOLVED
            issue.resolved_at = timezone.now()
            issue.save(update_fields=["status", "resolved_at"])
        _dispatch_waiters(item)
