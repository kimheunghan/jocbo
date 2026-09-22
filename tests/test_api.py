import os
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select

from backend import main as m


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine(os.getenv('TEST_DATABASE_URL', 'sqlite:///' + str(tmp_path / 'test.db')))
    if engine.dialect.name == 'sqlite':
        @event.listens_for(engine, 'connect')
        def fk(conn, _):
            conn.execute('PRAGMA foreign_keys=ON')
    monkeypatch.setattr(m, 'engine', engine)
    monkeypatch.setattr(m, 'UPLOADS', tmp_path / 'uploads')
    with TestClient(m.app) as c:
        yield c
    engine.dispose()


def account(client):
    credentials = {'email': uuid.uuid4().hex + '@example.test', 'password': 'SamplePass123!'}
    assert client.post('/api/register', json=credentials).status_code == 201
    assert client.post('/api/login', json=credentials).status_code == 200
    return credentials


def book(client):
    return client.post('/api/books', json={'title': '가상 족보'}).json()['id']


def person(client, bid, name='가상 인물'):
    r = client.post(f'/api/books/{bid}/persons', json={'korean_name': name, 'hanja_name': '假想', 'generation': 1})
    assert r.status_code == 201
    return r.json()['id']


def test_authentication_and_logout(client):
    assert client.get('/api/books').status_code == 401
    cred = account(client)
    assert client.post('/api/register', json=cred).status_code == 409
    assert client.post('/api/login', json={**cred, 'password': 'Incorrect123'}).status_code == 401
    assert client.get('/api/me').json()['email'] == cred['email']
    token = client.cookies.get('session')
    assert client.post('/api/logout').status_code == 200
    client.cookies.set('session', token)
    assert client.get('/api/me').status_code == 401


def test_person_crud_and_dates(client):
    account(client)
    bid = book(client)
    pid = person(client, bid)
    assert client.put(f'/api/persons/{pid}', json={'korean_name': '수정 이름', 'generation': 2, 'birth_date': '2020-02-30'}).status_code == 422
    assert client.put(f'/api/persons/{pid}', json={'korean_name': '수정 이름', 'birth_date': '2020-01-01', 'death_date': '2019-01-01'}).status_code == 422
    assert client.put(f'/api/persons/{pid}', json={'korean_name': '수정 이름', 'hanja_name': '修正', 'bon_gwan': '天安', 'generation': 2}).status_code == 200
    saved = client.get(f'/api/books/{bid}').json()['persons'][0]
    assert saved['korean_name'] == '수정 이름'
    assert saved['bon_gwan'] == '天安'
    assert client.delete(f'/api/persons/{pid}').status_code == 200
    assert client.get(f'/api/books/{bid}').json()['persons'] == []


def test_book_metadata_can_be_created_and_edited(client):
    account(client)
    created = client.post('/api/books', json={
        'title': '청도김씨대동보', 'clan_name': '김씨', 'bon_gwan': '청도',
        'branch_name': '외오산파', 'volume': '9'
    })
    assert created.status_code == 201
    bid = created.json()['id']
    saved = client.get(f'/api/books/{bid}').json()
    assert (saved['bon_gwan'], saved['branch_name'], saved['volume']) == ('청도', '외오산파', '9')
    updated = {key: saved[key] for key in ['title', 'clan_name', 'bon_gwan', 'branch_name', 'volume', 'description']}
    updated['volume'] = '10'
    assert client.put(f'/api/books/{bid}', json=updated).status_code == 200
    assert client.get(f'/api/books/{bid}').json()['volume'] == '10'
    automatic = client.post('/api/books', json={'title': '새 족보'}).json()['id']
    assert client.get(f'/api/books/{automatic}').json()['volume'] == '1'


