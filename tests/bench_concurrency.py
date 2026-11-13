#!/usr/bin/env python
"""
EventHive concurrency benchmark (in-process, real MySQL, real threads).

Runs N threads (default 50) released at the same instant by a barrier, each in
its own DB connection, against several seat-reservation strategies, and
reports what actually happened. Every number in Table 5.01 of the report should
come from this script's output.

Strategies
  naive                    BookingService.reserve_tickets_naive (no locking)
  optimistic_cas           BookingService.reserve_tickets_cas (conditional UPDATE
                           ... WHERE status='AVAILABLE'; the status column is the "version")
  pessimistic_in_unsorted  select_for_update() on ONE `id IN (...)` query, ids in
                           caller order, ORDER BY removed
  pessimistic_loop_unsorted  select_for_update() one seat at a time, in caller order
  pessimistic_sorted_raw   the real locking path (BookingService._execute_locked_booking),
                           called WITHOUT the retry wrapper so deadlocks stay visible
  eventhive_production     BookingService.reserve_tickets (sorted + retries).
                           Deadlocks swallowed by the retry loop are counted separately.

Scenarios
  single    all threads want the same seat                 -> exactly 1 winner
  opposite  half want [a, b], half want [b, a]             -> exactly 1 winner
  mixed     each thread wants 2 random seats out of 6      -> no seat may be sold twice

Usage (MySQL from docker-compose must be reachable on 127.0.0.1:3306, migrated):
  python tests/bench_concurrency.py
  python tests/bench_concurrency.py --threads 50 --rounds 20 --json results.json
  python tests/bench_concurrency.py --strategies eventhive_production --assert

All data is written under throw-away events named BENCH-* and bookings with
user_id >= 900000, and is deleted afterwards. Seeded demo data is untouched.
"""
import argparse
import itertools
import json
import math
import os
import platform
import random
import sys
import threading
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "booking_service"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "booking_service.settings")
os.environ.setdefault("DB_HOST", "127.0.0.1")  # settings default is the compose hostname "mysql"

import django  # noqa: E402

django.setup()

from django.db import DatabaseError, connection, connections, transaction  # noqa: E402
from django.db.models import Count  # noqa: E402
from django.utils import timezone  # noqa: E402
from rest_framework.exceptions import ValidationError  # noqa: E402

from bookings.models import Booking, Event, Ticket, TicketStatus  # noqa: E402
from bookings.services import BookingService, SeatConflictError  # noqa: E402

USER_ID_BASE = 900_000
_uid = itertools.count(USER_ID_BASE)
_created_events = []
_masked = Counter()  # deadlocks swallowed by BookingService's retry loop

SEATS = {"single": 1, "opposite": 2, "mixed": 6}
EXPECTED_ONE_WINNER = {"single", "opposite"}


# --------------------------------------------------------------------------- helpers
def lock_errno(exc):
    """MySQL error number for deadlock (1213) / lock wait timeout (1205), else None."""
    args = getattr(exc, "args", ())
    errno = args[0] if args and isinstance(args[0], int) else None
    if errno in (1213, 1205):
        return errno
    text = str(exc)
    if "Deadlock found" in text:
        return 1213
    if "Lock wait timeout" in text:
        return 1205
    return None


# --------------------------------------------------------------------------- strategies
def _finalize(user_id, tickets):
    """Shared tail for the pessimistic variants: check, create booking, flip seats."""
    for ticket in tickets:
        if ticket.status != TicketStatus.AVAILABLE:
            raise SeatConflictError(detail=f"Seat {ticket.seat_number} is already taken or locked!")
    total = sum((t.price for t in tickets), Decimal("0.00"))
    booking = Booking.objects.create(
        user_id=user_id, total_amount=total, status=Booking.BookingStatus.CONFIRMED
    )
    for ticket in tickets:
        ticket.status = TicketStatus.BOOKED
        ticket.save(update_fields=["status", "updated_at"])
    booking.tickets.add(*tickets)
    return booking


def naive(user_id, ids):
    return BookingService.reserve_tickets_naive(user_id, ids)


def optimistic_cas(user_id, ids):
    return BookingService.reserve_tickets_cas(user_id, ids)


@transaction.atomic
def pessimistic_in_unsorted(user_id, ids):
    ids = list(dict.fromkeys(ids))  # de-dupe, keep caller order
    # .order_by() guarantees no ORDER BY id is added: "no ordering discipline".
    tickets = list(Ticket.objects.select_for_update().filter(id__in=ids).order_by())
    if len(tickets) != len(ids):
        raise ValidationError("One or more selected tickets do not exist.")
    return _finalize(user_id, tickets)


@transaction.atomic
def pessimistic_loop_unsorted(user_id, ids):
    tickets = []
    for tid in dict.fromkeys(ids):  # lock one row at a time, in caller order
        try:
            tickets.append(Ticket.objects.select_for_update().get(pk=tid))
        except Ticket.DoesNotExist:
            raise ValidationError("One or more selected tickets do not exist.")
    return _finalize(user_id, tickets)


