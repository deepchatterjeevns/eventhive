from rest_framework import serializers

from .models import Booking, Event, Ticket


class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ["id", "seat_number", "status", "price"]
        read_only_fields = ["id", "status"]


class BookingResponseSerializer(serializers.ModelSerializer):
    tickets = TicketSerializer(many=True, read_only=True)

    class Meta:
        model = Booking
        fields = ["id", "user_id", "total_amount", "status", "created_at", "tickets"]


class BookingRequestSerializer(serializers.Serializer):
    ticket_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
        max_length=100,
    )


class EventSerializer(serializers.ModelSerializer):
    # Deliberately a shallow list: avoids the Event <-> Ticket circular
    # serialization recursion that caused the original 500s.
    tickets = TicketSerializer(many=True, read_only=True)

    class Meta:
        model = Event
        fields = ["id", "name", "venue", "event_date", "total_seats", "tickets"]
