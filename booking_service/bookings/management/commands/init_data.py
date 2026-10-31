from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from bookings.models import Event, Ticket, TicketStatus

class Command(BaseCommand):
    help = "Seed database with demo concert and seats"

    def handle(self, *args, **kwargs):
        Ticket.objects.all().delete()
        Event.objects.all().delete()

        event = Event.objects.create(
            name="Coldplay: Music of the Spheres Tour",
            venue="Narendra Modi Stadium",
            event_date=timezone.now() + timedelta(days=30),
            total_seats=10
        )

        tickets = [
            Ticket(event=event, seat_number=f"A{i}", status=TicketStatus.AVAILABLE, price=2500.00)
            for i in range(1, 11)
        ]
        Ticket.objects.bulk_create(tickets)
        self.stdout.write(self.style.SUCCESS("Successfully seeded 10 tickets for Coldplay concert."))