"""Web sharing: the book goes up to the share site (share/, on Netlify) on its own.

Once a book is shared, every change made in this program is sent up a few
seconds later, so the family's link always shows the book as it stands. When
the internet is down the change waits and goes up when it comes back.

The site keeps a copy for viewing only; the book itself stays here.
"""
import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request

# The share site. Set JOCBO_SHARE_SERVER to try another (netlify dev: http://localhost:8888).
SERVER = os.getenv('JOCBO_SHARE_SERVER', 'https://jocbo.netlify.app').rstrip('/')
# A file larger than this is not sent; a share function takes a few MB at most.
LARGEST = 4 * 1024 * 1024


class ShareError(Exception):
    pass


def call(method, url, token='', body=None, content_type='application/json'):
    data = json.dumps(body).encode() if content_type == 'application/json' and body is not None else body
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header('Content-Type', content_type)
    if token:
        request.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read()).get('detail')
        except Exception:
            detail = None
        raise ShareError(detail or f'공유 사이트가 요청을 받지 않았습니다 ({error.code}).')
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ShareError('공유 사이트에 연결하지 못했습니다. 인터넷 연결을 확인해 주십시오.')


def create(password):
    return call('POST', SERVER + '/api/share', body={'password': password})


def remove(row):
    call('DELETE', f"{row['server']}/api/share/{row['share_id']}", row['token'])


def link(row):
    return f"{row['server']}/s/{row['share_id']}"


def snapshot(book):
    """What the family sees: the book without the scans of its pages."""
    book = {key: value for key, value in book.items() if key not in ('scans', 'user_id')}
    book['files'] = [dict(f) for f in book['files']]
    book['relations'] = [dict(r) for r in book['relations']]
    return book


def push(row, book, password=None):
    """Send the book up if it changed since the last time, then any photo the site lacks.

    Gives back the fingerprint of what was sent.
    """
    from backend import main
    copy = snapshot(book)
    fingerprint = hashlib.sha256(json.dumps(copy, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if fingerprint == row['synced'] and password is None:
        return fingerprint
    base = f"{row['server']}/api/share/{row['share_id']}"
    body = {'book': copy}
    if password is not None:
        body['password'] = password
    there = set(call('PUT', base, row['token'], body).get('files', []))
    for file in copy['files']:
        if str(file['id']) in there:
            continue
        with main.engine.connect() as c:
            key = c.execute(main.select(main.files.c.storage_key).where(main.files.c.id == file['id'])).scalar()
        if not key:
            continue
        small = main.thumbnail(key, 240)
        if small:
            call('PUT', f"{base}/files/{file['id']}?size=thumb", row['token'], small.read_bytes(), 'image/jpeg')
        large = main.thumbnail(key, 1600)
        source = large or (main.UPLOADS / key)
        if source.exists() and source.stat().st_size <= LARGEST:
            call('PUT', f"{base}/files/{file['id']}", row['token'], source.read_bytes(),
                 'image/jpeg' if large else 'application/octet-stream')
    return fingerprint


def sync_all():
    """Bring every shared book up to date. Gives True when everything went up."""
    from backend import main
    with main.engine.connect() as c:
        rows = [dict(r) for r in c.execute(main.select(main.shares)).mappings()]
    done = True
    for row in rows:
        try:
            with main.engine.connect() as c:
                owner = c.execute(main.select(main.books.c.user_id).where(main.books.c.id == row['book_id'])).scalar()
                book = main.book_detail(c, row['book_id'], owner)
            fingerprint = push(row, book)
            values = {'synced': fingerprint, 'error': '', 'synced_at': int(time.time())}
        except ShareError as error:
            values, done = {'error': str(error)}, False
        except Exception as error:  # a book removed meanwhile, a photo gone missing
            values, done = {'error': f'올리지 못했습니다: {error}'}, False
        with main.engine.begin() as c:
            c.execute(main.shares.update().where(main.shares.c.book_id == row['book_id']).values(**values))
    return done


class Worker:
    """Sends changes up in the background, a moment after they are made."""

    def __init__(self):
        self.wake = threading.Event()
        self.stopping = False
        self.thread = None

    def changed(self):
        self.wake.set()

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.stopping = False
            self.thread = threading.Thread(target=self.run, name='share-sync', daemon=True)
            self.thread.start()

    def stop(self):
        self.stopping = True
        self.wake.set()

    def run(self):
        done = True
        while not self.stopping:
            # Waits for a change; tries again every minute while something failed.
            self.wake.wait(60 if not done else 600)
            if self.stopping:
                break
            self.wake.clear()
            # A family added in one go is many requests; they go up together.
            time.sleep(3)
            self.wake.clear()
            try:
                done = sync_all()
            except Exception:
                done = False


worker = Worker()
