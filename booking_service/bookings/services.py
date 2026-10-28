from rest_framework.exceptions import ValidationError
from .models import Ticket, Booking, TicketStatus

class BookingService:
    @staticmethod
    def reserve_tickets_naive(user_id: int, ticket_ids: list[int]) -> Booking:
        tickets = Ticket.objects.filter(id__in=ticket_ids)

        for ticket in tickets:
            if ticket.status != TicketStatus.AVAILABLE:
                raise ValidationError(f"Seat {ticket.seat_number} is already booked!")

        booking = Booking.objects.create(
            user_id=user_id,
            total_amount=sum(t.price for t in tickets),
            status=Booking.BookingStatus.CONFIRMED
        )

        for ticket in tickets:
            ticket.status = TicketStatus.BOOKED
            ticket.save()
            booking.tickets.add(ticket)

        return booking