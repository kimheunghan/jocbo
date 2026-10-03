"""Web sharing, with the share site stood in for by a fake that keeps what it is sent."""
import pytest

from backend import share as web_share
from tests.test_api import account, book, client, person  # noqa: F401 - fixture and helpers


class FakeSite:
    def __init__(self):
        self.books, self.files, self.removed, self.down = {}, {}, [], False

    def __call__(self, method, url, token='', body=None, content_type='application/json'):
        if self.down:
            raise web_share.ShareError('공유 사이트에 연결하지 못했습니다. 인터넷 연결을 확인해 주십시오.')
        path = url.split('/api/share', 1)[1]
        if method == 'POST':
            return {'id': 'abcdefghijkl', 'token': 'secret-token'}
        assert token == 'secret-token'
        if method == 'DELETE':
            self.removed.append(path)
            return {'ok': True}
        if '/files/' in path:
            self.files[path] = body
            return {'ok': True}
        self.books[path] = body
        return {'ok': True, 'files': []}


@pytest.fixture
def site(monkeypatch):
    fake = FakeSite()
    monkeypatch.setattr(web_share, 'call', fake)
    monkeypatch.setattr(web_share, 'SERVER', 'https://share.example')
    return fake


def test_a_shared_book_goes_up_with_its_link(client, site):
    account(client)
    bid = book(client)
    person(client, bid, '공유 인물')
    assert client.get(f'/api/books/{bid}/share').json() == {'shared': False}

    r = client.post(f'/api/books/{bid}/share')
    assert r.status_code == 201
    state = r.json()
    assert state['shared'] and state['link'] == 'https://share.example/s/abcdefghijkl'
    assert not state['error'] and not state['pending']
    sent = site.books['/abcdefghijkl']['book']
    assert [p['korean_name'] for p in sent['persons']] == ['공유 인물']
    # The scans of the printed pages stay on this computer.
    assert 'scans' not in sent and 'user_id' not in sent
    assert client.post(f'/api/books/{bid}/share').status_code == 409


def test_changes_go_up_and_an_unchanged_book_is_not_sent_again(client, site):
    account(client)
    bid = book(client)
    client.post(f'/api/books/{bid}/share')
    site.books.clear()
    assert web_share.sync_all()
    assert site.books == {}
    person(client, bid, '새 인물')
    assert web_share.sync_all()
    assert [p['korean_name'] for p in site.books['/abcdefghijkl']['book']['persons']] == ['새 인물']


def test_an_offline_change_waits_and_shows_why(client, site):
    account(client)
    bid = book(client)
    client.post(f'/api/books/{bid}/share')
    site.down = True
    person(client, bid)
    assert not web_share.sync_all()
    assert '연결하지 못했습니다' in client.get(f'/api/books/{bid}/share').json()['error']
    site.down = False
    assert web_share.sync_all()
    assert client.get(f'/api/books/{bid}/share').json()['error'] == ''


def test_stopping(client, site):
    account(client)
    bid = book(client)
    client.post(f'/api/books/{bid}/share')
    # The family opens the link alone; nothing about a password goes up.
    assert set(site.books['/abcdefghijkl']) == {'book'}
    # Stopping fails loudly when the copy on the site cannot be removed.
    site.down = True
    assert client.delete(f'/api/books/{bid}/share').status_code == 502
    assert client.get(f'/api/books/{bid}/share').json()['shared']
    site.down = False
    assert client.delete(f'/api/books/{bid}/share').json() == {'shared': False}
    assert site.removed == ['/abcdefghijkl']


def test_someone_elses_book_cannot_be_shared(client, site):
    account(client)
    bid = book(client)
    client.post('/api/logout')
    account(client)
    assert client.post(f'/api/books/{bid}/share').status_code == 404
    assert client.get(f'/api/books/{bid}/share').status_code == 404
