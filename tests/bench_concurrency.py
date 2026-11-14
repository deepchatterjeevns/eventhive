import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import os
from pathlib import Path
import random
import statistics
import sys
import threading
import time

# Bootstrap Django from booking_service
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "booking_service"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "booking_service.settings")

import django

django.setup()

from django.db import DatabaseError, connection, connections, transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from bookings.models import Booking, Event, Ticket, TicketStatus
from bookings.services import BookingService, SeatConflictError

TEST_USER_START = 900_000


def get_innodb_deadlocks() -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT `COUNT` FROM information_schema.INNODB_METRICS WHERE NAME = 'lock_deadlocks'"
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0


@transaction.atomic
def lock_row_by_row_unsorted(user_id: int, ticket_ids: list[int]) -> Booking:
    """Locks seats one query at a time in caller order to demonstrate deadlock risk."""
    ordered_unique = list(dict.fromkeys(ticket_ids))
    tickets = []
    for tid in ordered_unique:
        try:
            tickets.append(Ticket.objects.select_for_update().get(pk=tid))
        except Ticket.DoesNotExist as exc:
            raise ValidationError("Ticket does not exist.") from exc

    for ticket in tickets:
        if ticket.status != TicketStatus.AVAILABLE:
            raise SeatConflictError(f"Seat {ticket.seat_number} is already booked.")

    total = sum((t.price for t in tickets), Decimal("0.00"))
    booking = Booking.objects.create(
        user_id=user_id,
        total_amount=total,
        status=Booking.BookingStatus.CONFIRMED,
    )
    for ticket in tickets:
        ticket.status = TicketStatus.BOOKED
        ticket.save(update_fields=["status", "updated_at"])
    booking.tickets.add(*tickets)
    return booking


STRATEGIES = {
    "naive": BookingService.reserve_tickets_naive,
    "optimistic_cas": BookingService.reserve_tickets_cas,
    "pessimistic_unsorted_loop": lock_row_by_row_unsorted,
    "pessimistic_production": BookingService.reserve_tickets,
}


def seed_round_tickets(label: str, rounds: int, seats_per_round: int) -> tuple[int, list[list[int]]]:
    event = Event.objects.create(
        name=f"BENCH-{label}",
        venue="Local Benchmark",
        event_date=timezone.now(),
        total_seats=rounds * seats_per_round,
    )
    Ticket.objects.bulk_create(
        [
            Ticket(event=event, seat_number=f"R{r}-S{s}", price=Decimal("500.00"))
            for r in range(rounds)
            for s in range(seats_per_round)
        ]
    )
    round_seat_ids = []
    for r in range(rounds):
        seat_names = [f"R{r}-S{s}" for s in range(seats_per_round)]
        ids = list(
            Ticket.objects.filter(event=event, seat_number__in=seat_names)
            .order_by("id")
            .values_list("id", flat=True)
        )
        round_seat_ids.append(ids)
    return event.id, round_seat_ids


def build_batch(scenario: str, seat_ids: list[int], threads: int, rng: random.Random) -> list[list[int]]:
    if scenario == "single":
        return [[seat_ids[0]] for _ in range(threads)]
    if scenario == "opposite":
        a, b = seat_ids
        batch = [[a, b] if i % 2 == 0 else [b, a] for i in range(threads)]
        rng.shuffle(batch)
        return batch
    return [rng.sample(seat_ids, 2) for _ in range(threads)]


