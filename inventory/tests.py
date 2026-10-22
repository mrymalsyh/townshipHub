import tempfile
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Item, ItemLocker, ItemLoan, ItemMaintenance, ItemReturn, ItemWaitlist
from .services import (
    LoanError, borrow_item, join_waitlist, request_extension, submit_return, verify_return,
)


class InventoryReturnFlowTests(TestCase):
    def setUp(self):
        self.media_dir = tempfile.TemporaryDirectory()
        settings_override = override_settings(MEDIA_ROOT=self.media_dir.name)
        settings_override.enable()
        self.addCleanup(settings_override.disable)
        self.addCleanup(self.media_dir.cleanup)
        user_model = get_user_model()
        self.resident = user_model.objects.create_user(
            username="resident", password="password", points=4
        )
        self.next_resident = user_model.objects.create_user(
            username="next", password="password"
        )
        self.manager = user_model.objects.create_user(
            username="manager", password="password", role="admin"
        )
        self.item = Item.objects.create(name="Power drill", total_quantity=1)
        self.loan = ItemLoan.objects.create(
            item=self.item, user=self.resident, due_at=timezone.now() + timedelta(hours=1)
        )
        self.locker = ItemLocker.objects.create(
            name="Locker C", location_description="Clubhouse entrance"
        )

    @staticmethod
    def evidence():
        return SimpleUploadedFile("return.jpg", b"test-evidence", content_type="image/jpeg")

    def return_values(self, destination=ItemReturn.DESTINATION_OFFICE, locker=None, **overrides):
        values = {
            "destination": destination,
            "locker": locker,
            "cleaned": True,
            "accessories_included": True,
            "maintenance_requested": False,
            "evidence": self.evidence(),
        }
        values.update(overrides)
        return values

    def test_resident_return_waits_for_admin_and_awards_verified_points(self):
        client = Client()
        client.force_login(self.resident)
        page = client.get(reverse("my_loans"))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Submit return for inspection")
        self.assertContains(page, '<details class="inventory-collapse return-collapse">', html=False)
        self.assertContains(page, "Return this item")
        response = client.post(
            reverse("request_return", args=[self.loan.pk]),
            {
                "destination": ItemReturn.DESTINATION_OFFICE,
                "cleaned": "on",
                "accessories_included": "on",
                "evidence": self.evidence(),
            },
        )
        self.assertRedirects(response, reverse("my_loans"))
        ticket = ItemReturn.objects.get(loan=self.loan)
        self.loan.refresh_from_db()
        self.assertIsNone(self.loan.returned_at)
        self.assertEqual(ticket.status, ItemReturn.STATUS_PENDING)
        self.assertEqual(self.item.available, 0)

        client.force_login(self.manager)
        response = client.post(
            reverse("loan_return", args=[ticket.pk]),
            {"action": "approve", "condition": "good", "notes": "", "code": ""},
        )
        self.assertRedirects(response, reverse("manage_inventory"))
        self.loan.refresh_from_db()
        self.resident.refresh_from_db()
        self.assertIsNotNone(self.loan.returned_at)
        self.assertEqual(self.resident.points, 19)
        self.assertEqual(ItemReturn.objects.get(pk=ticket.pk).status, ItemReturn.STATUS_APPROVED)
        self.assertEqual(self.item.available, 1)

    def test_management_inventory_shows_return_review_and_locker_configuration(self):
        client = Client()
        client.force_login(self.manager)
        response = client.get(reverse("manage_inventory"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Returns pending inspection")
        self.assertContains(response, '<details class="inventory-collapse pending-returns-collapse">', html=False)
        self.assertContains(response, "Add locker")
        self.assertContains(response, "Lifecycle and stock")

    def test_locker_code_is_created_and_required_for_admin_verification(self):
        ticket = submit_return(
            self.loan,
            self.return_values(ItemReturn.DESTINATION_LOCKER, self.locker),
        )
        self.assertEqual(len(ticket.return_code), 6)
        with self.assertRaises(LoanError):
            verify_return(ticket, self.manager, "good", code="000000")
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, ItemReturn.STATUS_PENDING)

        verify_return(ticket, self.manager, "good", code=ticket.return_code)
        ticket.refresh_from_db()
        self.assertEqual(ticket.return_code, "")
        self.assertEqual(ticket.status, ItemReturn.STATUS_APPROVED)

    def test_transfer_notifies_next_resident_and_reservation_can_be_collected(self):
        waitlist_entry = join_waitlist(self.next_resident, self.item.pk)
        ticket = submit_return(
            self.loan,
            self.return_values(ItemReturn.DESTINATION_TRANSFER, self.locker),
        )
        verify_return(ticket, self.manager, "good", code=ticket.return_code)

        waitlist_entry.refresh_from_db()
        self.assertEqual(waitlist_entry.status, ItemWaitlist.STATUS_READY)
        self.assertEqual(waitlist_entry.locker, self.locker)
        self.assertEqual(len(waitlist_entry.pickup_code), 6)
        self.assertEqual(self.item.available, 0)
        next_loan = borrow_item(
            self.next_resident, self.item.pk, 1, timezone.now() + timedelta(days=1),
            reservation_id=waitlist_entry.pk,
        )
        self.assertEqual(next_loan.user, self.next_resident)
        waitlist_entry.refresh_from_db()
        self.assertEqual(waitlist_entry.status, ItemWaitlist.STATUS_FULFILLED)
        self.assertEqual(waitlist_entry.pickup_code, "")

    def test_maintenance_flag_removes_stock_without_deducting_points(self):
        ticket = submit_return(
            self.loan,
            self.return_values(maintenance_requested=True),
        )
        verify_return(ticket, self.manager, "good", "Blade needs service", flag=True)
        self.resident.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.resident.points, 4)
        self.assertEqual(self.item.out_of_service, 1)
        self.assertEqual(self.item.available, 0)
        self.loan.refresh_from_db()
        issue = ItemMaintenance.objects.get(loan=self.loan)
        self.assertEqual(issue.status, ItemMaintenance.STATUS_OPEN)
        self.assertEqual(self.loan.return_condition, "damaged")

    def test_extension_auto_approves_only_when_no_resident_is_waiting(self):
        old_due = self.loan.due_at
        client = Client()
        client.force_login(self.resident)
        response = client.post(reverse("loan_extension", args=[self.loan.pk]))
        self.assertRedirects(response, reverse("my_loans"))
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.extension_count, 1)
        self.assertGreater(self.loan.due_at, old_due)

        other_loan = ItemLoan.objects.create(
            item=self.item, user=self.next_resident, due_at=timezone.now() + timedelta(hours=1)
        )
        ItemWaitlist.objects.create(item=self.item, user=self.manager)
        with self.assertRaises(LoanError):
            request_extension(other_loan)
