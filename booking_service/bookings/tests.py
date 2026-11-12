from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as dt_timezone
import jwt
from django.conf import settings
from django.db import close_old_connections
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient
from bookings.models import Booking, Event, Ticket, TicketStatus


class EventHiveConcurrencyAndAuthTests(TransactionTestCase):
    def setUp(self):
        self.event = Event.objects.create(
            name="Coldplay Live",
            venue="Ahmedabad",
            event_date=timezone.now() + timedelta(days=10),
            total_seats=2,
        )
        self.t1 = Ticket.objects.create(
            event=self.event, seat_number="A1", status=TicketStatus.AVAILABLE, price=2500
        )
        self.t2 = Ticket.objects.create(
            event=self.event, seat_number="A2", status=TicketStatus.AVAILABLE, price=2500
        )

    def _make_token(self, user_id: int, token_type: str = "access") -> str:
        signing_key = getattr(settings, "JWT_SIGNING_KEY", settings.SECRET_KEY)
        payload = {
            "user_id": user_id,
            "token_type": token_type,
            "exp": datetime.now(dt_timezone.utc) + timedelta(minutes=15),
        }
        return jwt.encode(payload, signing_key, algorithm="HS256")

    def test_refresh_token_is_rejected_on_booking_endpoint(self):
        client = APIClient()
        refresh_token = self._make_token(user_id=101, token_type="refresh")
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh_token}")
        resp = client.post("/api/book/", {"ticket_ids": [self.t1.id]}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_concurrent_bookings_allow_only_single_winner(self):
        def worker(uid: int):
            close_old_connections()
            client = APIClient()
            token = self._make_token(user_id=uid, token_type="access")
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            res = client.post("/api/book/", {"ticket_ids": [self.t1.id]}, format="json")
            close_old_connections()
            return res.status_code

        with ThreadPoolExecutor(max_workers=10) as pool:
            statuses = list(pool.map(worker, range(1, 11)))

        self.assertEqual(statuses.count(201), 1)
        self.assertEqual(statuses.count(409), 9)
        self.assertEqual(Booking.objects.count(), 1)