_orig_reserve_once = BookingService._execute_locked_booking  # underlying function, no retries


def pessimistic_sorted_raw(user_id, ids):
    return _orig_reserve_once(user_id, sorted(set(ids)))


def _counting_reserve_once(user_id, ordered_ids):
    try:
        return _orig_reserve_once(user_id, ordered_ids)
    except DatabaseError as exc:
        errno = lock_errno(exc)
        if errno:
            _masked[errno] += 1
        raise


BookingService._execute_locked_booking = staticmethod(_counting_reserve_once)


def eventhive_production(user_id, ids):
    return BookingService.reserve_tickets(user_id, ids)


STRATEGIES = {
    "naive": naive,
    "optimistic_cas": optimistic_cas,
    "pessimistic_in_unsorted": pessimistic_in_unsorted,
    "pessimistic_loop_unsorted": pessimistic_loop_unsorted,
    "pessimistic_sorted_raw": pessimistic_sorted_raw,
    "eventhive_production": eventhive_production,
}


# --------------------------------------------------------------------------- harness
def classify(exc):
    if isinstance(exc, SeatConflictError):
        return "cas_retry" if str(exc.detail).startswith("CAS conflict") else "conflict"
    if isinstance(exc, ValidationError):
        return "conflict"
    if isinstance(exc, DatabaseError):
        return {1213: "deadlock", 1205: "lock_timeout"}.get(lock_errno(exc), "db_error")
    return "other_error"


def worker(fn, user_id, ids, barrier, out):
    try:
        try:
            connection.ensure_connection()  # connect BEFORE the barrier; not part of latency
        except Exception:
            barrier.abort()
            out.append(("harness_error", 0.0))
            return
        try:
            barrier.wait(timeout=60)
        except threading.BrokenBarrierError:
            out.append(("harness_error", 0.0))
            return
        start = time.perf_counter()
        try:
            fn(user_id, ids)
            kind = "success"
        except Exception as exc:  # noqa: BLE001 - we classify everything
            kind = classify(exc)
        out.append((kind, time.perf_counter() - start))
    finally:
        connections.close_all()


def server_deadlocks():
    """Server-side cross-check: InnoDB's own deadlock counter (MySQL 8.0)."""
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT `COUNT` FROM information_schema.INNODB_METRICS WHERE NAME='lock_deadlocks'"
            )
            row = cur.fetchone()
            return int(row[0]) if row else None
    except Exception:  # noqa: BLE001
        return None


def make_event_and_seats(label, n_rounds, seats_per_round):
    event = Event.objects.create(
        name=f"BENCH-{label}",
        venue="bench",
        event_date=timezone.now(),
        total_seats=n_rounds * seats_per_round,
    )
    _created_events.append(event.pk)
    Ticket.objects.bulk_create(
        [
            Ticket(event=event, seat_number=f"R{r}S{s}", price=Decimal("500.00"))
            for r in range(n_rounds)
            for s in range(seats_per_round)
        ]
    )
    rounds = []
    for r in range(n_rounds):
        names = [f"R{r}S{s}" for s in range(seats_per_round)]
        ids = list(
            Ticket.objects.filter(event=event, seat_number__in=names)
            .order_by("id")
            .values_list("id", flat=True)
        )
        rounds.append(ids)
    return rounds


def build_requests(scenario, seat_ids, n, rng):
    if scenario == "single":
        return [[seat_ids[0]] for _ in range(n)]
    if scenario == "opposite":
        a, b = seat_ids
        reqs = [[a, b] if i % 2 == 0 else [b, a] for i in range(n)]
        rng.shuffle(reqs)
        return reqs
    return [rng.sample(seat_ids, 2) for _ in range(n)]  # mixed


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0.0
    return sorted_vals[max(0, math.ceil(p * len(sorted_vals)) - 1)]


