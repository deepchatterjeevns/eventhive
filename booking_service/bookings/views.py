from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Event
from .serializers import EventSerializer, BookingRequestSerializer
from .services import BookingService
from .auth_client import StatelessJWTAuthentication

class EventListView(APIView):
    def get(self, request):
        events = Event.objects.all().prefetch_related('tickets')
        return Response(EventSerializer(events, many=True).data)

class BookTicketView(APIView):
    def post(self, request):
        # 1. Statelessly authenticate user from Bearer JWT
        user_id = StatelessJWTAuthentication.authenticate(request)

        # 2. Validate incoming ticket IDs
        serializer = BookingRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # 3. Call the concurrency-safe booking logic using Pessimistic Locking
        booking = BookingService.reserve_tickets(
            user_id=user_id,
            ticket_ids=serializer.validated_data['ticket_ids']
        )

        return Response(
            {
                "booking_id": booking.id,
                "status": booking.status,
                "total_amount": str(booking.total_amount),
                "message": "Tickets successfully reserved."
            },
            status=status.HTTP_201_CREATED
        )