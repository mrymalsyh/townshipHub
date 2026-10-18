"""
Fill the database with demo data, so the app looks alive the first time you open it.

    python manage.py seed_demo            (adds demo data)
    python manage.py seed_demo --reset    (wipes the demo data first, then adds it again)

Logins created (password in brackets):
    admin  (admin123)   township manager
    aisyah (demo123)    resident, priority help, Block C
    ravi, mei, hakim, siti, john (demo123)   other residents
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from bookings.models import Booking, Facility, MaintenanceBlock
from bookings.services import announce_block
from core.models import Location
from insights.models import Insight
from inventory.models import Item, ItemLoan
from notifications.models import Notification
from reports.models import Report, ReportConfirmation, ReportTip, ReportUpdate

User = get_user_model()


class Command(BaseCommand):
    help = "Create demo users, places, facilities, items and reports."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing demo data first")

    def handle(self, *args, **opts):
        if opts["reset"]:
            for model in (Notification, Insight, ReportTip, ReportConfirmation, ReportUpdate, Report,
                          Booking, MaintenanceBlock, Facility, ItemLoan, Item, Location):
                model.objects.all().delete()
            User.objects.filter(username__in=[
                "admin", "aisyah", "ravi", "mei", "hakim", "siti", "john"]).delete()
        elif Location.objects.exists():
            self.stdout.write("Demo data already exists. Use --reset to rebuild it.")
            return

        now = timezone.now()
        days_ago = lambda d, h=0: now - timedelta(days=d, hours=h)

        # ---- people -----------------------------------------------------
        admin = User.objects.create_superuser(
            "admin", password="admin123", first_name="Township", last_name="Manager", role="admin")
        people = {}
        for username, first, last, unit, vuln in [
            ("aisyah", "Aisyah", "Rahman", "Block C, 3-12", True),
            ("ravi", "Ravi", "Kumar", "Block C, 3-14", False),
            ("mei", "Mei Ling", "Tan", "Block C, 2-08", False),
            ("hakim", "Hakim", "Ismail", "Block A, 5-01", False),
            ("siti", "Siti", "Aminah", "Block B, 1-03", False),
            ("john", "John", "Lee", "Block D, 4-09", False),
        ]:
            people[username] = User.objects.create_user(
                username, password="demo123", first_name=first, last_name=last,
                unit=unit, is_vulnerable=vuln, points=20)

        # ---- places (demo coordinates, edit freely in the admin) ------------
        def loc(name, kind, lat, lng):
            return Location.objects.create(name=name, kind=kind, latitude=lat, longitude=lng)

        block_a = loc("Block A", "building", 3.2168, 101.5095)
        block_b = loc("Block B", "building", 3.2162, 101.5110)
        block_c = loc("Block C", "building", 3.2155, 101.5102)
        block_d = loc("Block D", "building", 3.2148, 101.5118)
        walkway = loc("Central Walkway", "pathway", 3.2158, 101.5108)
        lakeside = loc("Lakeside Path", "pathway", 3.2171, 101.5125)
        back_path = loc("Block B Back Path", "pathway", 3.2160, 101.5116)
        playground = loc("Playground", "park", 3.2150, 101.5106)
        hall_loc = loc("Community Hall", "facility", 3.2165, 101.5100)
        pool_loc = loc("Swimming Pool", "facility", 3.2172, 101.5112)

        # ---- reports ---------------------------------------------------------
        def make(reporter, location, scope, category, title, spot, age_days, urgency="medium",
                 status="received", desc="", note=None, route=""):
            r = Report.objects.create(
                reporter=people[reporter], location=location, scope=scope, category=category,
                title=title, spot_detail=spot, urgency=urgency, status=status,
                description=desc, alternative_route=route)
            ts = days_ago(age_days)
            Report.objects.filter(pk=r.pk).update(
                created_at=ts, resolved_at=(ts + timedelta(days=2) if status == "resolved" else None))
            ReportUpdate.objects.create(report=r, author=people[reporter], status="received",
                                        note="Report submitted")
            if status != "received":
                ReportUpdate.objects.create(report=r, author=admin, status=status, note=note or "")
            ReportUpdate.objects.filter(report=r).update(created_at=ts)
            return r

        # Hotspot 1: Block C plumbing (indoor, repeating)
        make("aisyah", block_c, "indoor", "plumbing", "Water leaking from bathroom ceiling",
             "Level 3, bathroom", 40, "high", "in_progress", note="Plumber has visited once")
        make("ravi", block_c, "indoor", "plumbing", "Low water pressure and damp wall",
             "Level 3, kitchen wall", 31, "medium", "verified")
        make("mei", block_c, "indoor", "plumbing", "Pipe dripping under sink",
             "Level 2, kitchen", 22, "medium", "received")
        make("aisyah", block_c, "indoor", "plumbing", "Leak came back after repair",
             "Level 3, bathroom", 12, "high", "received")
        make("ravi", block_c, "indoor", "plumbing", "Brown water from tap",
             "Level 3", 6, "medium", "received")
        make("mei", block_c, "indoor", "plumbing", "Wet patch on corridor ceiling",
             "Level 2, corridor", 3, "high", "received")

        # Hotspot 2: Central Walkway pathway damage (outdoor, repeating)
        walk_main = make("hakim", walkway, "outdoor", "pathway", "Cracked tiles, tripping hazard",
                         "Near the bench opposite Block C", 28, "high", "assigned",
                         note="Quick patch scheduled",
                         route="Please use the Block B Back Path while we repair this.")
        make("siti", walkway, "outdoor", "pathway", "Tiles lifted again after rain",
             "Near the bench", 17, "medium", "received")
        make("john", walkway, "outdoor", "pathway", "Hole in the walkway, hard for strollers",
             "Outside Block C lobby", 9, "high", "received")
        make("ravi", walkway, "outdoor", "pathway", "Sunken section, puddles form",
             "Near the bench", 5, "medium", "received")
        make("aisyah", walkway, "outdoor", "pathway", "Wheelchair cannot pass the broken tiles",
             "Outside Block C lobby", 2, "high", "received")

        # Hotspot 3: Lakeside Path lights
        make("siti", lakeside, "outdoor", "lighting", "Street light out", "Lamp 4", 20, "medium",
             "resolved", note="Bulb replaced")
        make("john", lakeside, "outdoor", "lighting", "Lights flicker and go off", "Lamp 4", 10,
             "medium", "received")
        make("hakim", lakeside, "outdoor", "lighting", "Dark stretch, unsafe at night", "Lamp 5",
             4, "high", "received")

        # A few one-offs
        make("mei", playground, "outdoor", "safety", "Broken swing chain", "Left swing", 1, "high",
             "verified", note="Area taped off")
        make("john", block_d, "indoor", "lift", "Lift door slow to close", "Lift 2", 8, "low",
             "in_progress", note="Contractor booked")
        make("hakim", block_a, "indoor", "pest", "Cockroaches in rubbish room", "Ground floor", 14,
             "low", "resolved", note="Pest control done")

        # Neighbour confirmations and a tip on the walkway report
        for u in ("siti", "john", "ravi", "mei"):
            ReportConfirmation.objects.create(report=walk_main, user=people[u], still_broken=True)
        ReportTip.objects.create(report=walk_main, author=people["siti"],
                                 text="The grass path beside Block B is flat and safe for strollers.")

        # ---- facilities ----------------------------------------------------------
        hall = Facility.objects.create(name="Community Hall", capacity=80, location=hall_loc,
                                       description="Air-conditioned hall with stage and tables")
        pool = Facility.objects.create(name="Swimming Pool", capacity=30, location=pool_loc,
                                       description="25m pool, open daily")
        bbq = Facility.objects.create(name="BBQ Pit", capacity=15,
                                      description="Covered pit with 3 grills")
        court = Facility.objects.create(name="Badminton Court", capacity=8,
                                        description="Two courts, lights included")

        def at(day_offset, hour, minutes=0):
            base = timezone.localtime(now) + timedelta(days=day_offset)
            return base.replace(hour=hour, minute=minutes, second=0, microsecond=0)

        Booking.objects.create(facility=hall, user=people["siti"], starts_at=at(2, 14),
                               ends_at=at(2, 18), purpose="Birthday party")
        Booking.objects.create(facility=court, user=people["john"], starts_at=at(1, 19),
                               ends_at=at(1, 21), purpose="Badminton with friends")
        Booking.objects.create(facility=bbq, user=people["hakim"], starts_at=at(3, 18),
                               ends_at=at(3, 21), purpose="Family BBQ")
        # A pool booking that will clash with the cleaning below -> demo of the notice
        Booking.objects.create(facility=pool, user=people["mei"], starts_at=at(1, 9),
                               ends_at=at(1, 10, 30), purpose="Morning swim")
        block = MaintenanceBlock.objects.create(
            facility=pool, starts_at=at(1, 8), ends_at=at(1, 12), reason="Pool cleaning")
        announce_block(block)

        # ---- items and loans ---------------------------------------------------------
        tables = Item.objects.create(name="Folding Tables", total_quantity=20, replacement_cost=120,
                                     repair_cost=30, description="6-foot folding tables")
        chairs = Item.objects.create(name="Plastic Chairs", total_quantity=100, replacement_cost=25,
                                     repair_cost=8)
        projector = Item.objects.create(name="Projector", total_quantity=2, replacement_cost=900,
                                        repair_cost=450, description="HDMI projector with screen")
        Item.objects.create(name="Ladder", total_quantity=3, replacement_cost=250, repair_cost=40,
                            description="2m aluminium ladder")
        Item.objects.create(name="Canopy Tent", total_quantity=4, replacement_cost=400, repair_cost=60)

        # Old returns: the projector has been damaged 3 times -> "consider replacing" advice
        for who, cond, ago in [("ravi", "damaged", 70), ("mei", "good", 55), ("john", "damaged", 40),
                               ("hakim", "damaged", 20)]:
            ItemLoan.objects.create(
                item=projector, user=people[who], quantity=1, due_at=days_ago(ago - 1),
                returned_at=days_ago(ago - 2), return_condition=cond,
                admin_notes="Lens cracked" if cond == "damaged" else "")
        projector.out_of_service = 1
        projector.save(update_fields=["out_of_service"])

        # Active loans, one overdue
        ItemLoan.objects.create(item=tables, user=people["siti"], quantity=6, purpose="Birthday party",
                                due_at=now + timedelta(days=3))
        ItemLoan.objects.create(item=chairs, user=people["siti"], quantity=30, purpose="Birthday party",
                                due_at=now + timedelta(days=3))
        ItemLoan.objects.create(item=tables, user=people["john"], quantity=4, purpose="Block D gathering",
                                due_at=now - timedelta(days=1))

        # ---- a couple of notifications so the bell is not empty ----------------------------
        Notification.objects.create(
            user=people["aisyah"], message="Update on your report 'Water leaking from bathroom ceiling': "
                                           "Work in progress", link=f"/reports/{Report.objects.filter(reporter=people['aisyah']).last().pk}/")

        self.stdout.write(self.style.SUCCESS(
            "Demo data ready.\n  Manager login:  admin / admin123\n  Resident login: aisyah / demo123"))
