import time
from decimal import Decimal

from django.db import DatabaseError, transaction
from rest_framework.exceptions import ValidationError

from .models import Booking, Ticket, TicketStatus


class BookingService:
    # MySQL can still report a lock-wait deadlock under heavy contention; a short
    # retry lets the loser of the race re-read committed state and fail cleanly.
    DEADLOCK_RETRIES = 3
    RETRY_BACKOFF_SECONDS = 0.05

    @staticmethod
    def reserve_tickets(user_id: int, ticket_ids: list[int]) -> Booking:
        """
        Reserves seats atomically with database row-level locking.

        Deadlock (MySQL 1213) handling:
        1. Requested IDs are de-duplicated and sorted ascending.
        2. The locking query is issued with an explicit ORDER BY id so InnoDB
           walks the PRIMARY index and therefore acquires row locks in
           ascending PK order for every transaction. A circular wait cannot form.
        3. Lock-wait/deadlock errors are retried a bounded number of times.
        """
        if not ticket_ids:
            raise ValidationError("ticket_ids list cannot be empty.")

        ordered_ids = sorted(set(ticket_ids))

        for attempt in range(1, BookingService.DEADLOCK_RETRIES + 1):
            try:
                return BookingService._reserve_once(user_id, ordered_ids)
            except DatabaseError as exc:
                if not BookingService._is_lock_error(exc) or attempt == BookingService.DEADLOCK_RETRIES:
                    raise ValidationError(
                        "Seat reservation failed under contention. Please retry."
                    ) from exc
                time.sleep(BookingService.RETRY_BACKOFF_SECONDS * attempt)

        raise ValidationError("Seat reservation failed. Please retry.")

    @staticmethod
    def _is_lock_error(exc: DatabaseError) -> bool:
        """Detect MySQL deadlock (1213) and lock-wait timeout (1205)."""
        args = getattr(exc, "args", ())
        errno = args[0] if args and isinstance(args[0], int) else None
        if errno in (1213, 1205):
            return True
        return "Deadlock found" in str(exc) or "Lock wait timeout" in str(exc)

    @staticmethod
    @transaction.atomic
    def _reserve_once(user_id: int, ordered_ids: list[int]) -> Booking:
        # Acquire pessimistic write locks in ascending primary-key order.
        locked_tickets = list(
            Ticket.objects.select_for_update().filter(id__in=ordered_ids).order_by("id")
        )

        if len(locked_tickets) != len(ordered_ids):
            raise ValidationError("One or more selected tickets do not exist.")

        # Re-check ordering defensively: locks are held, so a stable sequence is
        # guaranteed for the update phase below.
        locked_tickets.sort(key=lambda ticket: ticket.id)

        for ticket in locked_tickets:
            if ticket.status != TicketStatus.AVAILABLE:
                raise ValidationError(
                    f"Seat {ticket.seat_number} is already taken or locked!"
                )

        total_amount = sum((ticket.price for ticket in locked_tickets), Decimal("0.00"))

        booking = Booking.objects.create(
            user_id=user_id,
            total_amount=total_amount,
            status=Booking.BookingStatus.CONFIRMED,
        )

        for ticket in locked_tickets:
            ticket.status = TicketStatus.BOOKED
            ticket.save(update_fields=["status", "updated_at"])

        booking.tickets.add(*locked_tickets)

        return booking

    @staticmethod
    def reserve_tickets_naive(user_id: int, ticket_ids: list[int]) -> Booking:
        """
        Retained as a baseline control method for benchmarking against race
        conditions. Not wired to any endpoint: never call this from a view.
        """
        with transaction.atomic():
            tickets = list(Ticket.objects.filter(id__in=ticket_ids))

            for ticket in tickets:
                if ticket.status != TicketStatus.AVAILABLE:
                    raise ValidationError(f"Seat {ticket.seat_number} is already booked!")

            total_amount = sum((ticket.price for ticket in tickets), Decimal("0.00"))

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
