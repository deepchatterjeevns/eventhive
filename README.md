# EventHive (AtomicSeats) — High-Concurrency Distributed Event Booking System

EventHive is a microservices-based event ticket booking backend built with **Python 3.11, Django, Django REST Framework, MySQL 8.0 (InnoDB), Docker, and Kubernetes**. It prevents flash-sale double-booking race conditions using ACID-compliant row-level pessimistic locking (`select_for_update()`).

## Architecture Overview

- **Auth Service (`auth_service`, Port `8001`):** Handles user registration, email-based login, and HMAC-SHA256 JWT access/refresh token issuance via `djangorestframework-simplejwt`.
- **Booking Service (`booking_service`, Port `8002`):** Serves event/seat catalogs and processes atomic ticket reservations using stateless JWT verification (`JWT_SIGNING_KEY`, requiring `exp` and `token_type == "access"`) and InnoDB row locks.
- **Database (`MySQL 8.0`):** Shared `eventhive_db` instance in local/Minikube setups (documented trade-off for simplified local orchestration; logical domain isolation enforced via `user_id` integer references without cross-service foreign keys).

## API Endpoints

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/auth/api/register/` | Public | Register a new attendee account |
| `POST` | `/auth/api/login/` | Public | Authenticate and receive `access` & `refresh` JWTs |
| `GET` | `/auth/api/me/` | Bearer Access JWT | Retrieve authenticated user profile |
| `GET` | `/auth/api/health/` | Public | Auth service MySQL liveness probe |
| `GET` | `/booking/api/events/` | Public | List events and real-time seat status (`AVAILABLE` / `BOOKED`) |
| `POST` | `/booking/api/book/` | Bearer Access JWT | Atomically reserve seats (`201 Created` or `409 Conflict`) |
| `GET` | `/booking/api/health/` | Public | Booking service MySQL liveness probe |

*(Event creation and inventory administration are managed via Django Admin at `/booking/admin/` or via the idempotent `python manage.py init_data` command.)*

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

## 50-Thread Concurrency Benchmark
Run the parametrized 50-thread race condition benchmark against a single seat:
```bash
python tests/test_concurrency_bench.py --threads 50 --ticket-id 1 --strategy pessimistic
```
- **No Lock (`naive`):** 14/50 overbooked seats (28% failure rate).
- **Optimistic CAS (`cas`):** 0/50 overbooked seats, P95 latency 68 ms.
- **Pessimistic Lock (`pessimistic` — `select_for_update().order_by("id")`):** 0/50 overbooked seats, 1 confirmed (`201 Created`), 49 cleanly rejected (`409 Conflict`), 0 deadlocks, P95 latency 54 ms.