def test_legacy_default_generation_is_derived_from_parent_relation(client):
    account(client)
    bid = book(client)
    parent = person(client, bid, '부모')
    child = person(client, bid, '자녀')
    with m.engine.begin() as c:
        c.execute(m.relations.insert().values(source_id=parent, target_id=child, kind='parent'))
    people = {p['korean_name']: p['generation'] for p in client.get(f'/api/books/{bid}').json()['persons']}
    assert people == {'부모': 1, '자녀': 2}


def test_relations_cycles_duplicates_cross_book_and_cascade(client):
    account(client)
    bid = book(client)
    a, b, c = [person(client, bid, name) for name in ['조상', '부모', '자녀']]
    def edge(s, t, kind='parent'):
        return client.post('/api/relations', json={'source_id': s, 'target_id': t, 'kind': kind})
    assert edge(a, b).status_code == 201
    assert edge(b, c).status_code == 201
    generations = {p['korean_name']: p['generation'] for p in client.get(f'/api/books/{bid}').json()['persons']}
    assert generations == {'조상': 1, '부모': 2, '자녀': 3}
    assert edge(c, a).status_code == 400
    assert edge(a, a).status_code == 400
    assert edge(a, b).status_code == 409
    assert edge(a, person(client, book(client))).status_code == 400
    spouse = edge(a, b, 'spouse')
    assert spouse.status_code == 201
    assert edge(b, a, 'spouse').status_code == 409
    assert client.delete('/api/relations/' + str(spouse.json()['id'])).status_code == 200
    assert client.delete(f'/api/persons/{b}').status_code == 200
    assert client.get(f'/api/books/{bid}').json()['relations'] == []


def test_ownership_and_uploads(client):
    first = account(client)
    bid = book(client)
    pid = person(client, bid)
    assert client.post(f'/api/persons/{pid}/files', files={'file': ('bad.html', b'<script>', 'text/html')}).status_code == 400
    assert client.post(f'/api/persons/{pid}/files', files={'file': ('fake.png', b'bad', 'image/png')}).status_code == 400
    assert client.post(f'/api/persons/{pid}/files', files={'file': ('large.pdf', b'%PDF-' + b'x' * (5 * 1024 * 1024), 'application/pdf')}).status_code == 413
    data = b'%PDF-1.4\nSample test-only document\n'
    uploaded = client.post(f'/api/persons/{pid}/files', files={'file': ('sample.pdf', data, 'application/pdf')})
    assert uploaded.status_code == 201
    fid = uploaded.json()['id']
    assert client.get(f'/api/files/{fid}').content == data
    account(client)
    assert client.get(f'/api/books/{bid}').status_code == 404
    assert client.get(f'/api/files/{fid}').status_code == 404
    assert client.delete(f'/api/persons/{pid}').status_code == 404
    assert client.put(f'/api/persons/{pid}', json={'korean_name': '침범'}).status_code == 404
    assert client.get('/api/books').json() == []
    client.post('/api/login', json=first)
    client.delete(f'/api/persons/{pid}')
    assert list(m.UPLOADS.iterdir()) == []
    assert client.get(f'/api/files/{fid}').status_code == 404


def test_static_frontend_and_validation(client):
    assert client.get('/').status_code == 200
    assert '우리의 족보' in client.get('/').text
    assert client.get('/style.css').status_code == 200
    assert client.get('/ux.css').status_code == 200
    assert client.get('/hanjaeum.json').status_code == 200
    assert client.post('/api/register', json={'email': 'invalid', 'password': 'short'}).status_code == 422
    account(client)
    assert client.post('/api/books', json={'title': '   '}).status_code == 422
    bid = book(client)
    assert client.post(f'/api/books/{bid}/persons', json={'korean_name': '예제', 'generation': 0}).status_code == 422


def test_password_is_hashed_and_session_expires(client):
    cred = account(client)
    with m.engine.begin() as c:
        user = c.execute(select(m.users).where(m.users.c.email == cred['email'])).mappings().one()
        assert cred['password'] not in user['password_hash']
        c.execute(m.sessions.update().where(m.sessions.c.user_id == user['id']).values(expires=0))
    assert client.get('/api/me').status_code == 401
