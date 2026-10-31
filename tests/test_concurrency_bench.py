import concurrent.futures
import requests

BOOKING_URL = "http://localhost:8002/api/book/"

def attempt_booking(user_id):
    resp = requests.post(
        BOOKING_URL,
        json={"ticket_ids": [1]},
        headers={"Authorization": f"Bearer mock_token_user_{user_id}"}
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