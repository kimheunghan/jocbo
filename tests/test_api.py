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
        'branch_name': '외오산파', 'volume': '9', 'founder': '영헌공'
    })
    assert created.status_code == 201
    bid = created.json()['id']
    saved = client.get(f'/api/books/{bid}').json()
    assert (saved['bon_gwan'], saved['branch_name'], saved['volume']) == ('청도', '외오산파', '9')
    assert saved['founder'] == '영헌공'
    updated = {key: saved[key] for key in ['title', 'clan_name', 'bon_gwan', 'branch_name', 'volume', 'founder', 'description']}
    updated['volume'] = '10'
    assert client.put(f'/api/books/{bid}', json=updated).status_code == 200
    assert client.get(f'/api/books/{bid}').json()['volume'] == '10'
    # The page of the printed book and whose line it traces, beside the founder.
    updated.update(page='617', lineage='芝淑')
    assert client.put(f'/api/books/{bid}', json=updated).status_code == 200
    again = client.get(f'/api/books/{bid}').json()
    assert (again['page'], again['lineage']) == ('617', '芝淑')
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


def test_dates_must_be_real_and_past(client):
    account(client)
    bid = book(client)

    def make(value):
        return client.post(f'/api/books/{bid}/persons',
                           json={'korean_name': '아무개', 'generation': 1, 'birth_date': value})

    # A month past 12, a day past the end of its month, and 29 February in a
    # year that has 28 are each not a date at all.
    for value in ['1956-43-27', '1956-02-31', '1957-02-29', '1956-04-31']:
        assert make(value).status_code == 422, value

    # Nobody was born or died on a day that has not come yet.
    for value in ['8900-08-31', '3000-01-01']:
        answer = make(value)
        assert answer.status_code == 422, value
        assert '아직 오지 않은 날' in answer.text

    # A leap day in a leap year, and any ordinary past date, are fine.
    for value in ['1956-02-29', '1956-07-27']:
        assert make(value).status_code == 201, value


def test_a_page_is_taken_whole_and_a_clearer_reading_only_fills_blanks(client):
    account(client)
    bid = book(client)

    # A page goes in together or not at all: the bad line takes the good one with it.
    spoiled = client.post(f'/api/books/{bid}/persons/bulk', json={'people': [
        {'korean_name': '멀쩡한 줄', 'generation': 27},
        {'korean_name': '망가진 줄', 'generation': 27, 'birth_date': '1956-43-27'},
    ]})
    assert spoiled.status_code == 422
    assert client.get(f'/api/books/{bid}').json()['persons'] == []

    made = client.post(f'/api/books/{bid}/persons/bulk', json={'people': [
        {'korean_name': '갑', 'hanja_name': '甲', 'generation': 27},
        {'korean_name': '을', 'generation': 28, 'gender': '여'},
    ]})
    assert made.status_code == 201
    assert len(made.json()['added']) == 2

    # Someone recorded with nothing known but a name.
    blank = client.post(f'/api/books/{bid}/persons',
                        json={'korean_name': '병', 'generation': 27}).json()['id']

    # A clearer reading fills what was blank, and leaves 세대 where it was.
    read = client.post(f'/api/books/{bid}/persons/bulk', json={'people': [
        {'id': blank, 'korean_name': '병', 'hanja_name': '丙', 'bon_gwan': '淸道',
         'generation': 99, 'gender': '남', 'note': '父 東國'},
    ]})
    assert read.status_code == 201
    assert set(read.json()['filled'][0]['fields']) == {'hanja_name', 'bon_gwan', 'gender', 'note'}
    person = next(p for p in client.get(f'/api/books/{bid}').json()['persons'] if p['id'] == blank)
    assert (person['hanja_name'], person['bon_gwan'], person['gender']) == ('丙', '淸道', '남')
    assert person['generation'] == 27

    # A second reading may not write over what is now on record.
    again = client.post(f'/api/books/{bid}/persons/bulk', json={'people': [
        {'id': blank, 'korean_name': '병', 'hanja_name': '偉', 'generation': 27},
    ]})
    assert again.status_code == 201
    assert again.json()['filled'][0]['fields'] == []
    person = next(p for p in client.get(f'/api/books/{bid}').json()['persons'] if p['id'] == blank)
    assert person['hanja_name'] == '丙'

    # And it may not reach into someone else's book.
    other = client.post('/api/books', json={'title': '남의 족보'}).json()['id']
    assert client.post(f'/api/books/{other}/persons/bulk', json={'people': [
        {'id': blank, 'korean_name': '병', 'generation': 27},
    ]}).status_code == 404


