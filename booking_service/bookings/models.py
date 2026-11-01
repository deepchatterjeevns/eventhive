import decimal

from django.core.validators import MinValueValidator
from django.db import models


class Event(models.Model):
    name = models.CharField(max_length=200)
    venue = models.CharField(max_length=200)
    event_date = models.DateTimeField()
    total_seats = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.venue}"


class TicketStatus(models.TextChoices):
    AVAILABLE = "AVAILABLE", "Available"
    LOCKED = "LOCKED", "Locked"
    BOOKED = "BOOKED", "Booked"


class Ticket(models.Model):
    event = models.ForeignKey(Event, related_name="tickets", on_delete=models.CASCADE)
    seat_number = models.CharField(max_length=10)
    status = models.CharField(
        max_length=10,
        choices=TicketStatus.choices,
        default=TicketStatus.AVAILABLE,
        db_index=True,
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=decimal.Decimal("500.00"),
        validators=[MinValueValidator(decimal.Decimal("0.00"))],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "seat_number"],
                name="unique_event_seat",
            )
        ]
        # Deterministic PK order keeps select_for_update() locking rows in the
        # same sequence for every transaction, which prevents MySQL 1213 cycles.
        ordering = ["id"]

    def __str__(self):
        return f"Event {self.event_id} | Seat {self.seat_number} | {self.status}"


class Booking(models.Model):
    class BookingStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        CONFIRMED = "CONFIRMED", "Confirmed"
        FAILED = "FAILED", "Failed"

    # Logical reference to the auth service user id. The booking service owns no
    # user table, so integrity is enforced by validation instead of a FK.
    user_id = models.PositiveIntegerField(
        db_index=True,
        validators=[MinValueValidator(1)],
    )
    tickets = models.ManyToManyField(Ticket, related_name="bookings")
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(
        max_length=10,
        choices=BookingStatus.choices,
        default=BookingStatus.CONFIRMED
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking #{self.id} for User {self.user_id} [{self.status}]"
