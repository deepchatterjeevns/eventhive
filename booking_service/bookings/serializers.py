from rest_framework import serializers
from .models import Event, Ticket, Booking

class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ['id', 'seat_number', 'status', 'price']

class EventSerializer(serializers.ModelSerializer):
    tickets = TicketSerializer(many=True, read_only=True)

    class Meta:
        model = Event
        fields = ['id', 'name', 'venue', 'event_date', 'total_seats', 'tickets']

class BookingRequestSerializer(serializers.Serializer):
    ticket_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )