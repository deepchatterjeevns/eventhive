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
        user_id = StatelessJWTAuthentication.authenticate(request)
        serializer = BookingRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        booking = BookingService.reserve_tickets_naive(
            user_id=user_id,
            ticket_ids=serializer.validated_data['ticket_ids']
        )
        return Response({"booking_id": booking.id, "status": booking.status}, status=status.HTTP_201_CREATED)