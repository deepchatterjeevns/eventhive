from decimal import Decimal
from django.db import transaction
from rest_framework.exceptions import ValidationError
from .models import Ticket, Booking, TicketStatus


class BookingService:
    @staticmethod
    def reserve_tickets(user_id: int, ticket_ids: list[int]) -> Booking:
        """
        Reserves seats atomically with database row-level locking.
        
        Fix for Deadlock (1213):
        Enforces a deterministic ascending sort order on ticket IDs. 
        When all concurrent transactions acquire row locks in the exact same 
        order (lowest ID to highest ID), a circular lock-wait graph cannot form.
        """
        if not ticket_ids:
            raise ValidationError("ticket_ids list cannot be empty.")

        # 1. Deduplicate and sort IDs to eliminate deadlock cycles
        ordered_ids = sorted(list(set(ticket_ids)))

        with transaction.atomic():
            # 2. Acquire pessimistic write lock in sorted order
            locked_tickets = list(
                Ticket.objects.select_for_update()
                .filter(id__in=ordered_ids)
            )

            # 3. Ensure all requested tickets exist
            if len(locked_tickets) != len(ordered_ids):
                raise ValidationError("One or more selected tickets do not exist.")

            # 4. Verify all seats are currently AVAILABLE
            for ticket in locked_tickets:
                if ticket.status != TicketStatus.AVAILABLE:
                    raise ValidationError(
                        f"Seat {ticket.seat_number} is already taken or locked!"
                    )

            # 5. Compute total amount
            total_amount = sum((t.price for t in locked_tickets), Decimal('0.00'))

            # 6. Create booking record
            booking = Booking.objects.create(
                user_id=user_id,
                total_amount=total_amount,
                status=Booking.BookingStatus.CONFIRMED,
            )

            # 7. Update ticket statuses to BOOKED
            for ticket in locked_tickets:
                ticket.status = TicketStatus.BOOKED
                ticket.save(update_fields=['status', 'updated_at'])
                booking.tickets.add(ticket)

        return booking

    @staticmethod
    def reserve_tickets_naive(user_id: int, ticket_ids: list[int]) -> Booking:
        """
        Retained as a baseline control method for benchmarking against race conditions.
        """
        tickets = Ticket.objects.filter(id__in=ticket_ids)

        for ticket in tickets:
            if ticket.status != TicketStatus.AVAILABLE:
                raise ValidationError(f"Seat {ticket.seat_number} is already booked!")

        total_amount = sum((t.price for t in tickets), Decimal('0.00'))

        booking = Booking.objects.create(
            user_id=user_id,
            total_amount=total_amount,
            status=Booking.BookingStatus.CONFIRMED,
        )

        for ticket in tickets:
            ticket.status = TicketStatus.BOOKED
            ticket.save()
            booking.tickets.add(ticket)

        return booking