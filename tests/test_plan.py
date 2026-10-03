"""The free plan: up to FREE_PERSONS people per account, then the paid plan is asked for."""
from sqlalchemy import update

from backend import main as m
from tests.test_api import account, book, client, person  # noqa: F401 - fixture and helpers


def test_a_new_account_holds_twenty_people_then_asks_for_the_paid_plan(client):
    account(client)
    me = client.get('/api/me').json()
    assert me['plan'] == 'free' and me['people'] == 0 and me['free_people'] == m.FREE_PERSONS
    sample = client.post('/api/books/sample')
    assert sample.status_code == 201
    assert client.get('/api/me').json()['people'] == 20
    bid = sample.json()['id']
    r = client.post(f'/api/books/{bid}/persons', json={'korean_name': '스물한째', 'generation': 30})
    assert r.status_code == 402 and '20명' in r.json()['detail']
    line = {'korean_name': '판독 인물', 'generation': 30}
    assert client.post(f'/api/books/{bid}/persons/bulk', json={'people': [line]}).status_code == 402
    # A second sample would pass the limit too, and nothing of it is kept.
    assert client.post('/api/books/sample').status_code == 402
    assert len(client.get('/api/books').json()) == 1
    # What is there stays open to change.
    pid = client.get(f'/api/books/{bid}').json()['persons'][0]['id']
    edited = {'korean_name': '고친 이름', 'generation': 25}
    assert client.put(f'/api/persons/{pid}', json=edited).status_code == 200


def test_the_limit_counts_every_book_of_the_account(client):
    account(client)
    first, second = book(client), book(client)
    for n in range(m.FREE_PERSONS):
        person(client, first if n % 2 else second, f'인물{n}')
    assert client.post(f'/api/books/{first}/persons', json={'korean_name': '넘침', 'generation': 1}).status_code == 402


def test_an_account_from_before_the_plans_has_no_limit(client):
    cred = account(client)
    with m.engine.begin() as c:
        c.execute(update(m.users).where(m.users.c.email == cred['email']).values(plan=''))
    assert client.get('/api/me').json()['plan'] == 'paid'
    bid = client.post('/api/books/sample').json()['id']
    assert client.post(f'/api/books/{bid}/persons', json={'korean_name': '스물한째', 'generation': 30}).status_code == 201
