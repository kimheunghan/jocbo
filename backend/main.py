"""Family book MVP. SQLite for a quick start; PostgreSQL for shared deployments."""
import hashlib
import hmac
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Depends, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict, model_validator
from sqlalchemy import (create_engine, MetaData, Table, Column, Integer, String, Text, func,
                        ForeignKey, UniqueConstraint, CheckConstraint, select, event, delete,
                        inspect, text)
from sqlalchemy.exc import IntegrityError

from backend import license as paid
from backend import share as web_share

ROOT = Path(__file__).resolve().parents[1]
UPLOADS = Path(os.getenv('UPLOAD_DIR', str(ROOT / 'uploads')))
engine = create_engine(os.getenv('DATABASE_URL', 'sqlite:///' + str(ROOT / 'jocbo.db')))
if engine.dialect.name == 'sqlite':
    @event.listens_for(engine, 'connect')
    def foreign_keys(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
meta = MetaData()
# A free account holds up to FREE_PERSONS people across its books; adding past
# that asks for the paid plan. An account from before this ('' plan) has no limit.
FREE_PERSONS = 20
users = Table('users', meta, Column('id', Integer, primary_key=True), Column('email', String(255), nullable=False, unique=True), Column('password_hash', String(255), nullable=False), Column('plan', String(10), nullable=False, server_default='free'), Column('license_key', String(100), nullable=False, server_default=''), Column('license_instance', String(100), nullable=False, server_default=''))
sessions = Table('sessions', meta, Column('token_hash', String(64), primary_key=True), Column('user_id', ForeignKey('users.id', ondelete='CASCADE'), nullable=False), Column('expires', Integer, nullable=False))
books = Table('family_books', meta, Column('id', Integer, primary_key=True), Column('user_id', ForeignKey('users.id', ondelete='CASCADE'), nullable=False), Column('title', String(200), nullable=False), Column('clan_name', String(200), nullable=False), Column('bon_gwan', String(200), nullable=False, server_default=''), Column('branch_name', String(200), nullable=False, server_default=''), Column('volume', String(50), nullable=False, server_default=''), Column('founder', String(200), nullable=False, server_default=''), Column('page', String(50), nullable=False, server_default=''), Column('lineage', String(200), nullable=False, server_default=''), Column('page_breaks', String(200), nullable=False, server_default=''), Column('description', Text, nullable=False))
persons = Table('persons', meta, Column('id', Integer, primary_key=True), Column('book_id', ForeignKey('family_books.id', ondelete='CASCADE'), nullable=False, index=True), Column('korean_name', String(100), nullable=False), Column('hanja_name', String(100), nullable=False), Column('bon_gwan', String(200), nullable=False, server_default=''), Column('generation', Integer, nullable=False), Column('gender', String(10), nullable=False), Column('birth_date', String(10), nullable=False), Column('death_date', String(10), nullable=False), Column('note', Text, nullable=False), CheckConstraint('generation > 0'))
relations = Table('relations', meta, Column('id', Integer, primary_key=True), Column('source_id', ForeignKey('persons.id', ondelete='CASCADE'), nullable=False), Column('target_id', ForeignKey('persons.id', ondelete='CASCADE'), nullable=False), Column('kind', String(20), nullable=False), UniqueConstraint('source_id', 'target_id', 'kind'), CheckConstraint('source_id <> target_id'), CheckConstraint("kind IN ('parent', 'spouse')"))
scans = Table('scans', meta, Column('id', Integer, primary_key=True), Column('book_id', ForeignKey('family_books.id', ondelete='CASCADE'), nullable=False, index=True), Column('name', String(255), nullable=False), Column('storage_key', String(80), nullable=False, unique=True))
files = Table('files', meta, Column('id', Integer, primary_key=True), Column('person_id', ForeignKey('persons.id', ondelete='CASCADE'), nullable=False), Column('name', String(255), nullable=False), Column('storage_key', String(80), nullable=False, unique=True))
# A book shown on the share site: where it went, the key to send to it, and
# what was last sent.
shares = Table('shares', meta, Column('book_id', ForeignKey('family_books.id', ondelete='CASCADE'), primary_key=True), Column('server', String(255), nullable=False), Column('share_id', String(40), nullable=False), Column('token', String(128), nullable=False), Column('synced', String(64), nullable=False, server_default=''), Column('error', Text, nullable=False, server_default=''), Column('synced_at', Integer, nullable=False, server_default='0'))

@asynccontextmanager
async def lifespan(app):
    meta.create_all(engine)
    additions = {
        'family_books': {'bon_gwan': 'VARCHAR(200)', 'branch_name': 'VARCHAR(200)', 'volume': 'VARCHAR(50)', 'founder': 'VARCHAR(200)',
                         'page': 'VARCHAR(50)', 'lineage': 'VARCHAR(200)', 'page_breaks': 'VARCHAR(200)'},
        'persons': {'bon_gwan': 'VARCHAR(200)'},
        # Accounts already here take '' — no limit — since they began before it.
        'users': {'plan': 'VARCHAR(10)', 'license_key': 'VARCHAR(100)', 'license_instance': 'VARCHAR(100)'},
    }
    with engine.begin() as connection:
        for table, columns in additions.items():
            existing = {column['name'] for column in inspect(engine).get_columns(table)}
            for name, column_type in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {column_type} NOT NULL DEFAULT ''"))
    UPLOADS.mkdir(parents=True, exist_ok=True)
    # Shared books go up on their own; anything changed while offline goes now.
    web_share.worker.start()
    web_share.worker.changed()
    yield
    web_share.worker.stop()

app = FastAPI(title='우리의 족보', lifespan=lifespan)

@app.middleware('http')
async def send_changes_up(request: Request, call_next):
    """Any change that went through has the shared books sent up again."""
    response = await call_next(request)
    if request.method != 'GET' and request.url.path.startswith('/api/') and response.status_code < 400:
        web_share.worker.changed()
    return response

class Input(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

class Credentials(Input):
    email: str = Field(min_length=3, max_length=255, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    password: str = Field(min_length=10, max_length=128)

class Book(Input):
    title: str = Field(min_length=1, max_length=200)
    clan_name: str = Field(default='', max_length=200)
    bon_gwan: str = Field(default='', max_length=200)
    branch_name: str = Field(default='', max_length=200)
    volume: str = Field(default='', max_length=50)
    founder: str = Field(default='', max_length=200)
    # The page of the printed book the record begins on, and whose line (系統圖)
    # the book traces: 芝淑.
    page: str = Field(default='', max_length=50)
    lineage: str = Field(default='', max_length=200)
    # Where the printed book jumps to another page as a generation begins:
    # '31세 660쪽' — the sheet that opens with 31世 is page 660.
    page_breaks: str = Field(default='', max_length=200)
    description: str = Field(default='', max_length=5000)

# A book often knows only part of a date: the year alone, the year and month, or
# the month and day a spouse is remembered on with no year at all. Each is kept
# as far as it is known — 1956, 1956-03, 1956-03-02, or --03-02 without a year.
def partial_date(value):
    whole = re.fullmatch(r'(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?', value)
    yearless = re.fullmatch(r'--(\d{2})-(\d{2})', value)
    if whole:
        year, month, day = whole.groups()
    elif yearless:
        # A leap year, so that 29 February stands when the year is not known.
        year, (month, day) = '2000', yearless.groups()
    else:
        return False
    try:
        date(int(year), int(month or 1), int(day or 1))
    except ValueError:
        return False
    return True

class Person(Input):
    korean_name: str = Field(min_length=1, max_length=100)
    hanja_name: str = Field(default='', max_length=100)
    bon_gwan: str = Field(default='', max_length=200)
    generation: int = Field(default=1, ge=1, le=200)
    gender: Literal['미상', '남', '여'] = '미상'
    birth_date: str = ''
    death_date: str = ''
    note: str = Field(default='', max_length=10000)

    @model_validator(mode='after')
    def dates(self):
        # A day of slack, because the browser goes by its own clock and may be a
        # date ahead of this one.
        latest = (date.today() + timedelta(days=1)).isoformat()
        for label, value in (('출생일', self.birth_date), ('사망일', self.death_date)):
            if not value:
                continue
            if not partial_date(value):
                raise ValueError(f'{label}에 없는 날짜가 적혀 있습니다. 월은 1~12, 일은 그 달의 마지막 날까지입니다.')
            if not value.startswith('--') and value > latest[:len(value)]:
                raise ValueError(f'{label}에 아직 오지 않은 날이 적혀 있습니다.')
        # Only as far as both are known: 1956 and 1956-03-02 do not contradict.
        birth, death = self.birth_date, self.death_date
        if birth and death and not birth.startswith('--') and not death.startswith('--'):
            known = min(len(birth), len(death))
            if birth[:known] > death[:known]:
                raise ValueError('사망일은 출생일보다 빠를 수 없습니다.')
        return self

class PersonLine(Person):
    # Set when the line is a clearer reading of someone already in the book
    # rather than a new person.
    id: int | None = None
    # Set when the line shows the record as it is to be kept, corrections and
    # all: it is written as it stands, not only into what was blank.
    replace: bool = False

class PersonBatch(Input):
    people: list[PersonLine] = Field(min_length=1, max_length=200)

class Relation(Input):
    source_id: int
    target_id: int
    kind: Literal['parent', 'spouse']

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + digest

def auth(request: Request):
    token = request.cookies.get('session', '')
    with engine.connect() as c:
        uid = c.execute(select(sessions.c.user_id).where(sessions.c.token_hash == hashlib.sha256(token.encode()).hexdigest(), sessions.c.expires > int(time.time()))).scalar()
    if uid is None:
        raise HTTPException(401, '로그인이 필요합니다.')
    return uid

def own_book(c, book_id, uid):
    row = c.execute(select(books).where(books.c.id == book_id, books.c.user_id == uid)).mappings().first()
    if not row:
        raise HTTPException(404, '족보를 찾을 수 없습니다.')
    return row

def own_person(c, pid, uid):
    row = c.execute(select(persons).where(persons.c.id == pid)).mappings().first()
    if not row:
        raise HTTPException(404, '인물을 찾을 수 없습니다.')
    own_book(c, row['book_id'], uid)
    return row

@app.post('/api/register', status_code=201)
def register(data: Credentials):
    try:
        with engine.begin() as c:
            c.execute(users.insert().values(email=data.email.lower(), password_hash=password_hash(data.password), plan='free'))
    except IntegrityError:
        raise HTTPException(409, '이미 등록된 이메일입니다.')
    return {'message': '가입되었습니다. 로그인해 주세요.'}

@app.post('/api/login')
def login(data: Credentials, response: Response):
    with engine.begin() as c:
        user = c.execute(select(users).where(users.c.email == data.email.lower())).mappings().first()
        if not user or not hmac.compare_digest(user['password_hash'], password_hash(data.password, user['password_hash'].split(':')[0])):
            raise HTTPException(401, '이메일 또는 비밀번호가 올바르지 않습니다.')
        token = secrets.token_urlsafe(32)
        c.execute(delete(sessions).where(sessions.c.expires < int(time.time())))
        c.execute(sessions.insert().values(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user['id'], expires=int(time.time()) + 86400))
    response.set_cookie('session', token, httponly=True, samesite='strict', secure=os.getenv('COOKIE_SECURE') == '1', max_age=86400)
    return {'email': user['email']}

@app.post('/api/logout')
def logout(request: Request, response: Response):
    with engine.begin() as c:
        c.execute(delete(sessions).where(sessions.c.token_hash == hashlib.sha256(request.cookies.get('session', '').encode()).hexdigest()))
    response.delete_cookie('session')
    return {'ok': True}

def people_count(c, uid):
    return c.execute(select(func.count()).select_from(persons.join(books, persons.c.book_id == books.c.id))
                     .where(books.c.user_id == uid)).scalar()

def room_for(c, uid, adding):
    """Refuse, with 402, people beyond what a free account holds."""
    if adding <= 0 or c.execute(select(users.c.plan).where(users.c.id == uid)).scalar() != 'free':
        return
    if people_count(c, uid) + adding > FREE_PERSONS:
        raise HTTPException(402, f'무료 이용은 인물 {FREE_PERSONS}명까지입니다. 더 등록하려면 정식판으로 전환해 주십시오.')

@app.get('/api/me')
def me(uid=Depends(auth)):
    with engine.connect() as c:
        user = c.execute(select(users.c.email, users.c.plan, users.c.license_key).where(users.c.id == uid)).mappings().first()
        return {'email': user['email'], 'plan': user['plan'] or 'paid', 'people': people_count(c, uid),
                'free_people': FREE_PERSONS, 'licensed': bool(user['license_key']),
                'checkout_url': paid.CHECKOUT_URL}

class LicenseKey(Input):
    key: str = Field(min_length=8, max_length=100)

@app.post('/api/license')
def put_in_license(data: LicenseKey, uid=Depends(auth)):
    """Turn the account into the full version with a key bought on the checkout page."""
    import platform
    try:
        instance = paid.activate(data.key, platform.node() or 'PC')
    except paid.LicenseError as error:
        raise HTTPException(400, str(error))
    with engine.begin() as c:
        c.execute(users.update().where(users.c.id == uid)
                  .values(plan='paid', license_key=data.key, license_instance=instance))
    return {'plan': 'paid'}

@app.delete('/api/license')
def take_out_license(uid=Depends(auth)):
    """Free this PC's place under the key, so it can go on another PC."""
    with engine.connect() as c:
        user = c.execute(select(users.c.license_key, users.c.license_instance).where(users.c.id == uid)).mappings().first()
    if not user['license_key']:
        raise HTTPException(400, '이 계정에는 등록된 라이선스 키가 없습니다.')
    try:
        paid.deactivate(user['license_key'], user['license_instance'])
    except paid.LicenseError as error:
        raise HTTPException(400, str(error))
    with engine.begin() as c:
        c.execute(users.update().where(users.c.id == uid).values(plan='free', license_key='', license_instance=''))
    return {'plan': 'free'}

@app.get('/api/books')
def list_books(uid=Depends(auth)):
    with engine.connect() as c:
        return list(c.execute(select(books).where(books.c.user_id == uid).order_by(books.c.id)).mappings())

@app.post('/api/books', status_code=201)
def create_book(data: Book, uid=Depends(auth)):
    with engine.begin() as c:
        values = data.model_dump()
        values['volume'] = values['volume'] or '1'
        return {'id': c.execute(books.insert().values(user_id=uid, **values)).inserted_primary_key[0]}

@app.post('/api/books/sample', status_code=201)
def add_sample_book(uid=Depends(auth)):
    """A fictional 金海金氏 book of twenty people, every field in use."""
    from backend.sample import create_sample, PEOPLE
    with engine.begin() as c:
        room_for(c, uid, len(PEOPLE))
        return {'id': create_sample(c, uid, books, persons, relations)}

@app.put('/api/books/{bid}')
def edit_book(bid: int, data: Book, uid=Depends(auth)):
    with engine.begin() as c:
        own_book(c, bid, uid)
        c.execute(books.update().where(books.c.id == bid).values(**data.model_dump()))
    return {'ok': True}

@app.get('/api/books/{bid}')
def get_book(bid: int, uid=Depends(auth)):
    with engine.connect() as c:
        return book_detail(c, bid, uid)

def book_detail(c, bid, uid):
    """The book with everyone in it, as the page and the share site show it."""
    book = dict(own_book(c, bid, uid))
    book['persons'] = [dict(row) for row in c.execute(select(persons).where(persons.c.book_id == bid).order_by(persons.c.generation, persons.c.id)).mappings()]
    ids = [p['id'] for p in book['persons']]
    book['relations'] = list(c.execute(select(relations).where(relations.c.source_id.in_(ids))).mappings())
    book['files'] = list(c.execute(select(files.c.id, files.c.person_id, files.c.name).where(files.c.person_id.in_(ids))).mappings())
    book['scans'] = list(c.execute(select(scans.c.id, scans.c.name).where(scans.c.book_id == bid).order_by(scans.c.id)).mappings())
    # Legacy records may still have the default generation (1).  Derive the
    # displayed generation from parent-child relationships so every view is
    # consistent even before the record is edited again.
    generations = {p['id']: p['generation'] for p in book['persons']}
    parent_relations = [r for r in book['relations'] if r['kind'] == 'parent']
    # Husband and wife stand in one generation, so someone who married in,
    # entered at the default 1, takes the generation of the one married.
    spouse_relations = [r for r in book['relations'] if r['kind'] == 'spouse']
    for _ in range(len(book['persons'])):
        changed = False
        for relation in parent_relations:
            expected = generations[relation['source_id']] + 1
            if generations[relation['target_id']] < expected:
                generations[relation['target_id']] = expected
                changed = True
        for relation in spouse_relations:
            one, other = relation['source_id'], relation['target_id']
            if one in generations and other in generations and generations[one] != generations[other]:
                generations[one] = generations[other] = max(generations[one], generations[other])
                changed = True
        if not changed:
            break
    for person in book['persons']:
        person['generation'] = generations[person['id']]
    return book

def share_row(c, bid):
    return c.execute(select(shares).where(shares.c.book_id == bid)).mappings().first()

def share_status(row):
    if not row:
        return {'shared': False}
    return {'shared': True, 'link': web_share.link(row), 'synced_at': row['synced_at'],
            'error': row['error'], 'pending': not row['synced']}

@app.get('/api/books/{bid}/share')
def get_share(bid: int, uid=Depends(auth)):
    with engine.connect() as c:
        own_book(c, bid, uid)
        return share_status(share_row(c, bid))

@app.post('/api/books/{bid}/share', status_code=201)
def start_share(bid: int, uid=Depends(auth)):
    with engine.begin() as c:
        own_book(c, bid, uid)
        if share_row(c, bid):
            raise HTTPException(409, '이미 공유 중인 족보입니다.')
        try:
            made = web_share.create()
        except web_share.ShareError as error:
            raise HTTPException(502, str(error))
        c.execute(shares.insert().values(book_id=bid, server=web_share.SERVER, share_id=made['id'], token=made['token']))
        state = share_status(share_row(c, bid))
    # The link is given now; the book and its photos go up behind it, and the
    # page shows 올리는 중 until they are there.
    web_share.worker.changed(now=True)
    return state

@app.delete('/api/books/{bid}/share')
def stop_share(bid: int, uid=Depends(auth)):
    with engine.connect() as c:
        own_book(c, bid, uid)
        row = share_row(c, bid)
    if row:
        # The copy on the site goes first; a share left there would stay open.
        try:
            web_share.remove(row)
        except web_share.ShareError as error:
            raise HTTPException(502, f'공유를 끝내지 못했습니다. {error}')
        with engine.begin() as c:
            c.execute(delete(shares).where(shares.c.book_id == bid))
    return {'shared': False}

@app.post('/api/books/{bid}/persons', status_code=201)
def add_person(bid: int, data: Person, uid=Depends(auth)):
    with engine.begin() as c:
        own_book(c, bid, uid)
        room_for(c, uid, 1)
        return {'id': c.execute(persons.insert().values(book_id=bid, **data.model_dump())).inserted_primary_key[0]}

# What counts as nothing on record yet, per column. A clearer reading of a page
# may fill these in; it may never write over something already there.
BLANK = {'hanja_name': '', 'bon_gwan': '', 'birth_date': '', 'death_date': '', 'note': '', 'gender': '미상'}

# The words a note item begins with, of which a person has one: a second 父 is a
# misreading of the first, not news.
# A grave is one place too: the one on record, perhaps set right by hand, is
# kept over another reading of it.
NOTE_LABELS = {'父', '夫', '字', '初名', '一名', '號', '諱', '墓', '墓는'}

def merged_note(old, new):
    """The note on record with the items of a new reading it lacks added on.

    Items are the parts between · or on lines of their own. An item counts as
    said already when, readings in brackets and spacing aside, the old note
    holds it: 父 敬鎭 is in 父 敬鎭(경진).
    """
    import re
    bare = lambda text: re.sub(r'[\s·]|[(（][^)）]*[)）]', '', text)
    held = bare(old)
    # A reading's 父 or 字 where the note already names one is another reading
    # of the same thing, and more likely the misread one: it is not added.
    # 墓는 and 墓 are the one label.
    head = lambda item: item.split()[0].removesuffix('는') if item.split() else ''
    said = {head(item.strip()) for item in re.split(r'\s*·\s*|\n', old)}
    extra = [item.strip() for item in re.split(r'\s*·\s*|\n', new)
             if item.strip() and bare(item) and bare(item) not in held
             and not (head(item.strip()) in NOTE_LABELS and head(item.strip()) in said)]
    return old + ''.join('\n' + item for item in extra) if extra else old

@app.post('/api/books/{bid}/persons/bulk', status_code=201)
def add_people(bid: int, data: PersonBatch, uid=Depends(auth)):
    # A page is read as a whole. One bad line must not leave half a page filed,
    # so the lot goes in together or not at all.
    added, filled = [], []
    with engine.begin() as c:
        own_book(c, bid, uid)
        room_for(c, uid, sum(line.id is None for line in data.people))
        for line in data.people:
            values = line.model_dump(exclude={'id', 'replace'})
            if line.id is None:
                added.append(c.execute(persons.insert().values(book_id=bid, **values)).inserted_primary_key[0])
                continue
            row = c.execute(select(persons).where(persons.c.id == line.id, persons.c.book_id == bid)).mappings().first()
            if not row:
                raise HTTPException(404, '고쳐 쓸 인물을 이 족보에서 찾을 수 없습니다.')
            if line.replace:
                fill = {name: value for name, value in values.items() if value != row[name]}
                if fill:
                    c.execute(persons.update().where(persons.c.id == line.id).values(**fill))
                filled.append({'id': line.id, 'fields': sorted(fill)})
                continue
            # 세대 and 한글명 are what the line was matched on, so a reading never
            # moves them; everything else is filled only where nothing was known.
            fill = {name: values[name] for name, blank in BLANK.items()
                    if values.get(name) and values[name] != blank and row[name] == blank}
            # A note already on record keeps all it says, and gains whatever the
            # reading found that it does not say yet.
            if values.get('note') and row['note'] and 'note' not in fill:
                merged = merged_note(row['note'], values['note'])
                if merged != row['note']:
                    fill['note'] = merged
            if fill:
                c.execute(persons.update().where(persons.c.id == line.id).values(**fill))
            filled.append({'id': line.id, 'fields': sorted(fill)})
    return {'added': added, 'filled': filled}

@app.put('/api/persons/{pid}')
def edit_person(pid: int, data: Person, uid=Depends(auth)):
    with engine.begin() as c:
        own_person(c, pid, uid)
        c.execute(persons.update().where(persons.c.id == pid).values(**data.model_dump()))
    return {'ok': True}

@app.delete('/api/persons/{pid}')
def remove_person(pid: int, uid=Depends(auth)):
    with engine.begin() as c:
        own_person(c, pid, uid)
        keys = list(c.execute(select(files.c.storage_key).where(files.c.person_id == pid)).scalars())
        c.execute(delete(persons).where(persons.c.id == pid))
    for key in keys:
        (UPLOADS / key).unlink(missing_ok=True)
    return {'ok': True}

@app.post('/api/relations', status_code=201)
def add_relation(data: Relation, uid=Depends(auth)):
    with engine.begin() as c:
        a, b = own_person(c, data.source_id, uid), own_person(c, data.target_id, uid)
        if a['book_id'] != b['book_id'] or a['id'] == b['id']:
            raise HTTPException(400, '같은 족보의 서로 다른 인물을 선택하세요.')
        # Serialize relation writes per book on PostgreSQL to prevent concurrent cycles.
        c.execute(select(books.c.id).where(books.c.id == a['book_id']).with_for_update())
        if data.kind == 'parent':
            # A child stands below the parent. One entered at the default 1 has
            # no generation of its own yet and takes it from the parent; one
            # already at the parent's generation or above is someone else
            # (金讚煥 30세 is no father of 金起煥 30세).
            if b['generation'] > 1 and b['generation'] <= a['generation']:
                raise HTTPException(400, f"세대가 맞지 않습니다: 부모 {a['generation']}세대, 자녀 {b['generation']}세대")
            edges = list(c.execute(select(relations).where(relations.c.kind == 'parent')).mappings())
            pending, seen = [b['id']], set()
            while pending:
                node = pending.pop()
                if node == a['id']:
                    raise HTTPException(400, '부모-자녀 관계가 순환합니다.')
                if node not in seen:
                    seen.add(node)
                    pending.extend(e['target_id'] for e in edges if e['source_id'] == node)
            c.execute(persons.update().where(persons.c.id == b['id']).values(generation=max(b['generation'], a['generation'] + 1)))
        else:
            data.source_id, data.target_id = sorted([data.source_id, data.target_id])
        try:
            rid = c.execute(relations.insert().values(**data.model_dump())).inserted_primary_key[0]
        except IntegrityError:
            raise HTTPException(409, '이미 등록된 관계입니다.')
    return {'id': rid}

@app.delete('/api/relations/{rid}')
def remove_relation(rid: int, uid=Depends(auth)):
    with engine.begin() as c:
        row = c.execute(select(relations).where(relations.c.id == rid)).mappings().first()
        if not row:
            raise HTTPException(404, '관계가 없습니다.')
        own_person(c, row['source_id'], uid)
        c.execute(delete(relations).where(relations.c.id == rid))
    return {'ok': True}

SIGNATURES = {'.pdf': b'%PDF-', '.png': b'\x89PNG\r\n\x1a\n', '.jpg': b'\xff\xd8\xff', '.jpeg': b'\xff\xd8\xff'}
# A scan of a whole page is larger than a portrait, so it is given more room.
async def stored_upload(file: UploadFile, limit):
    name = Path((file.filename or 'file').replace('\\', '/')).name[:255]
    suffix = Path(name).suffix.lower()
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f'파일은 {limit // (1024 * 1024)}MB 이하만 가능합니다.')
    if suffix not in SIGNATURES or not data.startswith(SIGNATURES[suffix]):
        raise HTTPException(400, 'PNG, JPG, PDF 파일만 업로드할 수 있습니다.')
    key = secrets.token_hex(24) + suffix
    (UPLOADS / key).write_bytes(data)
    return name, key

# A PNG or a JPG is handed back as the picture it was checked to be, so it can be
# shown rather than downloaded; a PDF stays an attachment, since a PDF can carry
# more than it shows.
def served(row, key_column='storage_key'):
    suffix = Path(row[key_column]).suffix.lower()
    kinds = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg'}
    if suffix in kinds:
        return FileResponse(UPLOADS / row[key_column], media_type=kinds[suffix],
                            headers={'X-Content-Type-Options': 'nosniff'})
    return FileResponse(UPLOADS / row[key_column], filename=row['name'],
                        media_type='application/octet-stream',
                        headers={'X-Content-Type-Options': 'nosniff'})

@app.post('/api/books/{bid}/scans', status_code=201)
async def upload_scan(bid: int, file: UploadFile, uid=Depends(auth)):
    with engine.connect() as c:
        own_book(c, bid, uid)
    name, key = await stored_upload(file, 20 * 1024 * 1024)
    try:
        with engine.begin() as c:
            own_book(c, bid, uid)
            sid = c.execute(scans.insert().values(book_id=bid, name=name, storage_key=key)).inserted_primary_key[0]
    except Exception:
        (UPLOADS / key).unlink(missing_ok=True)
        raise
    return {'id': sid, 'name': name}

class ClaudeKey(Input):
    key: str = Field(default='', max_length=300)

@app.get('/api/claude')
def claude_status(uid=Depends(auth)):
    from backend import claude_read
    return {'available': claude_read.available(), 'configured': bool(claude_read.stored_key())}

@app.put('/api/claude/key')
def claude_key(data: ClaudeKey, uid=Depends(auth)):
    # The key is tried against Anthropic before it is kept, so a mistyped one
    # is caught here rather than on the first reading.
    from backend import claude_read
    if not claude_read.available():
        raise HTTPException(503, 'anthropic 꾸러미가 설치되어 있지 않습니다. start.bat을 다시 실행해 주세요.')
    if data.key:
        import anthropic
        try:
            claude_read.check_key(data.key)
        except anthropic.AuthenticationError:
            raise HTTPException(400, 'API 키가 올바르지 않습니다.')
        except anthropic.APIConnectionError:
            raise HTTPException(502, 'Anthropic에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.')
    claude_read.save_key(data.key)
    return {'configured': bool(data.key)}

def claude_reading(path, book):
    import anthropic
    from backend import claude_read
    if not claude_read.available():
        raise HTTPException(503, 'anthropic 꾸러미가 설치되어 있지 않습니다. start.bat을 다시 실행해 주세요.')
    try:
        return claude_read.read(path, dict(book))
    except anthropic.AuthenticationError:
        raise HTTPException(401, 'Claude API 키가 없거나 올바르지 않습니다. 키를 다시 넣어 주세요.')
    except anthropic.PermissionDeniedError:
        raise HTTPException(403, '이 API 키로는 Claude를 쓸 수 없습니다.')
    except anthropic.RateLimitError:
        raise HTTPException(429, 'Claude 사용량 한도에 걸렸습니다. 잠시 뒤 다시 해 주십시오.')
    except anthropic.APIConnectionError:
        raise HTTPException(502, 'Anthropic에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.')
    except anthropic.APIStatusError as problem:
        raise HTTPException(502, f'Claude 판독 실패 ({problem.status_code}): {problem.message}')

@app.post('/api/scans/{sid}/read')
def read_page(sid: int, reader: str = Query('', alias='engine'), uid=Depends(auth)):
    # The reading is only ever a proposal: it is handed back for correction and
    # nothing is written to the record here.
    from backend import readscan
    if reader != 'claude' and not readscan.available():
        raise HTTPException(503, '판독기가 설치되어 있지 않습니다. requirements.txt의 rapidocr-onnxruntime을 설치해 주세요.')
    with engine.connect() as c:
        row = c.execute(select(scans).where(scans.c.id == sid)).mappings().first()
        if not row:
            raise HTTPException(404, '스캔이 없습니다.')
        book = own_book(c, row['book_id'], uid)
    if reader == 'claude':
        return claude_reading(str(UPLOADS / row['storage_key']), book)
    # The page leaves the family name off a child of the line, so it is taken
    # from the book itself.
    surname = (book['clan_name'] or '').replace('氏', '').strip()[:1]
    try:
        return readscan.read(str(UPLOADS / row['storage_key']), surname=surname)
    except Exception as problem:
        raise HTTPException(500, f'판독하지 못했습니다: {problem}')

@app.get('/api/scans/{sid}')
def read_scan(sid: int, uid=Depends(auth)):
    with engine.connect() as c:
        row = c.execute(select(scans).where(scans.c.id == sid)).mappings().first()
        if not row:
            raise HTTPException(404, '스캔이 없습니다.')
        own_book(c, row['book_id'], uid)
    return served(row)

@app.delete('/api/scans/{sid}')
def remove_scan(sid: int, uid=Depends(auth)):
    with engine.begin() as c:
        row = c.execute(select(scans).where(scans.c.id == sid)).mappings().first()
        if not row:
            raise HTTPException(404, '스캔이 없습니다.')
        own_book(c, row['book_id'], uid)
        c.execute(delete(scans).where(scans.c.id == sid))
    (UPLOADS / row['storage_key']).unlink(missing_ok=True)
    return {'ok': True}

@app.post('/api/persons/{pid}/files', status_code=201)
async def upload(pid: int, file: UploadFile, uid=Depends(auth)):
    with engine.connect() as c:
        own_person(c, pid, uid)
    name, key = await stored_upload(file, 5 * 1024 * 1024)
    try:
        with engine.begin() as c:
            own_person(c, pid, uid)
            fid = c.execute(files.insert().values(person_id=pid, name=name, storage_key=key)).inserted_primary_key[0]
    except Exception:
        (UPLOADS / key).unlink(missing_ok=True)
        raise
    return {'id': fid}

@app.get('/api/files/{fid}')
def download(fid: int, size: int = Query(0, ge=0, le=1200), uid=Depends(auth)):
    with engine.connect() as c:
        row = c.execute(select(files).where(files.c.id == fid)).mappings().first()
        if not row:
            raise HTTPException(404, '파일이 없습니다.')
        own_person(c, row['person_id'], uid)
    if size:
        small = thumbnail(row['storage_key'], size)
        if small:
            return FileResponse(small, media_type='image/jpeg',
                                headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'private, max-age=86400'})
    return served(row)


def thumbnail(key, size):
    """A photo made small for a card, kept beside the uploads once it is made.

    A card shows a photo a few dozen pixels wide; sent whole, a phone's 4MB
    picture has the list, the tree and above all the print preview decode it
    at full size for every card it appears on. None when it cannot be made
    (not a picture, or Pillow missing), and the original is sent instead.
    """
    source = UPLOADS / key
    if source.suffix.lower() not in ('.png', '.jpg', '.jpeg') or not source.exists():
        return None
    small = UPLOADS / 'thumbs' / f'{source.stem}-{size}.jpg'
    if small.exists() and small.stat().st_mtime >= source.stat().st_mtime:
        return small
    try:
        from PIL import Image, ImageOps
        with Image.open(source) as picture:
            picture = ImageOps.exif_transpose(picture).convert('RGB')
            picture.thumbnail((size, size))
            small.parent.mkdir(parents=True, exist_ok=True)
            picture.save(small, 'JPEG', quality=85)
    except Exception:
        return None
    return small

@app.delete('/api/files/{fid}')
def remove_file(fid: int, uid=Depends(auth)):
    with engine.begin() as c:
        row = c.execute(select(files).where(files.c.id == fid)).mappings().first()
        if not row:
            raise HTTPException(404, '파일이 없습니다.')
        own_person(c, row['person_id'], uid)
        c.execute(delete(files).where(files.c.id == fid))
    (UPLOADS / row['storage_key']).unlink(missing_ok=True)
    return {'ok': True}

class FreshStatic(StaticFiles):
    """Ask the browser to revalidate every file.

    Without a Cache-Control header the browser is free to guess how long a file
    stays good, and it guesses long enough that an edited page keeps loading the
    old script until someone forces a reload.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers['Cache-Control'] = 'no-cache'
        return response


@app.get('/', include_in_schema=False)
@app.get('/index.html', include_in_schema=False)
def front_page():
    """The page, naming its script and styles by when they last changed.

    A browser that keeps an old app.js in its cache goes on running it after an
    update, however often the page is reloaded; a new name is a file it has
    never seen, so it fetches it.
    """
    front = ROOT / 'frontend'
    page = (front / 'index.html').read_text(encoding='utf-8')
    for name in ('app.js', 'style.css', 'ux.css', 'theme.css'):
        stamp = int((front / name).stat().st_mtime)
        page = page.replace(f'"{name}"', f'"{name}?v={stamp}"')
    return Response(page, media_type='text/html; charset=utf-8', headers={'Cache-Control': 'no-cache'})

app.mount('/', FreshStatic(directory=ROOT / 'frontend', html=True), name='frontend')
