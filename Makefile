.PHONY: build up down restart seed logs test-concurrency check clean

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart: down up

seed:
	docker compose exec booking_service python manage.py init_data

logs:
	docker compose logs -f auth_service booking_service

check:
	cd auth_service && python manage.py check
	cd booking_service && python manage.py check
	cd auth_service && python manage.py makemigrations --check --dry-run
	cd booking_service && python manage.py makemigrations --check --dry-run

test-concurrency:
	docker cp tests/bench_concurrency.py eventhive-booking:/app/bench_concurrency.py
	docker compose exec booking_service python bench_concurrency.py --threads 50 --rounds 6

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
