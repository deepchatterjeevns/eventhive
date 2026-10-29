from django.db import transaction
from rest_framework.exceptions import ValidationError
from .models import Ticket, Booking, TicketStatus

class BookingService:
    @staticmethod
    def reserve_tickets(user_id: int, ticket_ids: list[int]) -> Booking:
        with transaction.atomic():
            locked_tickets = list(
                Ticket.objects.select_for_update()
                .filter(id__in=ticket_ids)
            )

            if len(locked_tickets) != len(ticket_ids):
                raise ValidationError("One or more selected tickets do not exist.")

            for ticket in locked_tickets:
                if ticket.status != TicketStatus.AVAILABLE:
                    raise ValidationError(f"Seat {ticket.seat_number} is already taken!")

            booking = Booking.objects.create(
                user_id=user_id,
                total_amount=sum(t.price for t in locked_tickets),
                status=Booking.BookingStatus.CONFIRMED
            )

            for ticket in locked_tickets:
                ticket.status = TicketStatus.BOOKED
                ticket.save(update_fields=['status', 'updated_at'])
                booking.tickets.add(ticket)

        return booking