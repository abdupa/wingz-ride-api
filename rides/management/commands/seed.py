"""
Generates a realistic dataset: users, rides, and months of ride events.

Deterministic by default. The same --seed produces the same database every
time, so a number quoted in the README or shown on a demo can be reproduced
rather than described.

The data is not uniform noise. It deliberately contains the awkward cases the
tests and the bonus report depend on -- see build_edge_cases below.
"""

import random
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from rides.models import Ride, RideEvent
from users.models import User

PICKUP = "Status changed to pickup"
DROPOFF = "Status changed to dropoff"

ADMIN_EMAIL = "admin@wingz.test"
ADMIN_PASSWORD = "wingz-admin-password"

# First name plus last initial is how the bonus report renders a driver, so
# these produce "Chris H", "Howard Y" and "Randy W" -- the shape the brief's
# sample output uses.
DRIVERS = [("Chris", "Hernandez"), ("Howard", "Yamamoto"), ("Randy", "Watanabe")]

RIDER_NAMES = [
    ("Rita", "Reyes"), ("Ben", "Cruz"), ("Ana", "Santos"), ("Leo", "Garcia"),
    ("Mia", "Torres"), ("Sam", "Flores"), ("Ivy", "Ramos"), ("Nico", "Aquino"),
]

# Roughly Metro Manila, so seeded coordinates are plausible and distance
# sorting returns sensible kilometres rather than nonsense.
CENTRE_LAT, CENTRE_LNG = 14.5826, 120.9787


