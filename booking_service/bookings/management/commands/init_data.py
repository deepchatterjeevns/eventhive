from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from bookings.models import Event, Ticket, TicketStatus


class Command(BaseCommand):
    help = "Idempotently seed demo event and seat records (skips if events already exist unless --force is passed)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Purge existing events/tickets before reseeding",
        )

    def handle(self, *args, **options):
        if not options["force"] and Event.objects.exists():
            self.stdout.write(
                self.style.WARNING("Events already exist in database; skipping seed (use --force to reset).")
            )
            return

        if options["force"]:
            Ticket.objects.all().delete()
            Event.objects.all().delete()

        event = Event.objects.create(
            name="Coldplay: Music of the Spheres World Tour",
            venue="Narendra Modi Stadium, Ahmedabad",
            event_date=timezone.now() + timedelta(days=30),
            total_seats=10,
        )

        tickets = [
            Ticket(
                event=event,
                seat_number=f"A{i}",
                status=TicketStatus.AVAILABLE,
                price=2500.00,
            )
            for i in range(1, 11)
        ]
        Ticket.objects.bulk_create(tickets)
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded event '{event.name}' with {len(tickets)} available tickets."
            )
        )
