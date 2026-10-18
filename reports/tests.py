from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from bookings.models import Facility, MaintenanceBlock
from core.models import Location

from .models import Report


User = get_user_model()


class CommunityMapTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            username="map-manager", password="test-password", role="admin"
        )
        self.resident = User.objects.create_user(
            username="map-resident", password="test-password"
        )
        self.walkway = Location.objects.create(
            name="Central Walkway", kind="pathway", latitude=3.2, longitude=101.5
        )

    def create_report(self, reporter, **kwargs):
        defaults = {
            "location": self.walkway,
            "scope": Report.SCOPE_OUTDOOR,
            "category": "pathway",
            "title": "Damaged walkway",
        }
        defaults.update(kwargs)
        return Report.objects.create(reporter=reporter, **defaults)

    def test_resident_map_includes_resolved_public_reports_but_not_private_reports(self):
        active = self.create_report(self.resident, title="Open path damage")
        resolved = self.create_report(
            self.manager, title="Resolved light", category="lighting", status="resolved"
        )
        private_location = Location.objects.create(
            name="Private Block", kind="building", latitude=3.201, longitude=101.501
        )
        self.create_report(
            self.resident, location=private_location, scope=Report.SCOPE_INDOOR,
            category="plumbing", title="Private leak",
        )
        self.client.force_login(self.resident)

        response = self.client.get(reverse("report_map"))

        self.assertEqual(response.status_code, 200)
        pins = response.context["pins"]
        self.assertEqual({pin["id"] for pin in pins}, {active.pk, resolved.pk})
        self.assertFalse(next(pin for pin in pins if pin["id"] == active.pk)["can_vote"])
        self.assertTrue(next(pin for pin in pins if pin["id"] == resolved.pk)["can_vote"])
        self.assertEqual(response.context["predictive_alerts"], [])
        self.assertContains(response, "Suggested Detours")

    def test_resident_can_vote_for_another_resident_report_but_not_their_own(self):
        own_report = self.create_report(self.resident, title="My report")
        other_report = self.create_report(self.manager, title="Neighbour report")
        self.client.force_login(self.resident)

        own_response = self.client.get(reverse("report_detail", args=[own_report.pk]))
        other_response = self.client.get(reverse("report_detail", args=[other_report.pk]))

        self.assertNotContains(own_response, "It is still broken")
        self.assertContains(own_response, "cannot vote on your own report")
        self.assertContains(other_response, "It is still broken")
        self.assertContains(other_response, "It looks fixed")

    def test_manager_map_shows_predictive_alert_for_recent_repeating_reports(self):
        for index in range(3):
            self.create_report(
                self.resident,
                title=f"Walkway issue {index}",
                urgency="high" if index == 0 else "medium",
            )
        nearby_location = Location.objects.create(
            name="Nearby Path", kind="pathway", latitude=3.2, longitude=101.5002
        )
        self.create_report(self.resident, location=nearby_location, title="Nearby path issue")
        far_location = Location.objects.create(
            name="Far Path", kind="pathway", latitude=3.2, longitude=101.502
        )
        self.create_report(self.resident, location=far_location, title="Far path issue")
        self.client.force_login(self.manager)

        response = self.client.get(reverse("report_map"))

        self.assertEqual(response.status_code, 200)
        alerts = response.context["predictive_alerts"]
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["count"], 4)
        self.assertIn("Suggested action:", response.content.decode())

    def test_cluster_map_assets_and_filter_controls_are_included(self):
        self.create_report(self.resident)
        self.client.force_login(self.resident)

        response = self.client.get(reverse("report_map"))

        self.assertContains(response, "leaflet.markercluster@1.5.3")
        self.assertContains(response, 'data-map-filter="active"')
        self.assertContains(response, 'data-map-filter="maintenance"')
        self.assertContains(response, 'data-map-filter="detours"')
        self.assertContains(response, 'data-map-mode="heat"')
        self.assertContains(response, 'data-radius="500"')
        self.assertContains(response, 'id="route-form"')

    def test_quick_jump_uses_resident_block_and_mapped_facility_coordinates(self):
        self.resident.unit = "Block C, 3-12"
        self.resident.save(update_fields=["unit"])
        block = Location.objects.create(
            name="Block C", kind="building", latitude=3.201, longitude=101.501
        )
        pool_location = Location.objects.create(
            name="Swimming Pool", kind="facility", latitude=3.202, longitude=101.502
        )
        pool = Facility.objects.create(name="Swimming Pool", location=pool_location)
        MaintenanceBlock.objects.create(
            facility=pool,
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(hours=2),
            reason="Pool cleaning",
        )
        self.client.force_login(self.resident)

        response = self.client.get(reverse("report_map"))

        self.assertEqual(response.status_code, 200)
        zones = {zone["key"]: zone for zone in response.context["quick_zones"]}
        self.assertEqual(zones["my-block"]["location_name"], block.name)
        self.assertTrue(zones["clubhouse-pool"]["available"])
        self.assertEqual(zones["clubhouse-pool"]["facilities"][0]["status"], "Closed for maintenance")
        self.assertFalse(zones["school-zone"]["available"])
        self.assertContains(response, "Maintenance at Swimming Pool")

    def test_todays_detour_is_announced_and_links_to_its_report(self):
        report = self.create_report(
            self.resident, title="Blocked pathway", alternative_route="Use the side path."
        )
        self.client.force_login(self.resident)

        response = self.client.get(reverse("report_map"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Detour notice at Central Walkway")
        self.assertContains(response, reverse("report_detail", args=[report.pk]))
