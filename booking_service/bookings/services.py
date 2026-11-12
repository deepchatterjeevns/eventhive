from decimal import Decimal
import random
import time
from django.db import OperationalError, transaction
from rest_framework.exceptions import APIException, ValidationError
from .models import Booking, Ticket, TicketStatus


class SeatConflictError(APIException):
    status_code = 409
    default_detail = "One or more selected seats are already booked or locked."
    default_code = "seat_conflict"


class BookingService:
    MAX_RETRIES = 3

    @classmethod
    def reserve_tickets(cls, user_id: int, ticket_ids: list[int]) -> Booking:
        """
        Reserves seats atomically using InnoDB row-level pessimistic locking
        (SELECT ... FOR UPDATE) with deterministic primary-key ordering and
        bounded retry backoff for transient lock contention.
        """
        if not ticket_ids:
            raise ValidationError("ticket_ids list cannot be empty.")

        ordered_ids = sorted(set(ticket_ids))

        for attempt in range(1, cls.MAX_RETRIES + 1):
            try:
                return cls._execute_locked_booking(user_id, ordered_ids)
            except OperationalError as exc:
                # Retry transient InnoDB deadlock (1213) or lock wait timeout (1205)
                mysql_code = exc.args[0] if exc.args else None
                if mysql_code in (1205, 1213) and attempt < cls.MAX_RETRIES:
                    time.sleep(0.02 * attempt + random.uniform(0, 0.01))
                    continue
                raise

    @staticmethod
    def _execute_locked_booking(user_id: int, ordered_ids: list[int]) -> Booking:
        with transaction.atomic():
            locked_tickets = list(
                Ticket.objects.select_for_update()
                .filter(id__in=ordered_ids)
                .order_by("id")
            )

            if len(locked_tickets) != len(ordered_ids):
                raise ValidationError("One or more selected tickets do not exist.")

            for ticket in locked_tickets:
                if ticket.status != TicketStatus.AVAILABLE:
                    raise SeatConflictError(
                        detail=f"Seat {ticket.seat_number} is already taken or locked!"
                    )

            total_amount = sum((t.price for t in locked_tickets), Decimal("0.00"))
            booking = Booking.objects.create(
                user_id=user_id,
                total_amount=total_amount,
                status=Booking.BookingStatus.CONFIRMED,
            )

            for ticket in locked_tickets:
                ticket.status = TicketStatus.BOOKED
                ticket.save(update_fields=["status", "updated_at"])
                booking.tickets.add(ticket)

            return booking

    @staticmethod
    def reserve_tickets_cas(user_id: int, ticket_ids: list[int]) -> Booking:
        """
        Optimistic Compare-And-Swap (CAS) strategy using conditional UPDATE
        WHERE status='AVAILABLE'. Used as a comparative benchmark strategy.
        """
        ordered_ids = sorted(set(ticket_ids))
        with transaction.atomic():
            tickets = list(Ticket.objects.filter(id__in=ordered_ids).order_by("id"))
            if len(tickets) != len(ordered_ids):
                raise ValidationError("One or more selected tickets do not exist.")

            updated_count = Ticket.objects.filter(
                id__in=ordered_ids,
                status=TicketStatus.AVAILABLE,
            ).update(status=TicketStatus.BOOKED)

            if updated_count != len(ordered_ids):
                raise SeatConflictError(
                    detail="CAS conflict: one or more seats were claimed concurrently."
                )

            total_amount = sum((t.price for t in tickets), Decimal("0.00"))
            booking = Booking.objects.create(
                user_id=user_id,
                total_amount=total_amount,
                status=Booking.BookingStatus.CONFIRMED,
            )
            booking.tickets.add(*tickets)
            return booking

    @staticmethod
    def reserve_tickets_naive(user_id: int, ticket_ids: list[int]) -> Booking:
        """
        Un-locked baseline retained strictly for concurrency benchmark comparison.
        """
        tickets = list(Ticket.objects.filter(id__in=ticket_ids))
        for ticket in tickets:
            if ticket.status != TicketStatus.AVAILABLE:
                raise SeatConflictError(detail=f"Seat {ticket.seat_number} is already booked!")

        total_amount = sum((t.price for t in tickets), Decimal("0.00"))
        booking = Booking.objects.create(
            user_id=user_id,
            total_amount=total_amount,
            status=Booking.BookingStatus.CONFIRMED,
        )
        for ticket in tickets:
            ticket.status = TicketStatus.BOOKED
            ticket.save(update_fields=["status", "updated_at"])
            booking.tickets.add(ticket)
        return booking
