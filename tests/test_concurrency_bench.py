import argparse
from datetime import datetime, timedelta, timezone
import os
import statistics
import threading
import time
import jwt
import requests

try:
    import MySQLdb
except ImportError:
    MySQLdb = None

BOOKING_URL = os.getenv("BOOKING_URL", "http://localhost:8002/api/book/")
JWT_SIGNING_KEY = os.getenv(
    "JWT_SIGNING_KEY",
    os.getenv("SECRET_KEY", "dev-insecure-key-scaler-capstone-9923847291"),
)

# Optional MySQL connection params for direct DB & Innodb_deadlocks verification
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "eventhive_db")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "rootpassword")


def make_access_token(user_id: int) -> str:
    payload = {
        "user_id": user_id,
        "token_type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
    }
    return jwt.encode(payload, JWT_SIGNING_KEY, algorithm="HS256")


def inspect_mysql_state():
    """Reads Innodb_deadlocks counter and checks for duplicate ticket bookings in MySQL."""
    if MySQLdb is None:
        return None
    try:
        conn = MySQLdb.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            passwd=DB_PASSWORD,
            db=DB_NAME,
            connect_timeout=3,
        )
        cur = conn.cursor()
        cur.execute("SHOW GLOBAL STATUS LIKE 'Innodb_deadlocks';")
        row = cur.fetchone()
        deadlocks = int(row[1]) if row else 0

        cur.execute(
            """
            SELECT ticket_id, COUNT(*) AS cnt
            FROM bookings_booking_tickets
            GROUP BY ticket_id
            HAVING cnt > 1;
            """
        )
        duplicate_tickets = cur.fetchall()
        cur.close()
        conn.close()
        return {"deadlocks": deadlocks, "duplicate_tickets": len(duplicate_tickets)}
    except Exception:
        return None


def get_available_ticket_ids(count: int = 2) -> list[int]:
    """Fetch real ticket IDs from the events catalog so we don't hardcode PKs."""
    try:
        r = requests.get("http://localhost:8002/api/events/", timeout=5)
        if r.status_code == 200:
            events = r.json()
            ids = []
            for event in events:
                for ticket in event.get("tickets", []):
                    if ticket.get("status") == "AVAILABLE":
                        ids.append(ticket["id"])
            if len(ids) >= count:
                return ids[:count]
            return ids
    except Exception:
        pass
    return [1]


def run_benchmark(num_threads: int, strategy: str, scenario: str):
    barrier = threading.Barrier(num_threads, timeout=20)
    results = []  # list of (status_code, latency_seconds, response_text)
    lock = threading.Lock()

    available_ids = get_available_ticket_ids(count=2)
    pre_db = inspect_mysql_state()

    def worker(user_id: int, ticket_ids: list[int]):
        token = make_access_token(user_id)
        try:
            barrier.wait()  # Release all 50 threads at the exact same instant
        except threading.BrokenBarrierError:
            with lock:
                results.append((0, 0.0, "Barrier timeout"))
            return

        t0 = time.perf_counter()
        try:
            resp = requests.post(
                f"{BOOKING_URL}?strategy={strategy}",
                json={"ticket_ids": ticket_ids},
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            elapsed = time.perf_counter() - t0
            with lock:
                results.append((resp.status_code, elapsed, resp.text))
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            with lock:
                results.append((500, elapsed, str(exc)))

    threads = []
    for i in range(1, num_threads + 1):
        if scenario == "multiseat" and len(available_ids) >= 2:
            # Alternate [id1, id2] and [id2, id1] to stress-test bidirectional lock ordering
            seats = [available_ids[0], available_ids[1]] if i % 2 == 0 else [available_ids[1], available_ids[0]]
        else:
            # All threads contend for the first available seat
            seats = [available_ids[0]]
        threads.append(threading.Thread(target=worker, args=(1000 + i, seats)))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    post_db = inspect_mysql_state()

    wins = sum(1 for code, _, _ in results if code == 201)
    rejections = sum(1 for code, _, _ in results if code in (400, 409))
    errors = sum(1 for code, _, _ in results if code not in (201, 400, 409))
    latencies_ms = sorted(lat * 1000.0 for _, lat, _ in results if lat > 0)

    p50 = statistics.median(latencies_ms) if latencies_ms else 0.0
    p95_idx = max(0, int(0.95 * len(latencies_ms)) - 1)
    p95 = latencies_ms[p95_idx] if latencies_ms else 0.0

    deadlock_delta = "N/A"
    db_dups = "N/A"
    if pre_db is not None and post_db is not None:
        deadlock_delta = str(post_db["deadlocks"] - pre_db["deadlocks"])
        db_dups = str(post_db["duplicate_tickets"])

    expected_wins = 1
    overbooked = max(0, wins - expected_wins)

    print(
        f"Strategy={strategy:11s} | Scenario={scenario:9s} | Threads={num_threads} | "
        f"201_Wins={wins:2d} | Overbooked={overbooked:2d} | Rejections(400/409)={rejections:2d} | "
        f"500_Errors={errors:2d} | Deadlocks={deadlock_delta} | DB_Dups={db_dups} | "
        f"P50={p50:5.1f}ms | P95={p95:5.1f}ms"
    )

    if strategy != "naive":
        assert wins == expected_wins, f"Expected 1 winner, got {wins}!"
        assert errors == 0, f"Unexpected server/auth errors: {errors}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EventHive 50-thread barrier concurrency benchmark")
    parser.add_argument("--threads", type=int, default=50)
    parser.add_argument("--strategy", choices=["naive", "cas", "pessimistic"], default="pessimistic")
    parser.add_argument("--scenario", choices=["single", "multiseat"], default="single")
    args = parser.parse_args()
    run_benchmark(args.threads, args.strategy, args.scenario)