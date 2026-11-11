from django.db import connection
from django.http import JsonResponse
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth_client import StatelessJWTAuthentication
from .models import Event
from .serializers import BookingRequestSerializer, EventSerializer
from .services import BookingService


class EventListView(APIView):
    """Public catalog of events and their current seat inventory."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        events = Event.objects.all().prefetch_related("tickets")
        return Response(EventSerializer(events, many=True).data)


class BookTicketView(APIView):
    """Reserve seats for the authenticated user.

    Authentication is delegated to DRF: StatelessJWTAuthentication verifies the
    Bearer token signed by the auth service, and IsAuthenticated rejects anon
    requests with 401. Availability failures surface as DRF ValidationError,
    which the exception handler renders as HTTP 400.
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [StatelessJWTAuthentication]

    def post(self, request):
        serializer = BookingRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        booking = BookingService.reserve_tickets(
            user_id=request.user.user_id,
            ticket_ids=serializer.validated_data["ticket_ids"],
        )

        return Response(
            {
                "booking_id": booking.id,
                "status": booking.status,
                "total_amount": str(booking.total_amount),
                "message": "Tickets successfully reserved.",
            },
            status=status.HTTP_201_CREATED,
        )


def health_check(request):
    """Liveness/readiness probe: confirms the API and its database are reachable."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "healthy", "service": "booking_service"}, status=200)
    except Exception as exc:  # pragma: no cover - a probe must never raise
        return JsonResponse(
            {"status": "unhealthy", "service": "booking_service", "error": str(exc)},
            status=503,
        )
