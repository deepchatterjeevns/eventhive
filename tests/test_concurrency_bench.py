import concurrent.futures
import os
import time
import requests
import jwt

BOOKING_URL = 'http://localhost:8002/api/book/'
EVENTS_URL = 'http://localhost:8002/api/events/'
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-insecure-key-scaler-capstone-9923847291')


def make_token(user_id):
    return jwt.encode(
        {'user_id': user_id, 'exp': int(time.time()) + 3600},
        SECRET_KEY,
        algorithm='HS256',
    )


def get_target_ticket_id():
    try:
        r = requests.get(EVENTS_URL, timeout=5)
        if r.status_code == 200:
            events = r.json()
            for event in events:
                for ticket in event.get('tickets', []):
                    if ticket.get('status') == 'AVAILABLE':
                        return ticket['id']
    except Exception:
        pass
    return 1


def attempt_booking(user_id, ticket_id):
    token = make_token(user_id)
    resp = requests.post(
        BOOKING_URL,
        json={'ticket_ids': [ticket_id]},
        headers={'Authorization': f'Bearer {token}'},
    )
    return user_id, resp.status_code, resp.text


def run_stress_test():
    ticket_id = get_target_ticket_id()
    print(f'Starting simultaneous seat reservation race for ticket ID {ticket_id}...')
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(attempt_booking, 101, ticket_id)
        f2 = executor.submit(attempt_booking, 102, ticket_id)
        results = [f1.result(), f2.result()]

    for user_id, code, body in results:
        print(f'User {user_id}: HTTP {code} -> {body}')


if __name__ == '__main__':
    run_stress_test()
