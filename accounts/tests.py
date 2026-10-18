from django.test import TestCase
from django.urls import reverse

from .models import User


class ManagerNavigationTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="manager", password="test-password", role=User.ROLE_ADMIN
        )
        self.client.force_login(self.manager)

    def test_overview_renders_grouped_admin_sidebar(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Live Township Map")
        self.assertContains(response, "Incident Management")
        self.assertContains(response, "AI Predictive Insights")
        self.assertContains(response, "Facility Bookings")
        self.assertContains(response, "Inventory &amp; Returns")
        self.assertContains(response, "Admin Profile &amp; Settings")

    def test_manager_can_update_profile_settings(self):
        response = self.client.post(
            reverse("manage_profile"),
            {"first_name": "Alex", "last_name": "Manager", "email": "alex@example.com"},
        )

        self.assertRedirects(response, reverse("manage_profile"))
        self.manager.refresh_from_db()
        self.assertEqual(self.manager.first_name, "Alex")
        self.assertEqual(self.manager.last_name, "Manager")
        self.assertEqual(self.manager.email, "alex@example.com")

    def test_resident_cannot_open_admin_profile_settings(self):
        resident = User.objects.create_user(username="resident", password="test-password")
        self.client.force_login(resident)

        response = self.client.get(reverse("manage_profile"))

        self.assertEqual(response.status_code, 403)