def run_cell(name, scenario, n_threads, rounds, seed):
    fn = STRATEGIES[name]
    rng = random.Random(seed)
    seat_rounds = make_event_and_seats(f"{name}-{scenario}", rounds, SEATS[scenario])
    outcomes, latencies, wins = Counter(), [], []
    overbooked = 0
    _masked.clear()
    dl_before = server_deadlocks()

    for seat_ids in seat_rounds:
        out, barrier = [], threading.Barrier(n_threads)
        threads = [
            threading.Thread(target=worker, args=(fn, next(_uid), ids, barrier, out))
            for ids in build_requests(scenario, seat_ids, n_threads, rng)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for kind, secs in out:
            outcomes[kind] += 1
            latencies.append(secs)
        wins.append(sum(1 for kind, _ in out if kind == "success"))

        # Ground truth from the database: any seat attached to >1 booking is oversold.
        per_seat = (
            Booking.tickets.through.objects.filter(ticket_id__in=seat_ids)
            .values("ticket_id")
            .annotate(n=Count("id"))
        )
        overbooked += sum(max(0, row["n"] - 1) for row in per_seat)

    dl_after = server_deadlocks()
    lat = sorted(latencies)
    return {
        "strategy": name,
        "scenario": scenario,
        "attempts": sum(outcomes.values()),
        "success": outcomes["success"],
        "conflict": outcomes["conflict"],
        "cas_retry": outcomes["cas_retry"],
        "deadlock": outcomes["deadlock"],
        "lock_timeout": outcomes["lock_timeout"],
        "contention_failure": outcomes["contention_failure"],
        "other": outcomes["db_error"] + outcomes["other_error"] + outcomes["harness_error"],
        "overbooked": overbooked,
        "masked_deadlocks": sum(_masked.values()),
        "server_deadlocks": None if dl_before is None or dl_after is None else dl_after - dl_before,
        "p50_ms": round(percentile(lat, 0.50) * 1000, 1),
        "p95_ms": round(percentile(lat, 0.95) * 1000, 1),
        "p99_ms": round(percentile(lat, 0.99) * 1000, 1),
        "one_winner_every_round": all(w == 1 for w in wins) if scenario in EXPECTED_ONE_WINNER else None,
    }


def cleanup():
    Booking.objects.filter(user_id__gte=USER_ID_BASE).delete()
    Event.objects.filter(pk__in=_created_events).delete()


def print_table(rows, scenario):
    print(f"\n### Scenario: {scenario}\n")
    print(
        "| Strategy | Overbooked seats | Winners | Clean rejects | CAS retries | Deadlocks (app) "
        "| Deadlocks masked by retry | Deadlocks (server) | Lock timeouts | Other errors | P50 ms | P95 ms |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        srv = "n/a" if r["server_deadlocks"] is None else r["server_deadlocks"]
        print(
            f"| {r['strategy']} | {r['overbooked']} | {r['success']} | {r['conflict']} "
            f"| {r['cas_retry']} | {r['deadlock']} | {r['masked_deadlocks']} | {srv} "
            f"| {r['lock_timeout'] + r['contention_failure']} | {r['other']} "
            f"| {r['p50_ms']} | {r['p95_ms']} |"
        )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--threads", type=int, default=50)
    ap.add_argument("--rounds", type=int, default=10, help="fresh seats + fresh 50-thread race per round")
    ap.add_argument("--scenarios", default=",".join(SEATS), help=f"comma list of {list(SEATS)}")
    ap.add_argument("--strategies", default="all", help=f"comma list of {list(STRATEGIES)} or 'all'")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--json", help="write raw results to this file")
    ap.add_argument("--assert", dest="do_assert", action="store_true",
                    help="exit 1 if eventhive_production oversells, errors, or lets !=1 winner through")
    args = ap.parse_args()

    names = list(STRATEGIES) if args.strategies == "all" else args.strategies.split(",")
    scenarios = args.scenarios.split(",")
    for n in names:
        if n not in STRATEGIES:
            sys.exit(f"unknown strategy {n!r}")
    for s in scenarios:
        if s not in SEATS:
            sys.exit(f"unknown scenario {s!r}")

    try:
        connection.ensure_connection()
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"Cannot reach MySQL ({exc}). Start it with `docker compose up -d mysql` and migrate first.")

    try:
        with connection.cursor() as cur:
            cur.execute("SET GLOBAL innodb_monitor_enable = 'lock_deadlocks'")
    except Exception:  # noqa: BLE001
        pass  # needs privileges; the counter is usually on by default in 8.0

    with connection.cursor() as cur:
        cur.execute("SELECT VERSION(), @@transaction_isolation, @@innodb_lock_wait_timeout")
        version, isolation, lock_wait = cur.fetchone()
    meta = {
        "mysql": version, "isolation": isolation, "innodb_lock_wait_timeout_s": lock_wait,
        "threads": args.threads, "rounds": args.rounds, "seed": args.seed,
        "python": platform.python_version(), "platform": platform.platform(),
        "cpu_count": os.cpu_count(), "date": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    print("## Environment\n" + "\n".join(f"- {k}: {v}" for k, v in meta.items()))
    print(f"\nEach cell = {args.rounds} rounds x {args.threads} simultaneous threads "
          f"= {args.rounds * args.threads} attempts per strategy/scenario.")

    all_rows = []
    try:
        for scenario in scenarios:
            rows = [run_cell(n, scenario, args.threads, args.rounds, args.seed) for n in names]
            all_rows += rows
            print_table(rows, scenario)
    finally:
        cleanup()

    if args.json:
        Path(args.json).write_text(json.dumps({"meta": meta, "results": all_rows}, indent=2))
        print(f"\nRaw results written to {args.json}")

    if args.do_assert:
        bad = [
            r for r in all_rows
            if r["strategy"] == "eventhive_production"
            and (r["overbooked"] or r["other"] or r["contention_failure"]
                 or r["one_winner_every_round"] is False)
        ]
        print("\nASSERT:", "FAIL" if bad else "PASS")
        sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