def test_a_scan_belongs_to_the_book_and_is_served_as_a_picture(client):
    account(client)
    bid = book(client)
    png = (b'\x89PNG\r\n\x1a\n' + b'\x00' * 64, 'image/png')

    made = client.post(f'/api/books/{bid}/scans',
                       files={'file': ('618쪽.png', png[0], png[1])})
    assert made.status_code == 201
    sid = made.json()['id']
    assert [s['id'] for s in client.get(f'/api/books/{bid}').json()['scans']] == [sid]

    # A picture is handed back as one, so it can be shown rather than downloaded.
    shown = client.get(f'/api/scans/{sid}')
    assert shown.status_code == 200
    assert shown.headers['content-type'] == 'image/png'

    # Another account cannot reach it.
    client.post('/api/logout')
    account(client)
    assert client.get(f'/api/scans/{sid}').status_code == 404

    assert client.delete(f'/api/scans/{sid}').status_code == 404


def test_a_date_is_kept_as_far_as_it_is_known(client):
    account(client)
    bid = book(client)

    def make(birth, death=''):
        return client.post(f'/api/books/{bid}/persons',
                           json={'korean_name': '아무개', 'generation': 1, 'birth_date': birth, 'death_date': death})

    # The year alone, the year and month, or a day remembered without a year.
    for value in ['1956', '1956-03', '--09-19', '--02-29']:
        assert make(value).status_code == 201, value
    for value in ['1956-13', '--02-30', '56', '1956-3', '--9-19']:
        assert make(value).status_code == 422, value
    # Only as far as both are known: 1956 and 1956-03-02 do not contradict.
    assert make('1956-03-02', '1956').status_code == 201
    assert make('1956', '1955-12-31').status_code == 422
    assert make('--09-19', '1900').status_code == 201


def test_a_reading_adds_to_a_note_what_it_does_not_say_yet(client):
    account(client)
    bid = book(client)
    pid = client.post(f'/api/books/{bid}/persons', json={
        'korean_name': '김진영', 'hanja_name': '金珍英', 'generation': 31, 'note': '女 智恩(지은)·睿恩(예은)'}).json()['id']
    done = client.post(f'/api/books/{bid}/persons/bulk', json={'people': [{
        'id': pid, 'korean_name': '김진영', 'hanja_name': '金珍英', 'generation': 31,
        'note': '夫 金興漢(김흥한) 安東(안동)人 父 敬鎭(경진) · 女 智恩 · 睿恩'}]}).json()
    assert 'note' in done['filled'][0]['fields']
    note = next(p for p in client.get(f'/api/books/{bid}').json()['persons'] if p['id'] == pid)['note']
    # What was there stays; only what it lacked is added, readings aside.
    assert note == '女 智恩(지은)·睿恩(예은)\n夫 金興漢(김흥한) 安東(안동)人 父 敬鎭(경진)'
    # Read again, nothing is added twice.
    again = client.post(f'/api/books/{bid}/persons/bulk', json={'people': [{
        'id': pid, 'korean_name': '김진영', 'hanja_name': '金珍英', 'generation': 31,
        'note': '夫 金興漢 安東人 父 敬鎭'}]}).json()
    assert again['filled'][0]['fields'] == []


def test_a_reading_does_not_give_a_person_a_second_father(client):
    account(client)
    bid = book(client)
    pid = client.post(f'/api/books/{bid}/persons', json={
        'korean_name': '박순남', 'hanja_name': '朴順南', 'generation': 30, 'note': '父 泰鎬(태호)'}).json()['id']
    client.post(f'/api/books/{bid}/persons/bulk', json={'people': [{
        'id': pid, 'korean_name': '박순남', 'hanja_name': '朴順南', 'generation': 30, 'note': '父 甘泰 · 字 玉汝'}]})
    note = next(p for p in client.get(f'/api/books/{bid}').json()['persons'] if p['id'] == pid)['note']
    assert note.splitlines() == ['父 泰鎬(태호)', '字 玉汝']


def test_a_spouse_takes_the_generation_of_the_one_married(client):
    account(client)
    bid = book(client)
    father = client.post(f'/api/books/{bid}/persons', json={'korean_name': '김정환', 'hanja_name': '金正煥', 'generation': 30}).json()['id']
    son = client.post(f'/api/books/{bid}/persons', json={'korean_name': '김철순', 'hanja_name': '金澈純', 'generation': 1}).json()['id']
    wife = client.post(f'/api/books/{bid}/persons', json={'korean_name': '한명래', 'hanja_name': '韓明來', 'generation': 1}).json()['id']
    assert client.post('/api/relations', json={'source_id': father, 'target_id': son, 'kind': 'parent'}).status_code == 201
    assert client.post('/api/relations', json={'source_id': son, 'target_id': wife, 'kind': 'spouse'}).status_code == 201
    generations = {p['id']: p['generation'] for p in client.get(f'/api/books/{bid}').json()['persons']}
    assert (generations[son], generations[wife]) == (31, 31)
