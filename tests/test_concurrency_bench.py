import concurrent.futures
import os
import time
import requests
import jwt

BOOKING_URL = "http://localhost:8002/api/book/"
SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-secret-key-change-in-production-0123456789")


def make_token(user_id):
    return jwt.encode(
        {"user_id": user_id, "exp": int(time.time()) + 3600},
        SECRET_KEY,
        algorithm="HS256",
    )


def attempt_booking(user_id):
    token = make_token(user_id)
    resp = requests.post(
        BOOKING_URL,
        json={"ticket_ids": [1]},
        headers={"Authorization": f"Bearer {token}"},
    )
    return user_id, resp.status_code, resp.text


def run_stress_test():
    print("Starting simultaneous seat reservation race...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_booking, 101)
        f2 = executor.submit(attempt_booking, 102)
        results = [f1.result(), f2.result()]

    for user_id, code, body in results:
        print(f"User {user_id}: HTTP {code} -> {body}")


if __name__ == "__main__":
    run_stress_test()