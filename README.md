# EventHive (AtomicSeats) — High-Concurrency Distributed Event Booking System

EventHive is a microservices-based event ticket booking backend built with **Python 3.11, Django, Django REST Framework, MySQL 8.0 (InnoDB), Docker, and Kubernetes**. It prevents flash-sale double-booking race conditions using ACID-compliant row-level pessimistic locking (`select_for_update().order_by("id")`).

## Architecture Overview

- **Auth Service (`auth_service`, Port `8001`):** Handles user registration, email-based login, and HMAC-SHA256 JWT access/refresh token issuance via `djangorestframework-simplejwt`.
- **Booking Service (`booking_service`, Port `8002`):** Serves event/seat catalogs and processes atomic ticket reservations using stateless JWT verification (`JWT_SIGNING_KEY`, requiring `exp` and `token_type == "access"`) and InnoDB row locks under Django's `READ COMMITTED` session isolation.
- **Database (`MySQL 8.0`):** Shared `eventhive_db` instance in local Docker Compose / Minikube setups (documented trade-off for simplified local orchestration; logical domain isolation enforced via `user_id` integer references without cross-service foreign keys).

## API Endpoints

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/auth/api/register/` | Public | Register a new attendee account (`201 Created`) |
| `POST` | `/auth/api/login/` | Public | Authenticate and receive `access` & `refresh` JWTs (`200 OK`) |
| `GET` | `/auth/api/me/` | Bearer Access JWT | Retrieve authenticated user profile (`200 OK` / `403 Forbidden`) |
| `GET` | `/auth/api/health/` | Public | Auth service MySQL liveness probe (`200 OK` / `503`) |
| `GET` | `/booking/api/events/` | Public | List events and real-time seat status (`AVAILABLE` / `BOOKED`) |
| `POST` | `/booking/api/book/` | Bearer Access JWT | Atomically reserve seats (`201 Created`, `409 Conflict`, or `403 Forbidden`) |
| `GET` | `/booking/api/health/` | Public | Booking service MySQL liveness probe (`200 OK` / `503`) |

*(Note: Event and seat inventory seeding is managed via `python manage.py init_data` rather than `/booking/admin/`, since `booking_service` delegates user management to `auth_service` and does not maintain a separate `auth_user` table.)*

## Local Setup & Running

### 1. Docker Compose
```bash
docker compose up -d --build
docker compose exec booking_service python manage.py init_data
```
*(Note: `init_data` is idempotent and skips reseeding if events already exist; pass `--force` to reset demo seats.)*

### 2. Local Kubernetes (Minikube)
```bash
minikube start --driver=docker
minikube addons enable ingress
chmod +x scripts/build_and_deploy.sh
./scripts/build_and_deploy.sh
```

## Concurrency Benchmark (`tests/bench_concurrency.py`)
Run the in-process 50-thread barrier benchmark directly inside the `booking_service` container against MySQL 8.0 (eliminates Gunicorn sync-worker HTTP queue distortion and audits `information_schema.INNODB_METRICS` `lock_deadlocks`):

```bash
docker cp tests/bench_concurrency.py eventhive-booking:/app/bench_concurrency.py
docker compose exec booking_service python bench_concurrency.py --threads 50 --rounds 6
```

### Measured Results (50 Simultaneous Threads × 6 Rounds = 300 Attempts / Cell, MySQL 8.0.46)
- **No Lock (`naive`):** `294 / 300` oversold seats (`single` scenario; 6 legitimate wins) and `588` oversold seat-assignments (`opposite` `[a, b]` / `[b, a]` scenario).
- **Optimistic CAS (`optimistic_cas`):** `0` oversold seats, `0` deadlocks, `P95 = 61.2 ms` (`single`) / `72.6 ms` (`opposite`).
- **Pessimistic Row-by-Row Unsorted (`pessimistic_loop_unsorted`):** `0` oversold seats, **`149` InnoDB deadlocks** in `opposite` (`[a, b]` vs. `[b, a]`) contention (`P95 = 64.6 ms`).
- **EventHive Production (`BookingService.reserve_tickets` — `select_for_update().order_by("id")` + retry):** **`0` oversold seats, `0` deadlocks (`0` masked), `P95 = 47.9 ms` (`single`) / `48.7 ms` (`opposite`) / `58.7 ms` (`mixed`)**.
