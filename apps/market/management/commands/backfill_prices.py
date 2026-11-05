from django.core.management.base import BaseCommand

from apps.market.tasks import backfill


class Command(BaseCommand):
    help = "Queue the history load in the worker (about 15 minutes at free-plan speed). Safe to repeat."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Reload every asset, not only the empty ones.")

    def handle(self, *args, all=False, **options):
        backfill.delay(only_missing=not all)
        self.stdout.write("Queued. Follow it in the admin under Fetch runs or in the worker log.")
