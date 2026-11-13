from django.db import connection
from django.http import JsonResponse
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from .auth_client import StatelessJWTAuthentication
from .models import Event
from .serializers import (
    BookingRequestSerializer,
    BookingResponseSerializer,
    EventSerializer,
)
from .services import BookingService


class EventListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        events = Event.objects.all().prefetch_related("tickets")
        return Response(EventSerializer(events, many=True).data)


class BookTicketView(APIView):
    authentication_classes = [StatelessJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = BookingRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        booking = BookingService.reserve_tickets(
            user_id=request.user.id,
            ticket_ids=serializer.validated_data["ticket_ids"],
        )
        return Response(
            BookingResponseSerializer(booking).data,
            status=status.HTTP_201_CREATED,
        )


def health_check(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "healthy", "service": "booking_service"}, status=200)
    except Exception as exc:
        return JsonResponse({"status": "unhealthy", "error": str(exc)}, status=503)