class Command(BaseCommand):
    help = "Populate the database with users, rides and ride events."

    def add_arguments(self, parser):
        parser.add_argument("--rides", type=int, default=300, help="Rides to create.")
        parser.add_argument("--months", type=int, default=4, help="Months of history.")
        parser.add_argument("--seed", type=int, default=20260820, help="RNG seed.")
        parser.add_argument("--clear", action="store_true", help="Delete existing data first.")

    @transaction.atomic
    def handle(self, *args, **options):
        rng = random.Random(options["seed"])

        if options["clear"]:
            RideEvent.objects.all().delete()
            Ride.objects.all().delete()
            User.objects.all().delete()
            self.stdout.write("Cleared existing rides, events and users.")

        admin = self.build_admin()
        drivers, riders = self.build_people(rng)
        rides, events = self.build_history(rng, drivers, riders, options)
        extra_rides, extra_events = self.build_edge_cases(drivers, riders)

        self.report(admin, drivers, riders, rides + extra_rides, events + extra_events)

    # -- people --------------------------------------------------------------

    def build_admin(self):
        admin, created = User.objects.get_or_create(
            email=ADMIN_EMAIL,
            defaults=dict(
                role=User.Role.ADMIN,
                first_name="Ada",
                last_name="Admin",
                phone_number="+639170000000",
            ),
        )
        if created:
            admin.set_password(ADMIN_PASSWORD)
            admin.save()
        return admin

    def build_people(self, rng):
        def person(first, last, role, index):
            return User(
                role=role,
                first_name=first,
                last_name=last,
                # Lowercased here because bulk_create bypasses save(). The
                # database enforces it too -- a mixed-case address would fail
                # the check constraint rather than quietly break the email
                # filter.
                email=f"{first}.{last}.{index}@example.com".lower(),
                phone_number=f"+63917{rng.randint(1000000, 9999999)}",
                # Riders and drivers never sign in; only the admin does.
                password=make_password(None),
            )

        people = [person(f, l, User.Role.DRIVER, i) for i, (f, l) in enumerate(DRIVERS)]
        people += [person(f, l, User.Role.RIDER, i) for i, (f, l) in enumerate(RIDER_NAMES)]
        User.objects.bulk_create(people, ignore_conflicts=True)

        return (
            list(User.objects.filter(role=User.Role.DRIVER)),
            list(User.objects.filter(role=User.Role.RIDER)),
        )

    # -- the bulk of the history --------------------------------------------

    def build_history(self, rng, drivers, riders, options):
        now = timezone.now()
        window = timedelta(days=30 * options["months"])

        rides = []
        for _ in range(options["rides"]):
            picked_up = now - timedelta(seconds=rng.randint(0, int(window.total_seconds())))
            rides.append(
                Ride(
                    status=Ride.Status.DROPOFF,
                    id_rider=rng.choice(riders),
                    id_driver=rng.choice(drivers),
                    pickup_latitude=CENTRE_LAT + rng.uniform(-0.45, 0.45),
                    pickup_longitude=CENTRE_LNG + rng.uniform(-0.45, 0.45),
                    dropoff_latitude=CENTRE_LAT + rng.uniform(-0.45, 0.45),
                    dropoff_longitude=CENTRE_LNG + rng.uniform(-0.45, 0.45),
                    pickup_time=picked_up,
                )
            )
        rides = Ride.objects.bulk_create(rides)

        events = []
        for ride in rides:
            # A spread that straddles the hour, so the report has something to
            # exclude as well as something to count.
            minutes = rng.choice([18, 25, 40, 55, 58, 61, 70, 95, 130, 180])
            events.append(RideEvent(id_ride=ride, description=PICKUP, created_at=ride.pickup_time))
            events.append(
                RideEvent(
                    id_ride=ride,
                    description=DROPOFF,
                    created_at=ride.pickup_time + timedelta(minutes=minutes),
                )
            )
        RideEvent.objects.bulk_create(events)
        return rides, events

    # -- the awkward cases, on purpose ---------------------------------------

    def build_edge_cases(self, drivers, riders):
        """
        Three shapes that uniform random data would never produce, each one
        the thing a specific test or requirement needs to be provable.
        """
        now = timezone.now()

        def ride(**overrides):
            # Every default goes in the dict, including pickup_time. Building
            # the object with one keyword hardcoded and the rest splatted means
            # an override of that keyword is a TypeError, not an override.
            fields = dict(
                status=Ride.Status.EN_ROUTE,
                id_rider=riders[0],
                id_driver=drivers[0],
                pickup_latitude=CENTRE_LAT,
                pickup_longitude=CENTRE_LNG,
                dropoff_latitude=CENTRE_LAT + 0.05,
                dropoff_longitude=CENTRE_LNG + 0.05,
                pickup_time=now,
            )
            fields.update(overrides)
            return Ride(**fields)

        # 1. Either side of the 24-hour boundary, so todays_ride_events can be
        #    seen including one and excluding the other.
        boundary = ride()
        # 2. Five rides sharing one pickup_time, so ordering ties are visible.
        tied = [ride(pickup_time=now - timedelta(days=1)) for _ in range(5)]
        # 3. A ride with two pickup events. Joining ride_event twice in the
        #    bonus report would count this trip twice; the FILTER aggregate
        #    does not. Without this row the report looks correct either way.
        doubled = ride(pickup_time=now - timedelta(days=2))

        created = Ride.objects.bulk_create([boundary, *tied, doubled])
        boundary, doubled = created[0], created[-1]

        events = RideEvent.objects.bulk_create(
            [
                RideEvent(id_ride=boundary, description=PICKUP,
                          created_at=now - timedelta(hours=23)),
                RideEvent(id_ride=boundary, description=DROPOFF,
                          created_at=now - timedelta(hours=25)),
                RideEvent(id_ride=doubled, description=PICKUP,
                          created_at=doubled.pickup_time),
                RideEvent(id_ride=doubled, description=PICKUP,
                          created_at=doubled.pickup_time + timedelta(minutes=2)),
                RideEvent(id_ride=doubled, description=DROPOFF,
                          created_at=doubled.pickup_time + timedelta(minutes=90)),
            ]
        )
        return created, events

    # -- output --------------------------------------------------------------

    def report(self, admin, drivers, riders, rides, events):
        self.stdout.write(
            self.style.SUCCESS(
                f"\nSeeded {len(rides)} rides, {len(events)} events, "
                f"{len(drivers)} drivers, {len(riders)} riders."
            )
        )
        self.stdout.write(f"  admin login: {admin.email} / {ADMIN_PASSWORD}")
        self.stdout.write("  includes: a ride straddling the 24-hour boundary,")
        self.stdout.write("            five rides sharing one pickup_time,")
        self.stdout.write("            one ride with two pickup events.")