def run_case(strategy_name: str, scenario: str, threads: int, rounds: int, seed: int) -> dict:
    reserve_fn = STRATEGIES[strategy_name]
    rng = random.Random(seed)
    seats_needed = {"single": 1, "opposite": 2, "mixed": 6}[scenario]
    event_id, round_sets = seed_round_tickets(f"{strategy_name}-{scenario}", rounds, seats_needed)

    wins = 0
    rejects = 0
    deadlocks = 0
    oversold = 0
    latencies_ms = []
    user_seq = TEST_USER_START

    deadlocks_before = get_innodb_deadlocks()

    try:
        for seat_ids in round_sets:
            barrier = threading.Barrier(threads)
            requests_batch = build_batch(scenario, seat_ids, threads, rng)

            def attempt(args: tuple[int, list[int]]) -> tuple[str, float]:
                uid, target_ids = args
                try:
                    connection.ensure_connection()
                    barrier.wait(timeout=30)
                    t0 = time.perf_counter()
                    try:
                        reserve_fn(uid, target_ids)
                        status = "win"
                    except (SeatConflictError, ValidationError):
                        status = "reject"
                    except DatabaseError as db_err:
                        errno = db_err.args[0] if db_err.args else None
                        status = "deadlock" if errno == 1213 else "error"
                    elapsed_ms = (time.perf_counter() - t0) * 1000.0
                    return status, elapsed_ms
                finally:
                    connections.close_all()

            payloads = [(user_seq + i, ids) for i, ids in enumerate(requests_batch)]
            user_seq += threads

            with ThreadPoolExecutor(max_workers=threads) as pool:
                outcomes = list(pool.map(attempt, payloads))

            for status, ms in outcomes:
                latencies_ms.append(ms)
                if status == "win":
                    wins += 1
                elif status == "reject":
                    rejects += 1
                elif status == "deadlock":
                    deadlocks += 1

            # Audit actual join table duplicates for this round's seats
            dup_rows = (
                Booking.tickets.through.objects.filter(ticket_id__in=seat_ids)
                .values("ticket_id")
                .annotate(cnt=Count("id"))
            )
            oversold += sum(max(0, row["cnt"] - 1) for row in dup_rows)
    finally:
        Booking.objects.filter(user_id__gte=TEST_USER_START).delete()
        Event.objects.filter(pk=event_id).delete()

    deadlocks_after = get_innodb_deadlocks()
    latencies_ms.sort()
    p50 = statistics.median(latencies_ms) if latencies_ms else 0.0
    p95 = latencies_ms[max(0, int(0.95 * len(latencies_ms)) - 1)] if latencies_ms else 0.0

    return {
        "strategy": strategy_name,
        "scenario": scenario,
        "oversold": oversold,
        "wins": wins,
        "rejects": rejects,
        "app_deadlocks": deadlocks,
        "mysql_deadlocks": deadlocks_after - deadlocks_before,
        "p50_ms": round(p50, 1),
        "p95_ms": round(p95, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="EventHive MySQL concurrency benchmark")
    parser.add_argument("--threads", type=int, default=50)
    parser.add_argument("--rounds", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    with connection.cursor() as cur:
        cur.execute("SELECT VERSION(), @@transaction_isolation")
        db_ver, iso_level = cur.fetchone()

    print(f"MySQL={db_ver} | Isolation={iso_level} | Threads={args.threads} | Rounds={args.rounds} | CPUs={os.cpu_count()}")
    for scenario in ("single", "opposite", "mixed"):
        print(f"\n--- Scenario: {scenario} ({args.threads * args.rounds} attempts) ---")
        print(f"{'Strategy':26s} | {'Oversold':8s} | {'Wins':5s} | {'Rejects':7s} | {'Deadlocks(App/DB)':17s} | {'P50 ms':7s} | {'P95 ms':7s}")
        for strat in STRATEGIES:
            res = run_case(strat, scenario, args.threads, args.rounds, args.seed)
            dl_str = f"{res['app_deadlocks']} / {res['mysql_deadlocks']}"
            print(
                f"{res['strategy']:26s} | {res['oversold']:8d} | {res['wins']:5d} | "
                f"{res['rejects']:7d} | {dl_str:17s} | {res['p50_ms']:7.1f} | {res['p95_ms']:7.1f}"
            )


if __name__ == "__main__":
    main()