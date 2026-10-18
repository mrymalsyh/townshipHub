"""Automated checks for the rules that matter most. Run with:  python manage.py test"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking, Facility, MaintenanceBlock
from bookings.services import BookingError, announce_block, create_booking
from core.models import Location
from insights.services import find_hotspots, refresh_insight
from inventory.models import Item, ItemLoan
from inventory.services import LoanError, borrow_item, record_return
from notifications.models import Notification
from reports.models import Report
from reports.services import after_report_created, apply_status_update

User = get_user_model()


class Base(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("boss", password="x", role="admin")
        self.ann = User.objects.create_user("ann", password="x", is_vulnerable=True)
        self.bob = User.objects.create_user("bob", password="x")
        self.cat = User.objects.create_user("cat", password="x")
        self.block = Location.objects.create(name="Block C", kind="building", latitude=3.2, longitude=101.5)
        self.path = Location.objects.create(name="Walkway", kind="pathway", latitude=3.21, longitude=101.51)

    def report(self, who, scope="outdoor", loc=None, category="pathway", title="Broken", **kw):
        return Report.objects.create(
            reporter=who, location=loc or self.path, scope=scope, category=category, title=title, **kw)


class ReportRulesTests(Base):
    def test_indoor_reports_are_private_outdoor_are_public(self):
        indoor = self.report(self.ann, "indoor", self.block, "plumbing", "Leak")
        outdoor = self.report(self.ann, "outdoor", title="Hole")
        visible_to_bob = set(Report.objects.visible_to(self.bob))
        self.assertNotIn(indoor, visible_to_bob)
        self.assertIn(outdoor, visible_to_bob)
        self.assertIn(indoor, set(Report.objects.visible_to(self.ann)))
        self.assertIn(indoor, set(Report.objects.visible_to(self.admin)))

        self.client.login(username="bob", password="x")
        self.assertEqual(self.client.get(reverse("report_detail", args=[indoor.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("report_detail", args=[outdoor.pk])).status_code, 200)

    def test_outdoor_report_alerts_neighbours_indoor_does_not(self):
        out = self.report(self.ann, "outdoor")
        after_report_created(out)
        self.assertTrue(Notification.objects.filter(user=self.bob, message__contains="Heads-up").exists())
        self.assertTrue(Notification.objects.filter(user=self.admin, message__contains="New").exists())

        Notification.objects.all().delete()
        inn = self.report(self.ann, "indoor", self.block, "plumbing", "Leak")
        after_report_created(inn)
        self.assertFalse(Notification.objects.filter(user=self.bob).exists())
        self.assertTrue(Notification.objects.filter(user=self.admin).exists())

    def test_status_update_notifies_reporter_and_route_advice_goes_to_all(self):
        r = self.report(self.ann, "outdoor")
        apply_status_update(r, self.admin, "assigned", "Team booked", "Use the back path")
        r.refresh_from_db()
        self.assertEqual(r.status, "assigned")
        self.assertTrue(Notification.objects.filter(user=self.ann, message__contains="Assigned").exists())
        self.assertTrue(Notification.objects.filter(user=self.bob, message__contains="route advice").exists())
        apply_status_update(r, self.admin, "resolved", "Fixed")
        r.refresh_from_db()
        self.assertIsNotNone(r.resolved_at)
        self.assertTrue(Notification.objects.filter(user=self.cat, message__startswith="Fixed").exists())

    def test_priority_score_rewards_vulnerable_and_confirmations(self):
        a = self.report(self.ann, urgency="medium")
        b = self.report(self.bob, urgency="medium")
        self.assertGreater(a.priority_score, b.priority_score)

    def test_only_managers_can_update_and_residents_can_vote_once(self):
        r = self.report(self.ann, "outdoor")
        self.client.login(username="bob", password="x")
        self.client.post(reverse("report_update", args=[r.pk]), {"status": "resolved"})
        r.refresh_from_db()
        self.assertEqual(r.status, "received")  # bob is not a manager

        self.client.post(reverse("report_confirm", args=[r.pk]), {"answer": "broken"})
        self.client.post(reverse("report_confirm", args=[r.pk]), {"answer": "fixed"})
        self.assertEqual(r.confirmations.count(), 1)
        self.assertFalse(r.confirmations.get().still_broken)


class BookingTests(Base):
    def setUp(self):
        super().setUp()
        self.pool = Facility.objects.create(name="Pool", capacity=20)
        self.t0 = timezone.now() + timedelta(days=1)

    def test_double_booking_is_refused_by_the_database(self):
        create_booking(self.ann, self.pool, self.t0, self.t0 + timedelta(hours=2))
        with self.assertRaises(BookingError):
            create_booking(self.bob, self.pool, self.t0 + timedelta(hours=1), self.t0 + timedelta(hours=3))
        # back-to-back is fine
        create_booking(self.bob, self.pool, self.t0 + timedelta(hours=2), self.t0 + timedelta(hours=3))
        self.assertEqual(Booking.objects.count(), 2)

    def test_cancelled_booking_frees_the_slot(self):
        b = create_booking(self.ann, self.pool, self.t0, self.t0 + timedelta(hours=2))
        b.status = "cancelled"
        b.save()
        create_booking(self.bob, self.pool, self.t0, self.t0 + timedelta(hours=2))

    def test_cannot_book_during_maintenance_and_bookers_are_warned(self):
        existing = create_booking(self.ann, self.pool, self.t0, self.t0 + timedelta(hours=2))
        block = MaintenanceBlock.objects.create(
            facility=self.pool, starts_at=self.t0 - timedelta(hours=1),
            ends_at=self.t0 + timedelta(hours=1), reason="Pool cleaning")
        announce_block(block)
        self.assertTrue(Notification.objects.filter(user=self.ann, message__contains="clashes").exists())
        self.assertTrue(Notification.objects.filter(user=self.bob, message__contains="closed").exists())
        with self.assertRaises(BookingError):
            create_booking(self.bob, self.pool, self.t0, self.t0 + timedelta(hours=1))
        self.assertEqual(existing.status, "confirmed")

    def test_end_before_start_is_rejected(self):
        with self.assertRaises(BookingError):
            create_booking(self.ann, self.pool, self.t0, self.t0 - timedelta(hours=1))


class InventoryTests(Base):
    def setUp(self):
        super().setUp()
        self.item = Item.objects.create(name="Projector", total_quantity=2, replacement_cost=900, repair_cost=450)
        self.due = timezone.now() + timedelta(days=2)

    def test_cannot_borrow_more_than_available(self):
        borrow_item(self.ann, self.item.pk, 2, self.due)
        self.assertEqual(self.item.available, 0)
        with self.assertRaises(LoanError):
            borrow_item(self.bob, self.item.pk, 1, self.due)

    def test_return_conditions_update_stock_and_points(self):
        loan = borrow_item(self.ann, self.item.pk, 1, self.due)
        record_return(loan, "damaged", "Cracked lens")
        self.item.refresh_from_db()
        self.assertEqual(self.item.out_of_service, 1)
        self.assertEqual(self.item.available, 1)

        loan2 = borrow_item(self.bob, self.item.pk, 1, self.due)
        record_return(loan2, "missing")
        self.item.refresh_from_db()
        self.assertEqual(self.item.total_quantity, 1)

        loan3 = ItemLoan.objects.create(item=self.item, user=self.cat, quantity=1, due_at=self.due)
        before = self.cat.points
        record_return(loan3, "good")
        self.cat.refresh_from_db()
        self.assertEqual(self.cat.points, before + 3)

    def test_replace_advice_after_repeated_damage(self):
        for _ in range(3):
            ItemLoan.objects.create(item=self.item, user=self.ann, quantity=1, due_at=self.due,
                                    returned_at=timezone.now(), return_condition="damaged")
        self.assertIn("REPLACING", self.item.advice)


class InsightTests(Base):
    def test_repeated_reports_at_one_place_become_a_hotspot(self):
        for i in range(4):
            self.report([self.ann, self.bob, self.cat, self.ann][i], "indoor", self.block, "plumbing", f"Leak {i}",
                        spot_detail="Level 3")
        self.report(self.bob, "outdoor", self.path, "pathway", "One-off")
        spots = find_hotspots(days=60, threshold=3)
        self.assertEqual(len(spots), 1)
        self.assertEqual((spots[0]["location"], spots[0]["category"], spots[0]["total"]),
                         ("Block C", "plumbing", 4))
        saved = refresh_insight(spots[0])
        self.assertEqual(saved.source, "rules")  # no API key in tests
        self.assertIn("plumb", saved.suggested_action.lower())

    def test_old_reports_fall_outside_the_window(self):
        for i in range(4):
            r = self.report(self.ann, "outdoor", title=f"Old {i}")
            Report.objects.filter(pk=r.pk).update(created_at=timezone.now() - timedelta(days=200))
        self.assertEqual(find_hotspots(days=60, threshold=3), [])


class PageSmokeTests(TestCase):
    """Load the demo data and open every page as a resident and as a manager."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo", "--reset", verbosity=0)

    def visit(self, username, password, urls):
        self.client.login(username=username, password=password)
        for name, args in urls:
            resp = self.client.get(reverse(name, args=args), follow=True)
            self.assertEqual(resp.status_code, 200, f"{name} failed for {username}")

    def test_resident_pages(self):
        r = Report.objects.filter(scope="outdoor").first()
        self.visit("aisyah", "demo123", [
            ("home", []), ("report_list", []), ("report_create", []), ("report_map", []),
            ("report_detail", [r.pk]), ("facility_list", []), ("facility_detail", [Facility.objects.first().pk]),
            ("my_bookings", []), ("item_list", []), ("item_detail", [Item.objects.first().pk]),
            ("my_loans", []), ("notification_list", []),
        ])

    def test_manager_pages(self):
        loc = Location.objects.get(name="Block C")
        self.visit("admin", "admin123", [
            ("dashboard", []), ("manage_reports", []), ("insights_home", []), ("manage_bookings", []),
            ("manage_inventory", []), ("report_map", []),
            ("insight_proposal", [loc.pk, "plumbing"]),
        ])

    def test_residents_cannot_open_manager_pages(self):
        self.client.login(username="aisyah", password="demo123")
        for name in ("dashboard", "manage_reports", "insights_home", "manage_bookings", "manage_inventory"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 403, name)

    def test_anonymous_users_are_sent_to_login(self):
        resp = self.client.get(reverse("home"))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/accounts/login/", resp["Location"])

    def test_seed_data_has_the_demo_story(self):
        names = {(h["location"], h["category"]) for h in find_hotspots()}
        self.assertIn(("Block C", "plumbing"), names)
        self.assertIn(("Central Walkway", "pathway"), names)
        mei_note = Notification.objects.filter(user__username="mei", message__contains="clashes")
        self.assertTrue(mei_note.exists())
