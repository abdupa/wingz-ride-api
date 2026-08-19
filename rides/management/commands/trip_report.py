"""
Runs the bonus report and prints it.

The query itself lives in rides/reports/trips_over_one_hour.sql so the SQL in
the README is the SQL that runs, rather than a copy that can drift.
"""

from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import connection

QUERY_PATH = Path(__file__).resolve().parents[2] / "reports" / "trips_over_one_hour.sql"


def run_report():
    """Returns [(month, driver, count), ...] ordered by month then driver."""
    with connection.cursor() as cursor:
        cursor.execute(QUERY_PATH.read_text())
        return cursor.fetchall()


class Command(BaseCommand):
    help = "Trips longer than one hour, by month and driver."

    def handle(self, *args, **options):
        rows = run_report()
        if not rows:
            self.stdout.write("No trips over one hour. Try: manage.py seed --clear")
            return

        header = ("Month", "Driver", "Count of Trips > 1 hr")
        widths = [
            max(len(header[i]), max(len(str(row[i])) for row in rows)) for i in range(3)
        ]
        line = "  ".join(h.ljust(w) for h, w in zip(header, widths))
        self.stdout.write(line)
        self.stdout.write("  ".join("-" * w for w in widths))
        for month, driver, count in rows:
            self.stdout.write(
                f"{month.ljust(widths[0])}  {driver.ljust(widths[1])}  {str(count).ljust(widths[2])}"
            )
