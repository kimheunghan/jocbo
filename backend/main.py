"""Family book MVP. SQLite for a quick start; PostgreSQL for shared deployments."""
import hashlib
import hmac
import os
import secrets
import time
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Depends, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict, model_validator
from sqlalchemy import (create_engine, MetaData, Table, Column, Integer, String, Text,
                        ForeignKey, UniqueConstraint, CheckConstraint, select, event, delete,
                        inspect, text)
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[1]
UPLOADS = Path(os.getenv('UPLOAD_DIR', str(ROOT / 'uploads')))
engine = create_engine(os.getenv('DATABASE_URL', 'sqlite:///' + str(ROOT / 'jocbo.db')))
if engine.dialect.name == 'sqlite':
    @event.listens_for(engine, 'connect')
    def foreign_keys(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
meta = MetaData()
users = Table('users', meta, Column('id', Integer, primary_key=True), Column('email', String(255), nullable=False, unique=True), Column('password_hash', String(255), nullable=False))
sessions = Table('sessions', meta, Column('token_hash', String(64), primary_key=True), Column('user_id', ForeignKey('users.id', ondelete='CASCADE'), nullable=False), Column('expires', Integer, nullable=False))
books = Table('family_books', meta, Column('id', Integer, primary_key=True), Column('user_id', ForeignKey('users.id', ondelete='CASCADE'), nullable=False), Column('title', String(200), nullable=False), Column('clan_name', String(200), nullable=False), Column('bon_gwan', String(200), nullable=False, server_default=''), Column('branch_name', String(200), nullable=False, server_default=''), Column('volume', String(50), nullable=False, server_default=''), Column('description', Text, nullable=False))
persons = Table('persons', meta, Column('id', Integer, primary_key=True), Column('book_id', ForeignKey('family_books.id', ondelete='CASCADE'), nullable=False, index=True), Column('korean_name', String(100), nullable=False), Column('hanja_name', String(100), nullable=False), Column('bon_gwan', String(200), nullable=False, server_default=''), Column('generation', Integer, nullable=False), Column('gender', String(10), nullable=False), Column('birth_date', String(10), nullable=False), Column('death_date', String(10), nullable=False), Column('note', Text, nullable=False), CheckConstraint('generation > 0'))
relations = Table('relations', meta, Column('id', Integer, primary_key=True), Column('source_id', ForeignKey('persons.id', ondelete='CASCADE'), nullable=False), Column('target_id', ForeignKey('persons.id', ondelete='CASCADE'), nullable=False), Column('kind', String(20), nullable=False), UniqueConstraint('source_id', 'target_id', 'kind'), CheckConstraint('source_id <> target_id'), CheckConstraint("kind IN ('parent', 'spouse')"))
files = Table('files', meta, Column('id', Integer, primary_key=True), Column('person_id', ForeignKey('persons.id', ondelete='CASCADE'), nullable=False), Column('name', String(255), nullable=False), Column('storage_key', String(80), nullable=False, unique=True))

@asynccontextmanager
async def lifespan(app):
    meta.create_all(engine)
    additions = {
        'family_books': {'bon_gwan': 'VARCHAR(200)', 'branch_name': 'VARCHAR(200)', 'volume': 'VARCHAR(50)'},
        'persons': {'bon_gwan': 'VARCHAR(200)'},
    }
    with engine.begin() as connection:
        for table, columns in additions.items():
            existing = {column['name'] for column in inspect(engine).get_columns(table)}
            for name, column_type in columns.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {column_type} NOT NULL DEFAULT ''"))
    UPLOADS.mkdir(parents=True, exist_ok=True)
    yield

app = FastAPI(title='우리의 족보', lifespan=lifespan)

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
    description: str = Field(default='', max_length=5000)

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
        for value in [self.birth_date, self.death_date]:
            if value and date.fromisoformat(value).isoformat() != value:
                raise ValueError('날짜는 YYYY-MM-DD 형식입니다.')
        if self.birth_date and self.death_date and self.birth_date > self.death_date:
            raise ValueError('사망일은 출생일보다 빠를 수 없습니다.')
        return self

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
            c.execute(users.insert().values(email=data.email.lower(), password_hash=password_hash(data.password)))
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

@app.get('/api/me')
def me(uid=Depends(auth)):
    with engine.connect() as c:
        return {'email': c.execute(select(users.c.email).where(users.c.id == uid)).scalar()}

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

@app.put('/api/books/{bid}')
def edit_book(bid: int, data: Book, uid=Depends(auth)):
    with engine.begin() as c:
        own_book(c, bid, uid)
        c.execute(books.update().where(books.c.id == bid).values(**data.model_dump()))
    return {'ok': True}

@app.get('/api/books/{bid}')
def get_book(bid: int, uid=Depends(auth)):
    with engine.connect() as c:
        book = dict(own_book(c, bid, uid))
        book['persons'] = [dict(row) for row in c.execute(select(persons).where(persons.c.book_id == bid).order_by(persons.c.generation, persons.c.id)).mappings()]
        ids = [p['id'] for p in book['persons']]
        book['relations'] = list(c.execute(select(relations).where(relations.c.source_id.in_(ids))).mappings())
        book['files'] = list(c.execute(select(files.c.id, files.c.person_id, files.c.name).where(files.c.person_id.in_(ids))).mappings())
        # Legacy records may still have the default generation (1).  Derive the
        # displayed generation from parent-child relationships so every view is
        # consistent even before the record is edited again.
        generations = {p['id']: p['generation'] for p in book['persons']}
        parent_relations = [r for r in book['relations'] if r['kind'] == 'parent']
        for _ in range(len(book['persons'])):
            changed = False
            for relation in parent_relations:
                expected = generations[relation['source_id']] + 1
                if generations[relation['target_id']] < expected:
                    generations[relation['target_id']] = expected
                    changed = True
            if not changed:
                break
        for person in book['persons']:
            person['generation'] = generations[person['id']]
        return book

@app.post('/api/books/{bid}/persons', status_code=201)
def add_person(bid: int, data: Person, uid=Depends(auth)):
    with engine.begin() as c:
        own_book(c, bid, uid)
        return {'id': c.execute(persons.insert().values(book_id=bid, **data.model_dump())).inserted_primary_key[0]}

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

@app.post('/api/persons/{pid}/files', status_code=201)
async def upload(pid: int, file: UploadFile, uid=Depends(auth)):
    with engine.connect() as c:
        own_person(c, pid, uid)
    name = Path((file.filename or 'file').replace('\\', '/')).name[:255]
    suffix = Path(name).suffix.lower()
    data = await file.read(5 * 1024 * 1024 + 1)
    signatures = {'.pdf': b'%PDF-', '.png': b'\x89PNG\r\n\x1a\n', '.jpg': b'\xff\xd8\xff', '.jpeg': b'\xff\xd8\xff'}
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, '파일은 5MB 이하만 가능합니다.')
    if suffix not in signatures or not data.startswith(signatures[suffix]):
        raise HTTPException(400, 'PNG, JPG, PDF 파일만 업로드할 수 있습니다.')
    key = secrets.token_hex(24) + suffix
    (UPLOADS / key).write_bytes(data)
    try:
        with engine.begin() as c:
            own_person(c, pid, uid)
            fid = c.execute(files.insert().values(person_id=pid, name=name, storage_key=key)).inserted_primary_key[0]
    except Exception:
        (UPLOADS / key).unlink(missing_ok=True)
        raise
    return {'id': fid}

@app.get('/api/files/{fid}')
def download(fid: int, uid=Depends(auth)):
    with engine.connect() as c:
        row = c.execute(select(files).where(files.c.id == fid)).mappings().first()
        if not row:
            raise HTTPException(404, '파일이 없습니다.')
        own_person(c, row['person_id'], uid)
    return FileResponse(UPLOADS / row['storage_key'], filename=row['name'], media_type='application/octet-stream', headers={'X-Content-Type-Options': 'nosniff'})

app.mount('/', StaticFiles(directory=ROOT / 'frontend', html=True), name='frontend')
