.PHONY: build up down seed test-concurrency clean

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down -v

seed:
	docker compose exec booking_service python manage.py init_data

test-concurrency:
	python tests/test_concurrency_bench.py

clean:
	find . -type d -name "__pycache__" -exec rm -r {} +
	find . -type f -name "*.pyc" -delete