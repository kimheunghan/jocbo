"""설치 파일판의 새 판 알림과 설치 파일 받기(backend/update.py)."""
import hashlib
import json

import pytest

from backend import update
from test_api import client  # noqa: F401  (fixture)

SETUP = b'fake installer bytes'
GOOD = {'version': '2026.11.12', 'url': 'https://jocbo.pages.dev/download/store-v2026.11.12/jocbo-setup.exe',
        'sha256': hashlib.sha256(SETUP).hexdigest(), 'notes': '바뀐 점'}


@pytest.fixture
def exe(tmp_path, monkeypatch):
    """판 번호 2026.11.11 인 설치 파일판처럼 꾸밉니다. 홈페이지 대신 GOOD 을 돌려줍니다."""
    (tmp_path / 'app').mkdir()
    (tmp_path / 'app' / 'version.txt').write_text('2026.11.11\n', encoding='utf-8')
    monkeypatch.setattr(update, 'ROOT', tmp_path / 'app')
    monkeypatch.setenv('JOCBO_CHANNEL', 'exe')
    monkeypatch.setenv('JOCBO_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(update, 'pending', None)
    calls = []

    def fetch():
        calls.append(1)
        return dict(GOOD)
    monkeypatch.setattr(update, 'fetch', fetch)
    return calls


def test_versions_compare_by_number():
    assert update.newer('2026.11.12', '2026.11.11')
    assert update.newer('2026.12.1', '2026.11.30')
    assert not update.newer('2026.11.11', '2026.11.11')
    assert not update.newer('2026.11.9', '2026.11.11')
    assert not update.newer('nonsense', '2026.11.11')


def test_a_newer_version_is_offered_once_a_day(exe):
    assert update.available(now=1000)['version'] == '2026.11.12'
    assert update.available(now=1000 + 3600)['version'] == '2026.11.12'
    assert len(exe) == 1  # 하루 안에는 홈페이지에 다시 묻지 않습니다.
    update.available(now=1000 + update.ONE_DAY)
    assert len(exe) == 2


def test_later_waits_a_day(exe):
    update.later(now=1000)
    assert update.available(now=1000 + 60) is None
    assert update.available(now=1000 + update.ONE_DAY) is not None


@pytest.mark.parametrize('channel', ['store', ''])
def test_store_and_development_runs_never_ask(exe, monkeypatch, channel):
    monkeypatch.setenv('JOCBO_CHANNEL', channel)
    assert update.available(now=1000) is None
    assert exe == []


@pytest.mark.parametrize('change', [
    {'version': '2026.11.11'},                                   # 같은 판
    {'version': '2026.11.10'},                                   # 옛 판
    {'url': 'https://example.com/jocbo-setup.exe'},              # 우리 주소가 아님
    {'url': 'http://jocbo.pages.dev/download/x/jocbo-setup.exe'},  # https 아님
    {'sha256': 'abc'},                                           # 확인값이 이상함
])
def test_doubtful_information_is_not_offered(exe, monkeypatch, change):
    monkeypatch.setattr(update, 'fetch', lambda: {**GOOD, **change})
    assert update.available(now=1000) is None


def test_no_internet_is_quiet(exe, monkeypatch):
    def fail():
        raise OSError('offline')
    monkeypatch.setattr(update, 'fetch', fail)
    assert update.available(now=1000) is None


class Response:
    def __init__(self, data):
        self.data = data

    def read(self, size=-1):
        chunk, self.data = (self.data, b'') if size < 0 else (self.data[:size], self.data[size:])
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_download_checks_the_file(exe, monkeypatch, tmp_path):
    monkeypatch.setattr(update.urllib.request, 'urlopen', lambda *a, **k: Response(SETUP))
    path = update.download(dict(GOOD))
    assert path.read_bytes() == SETUP and update.pending == path


def test_a_wrong_file_is_thrown_away(exe, monkeypatch, tmp_path):
    monkeypatch.setattr(update.urllib.request, 'urlopen', lambda *a, **k: Response(b'something else'))
    with pytest.raises(update.UpdateError):
        update.download(dict(GOOD))
    assert update.pending is None
    assert list((tmp_path / 'update').glob('*.exe')) == []


def test_api_reports_version_and_new_version(client, exe):
    assert client.get('/api/app').json() == {'version': '2026.11.11', 'channel': 'exe'}
    body = client.get('/api/update').json()
    assert body['available'] and body['version'] == '2026.11.12'
    assert client.post('/api/update/later', json={}).status_code == 200
    assert client.get('/api/update').json()['available'] is False
    assert json.loads(update._state_file().read_text(encoding='utf-8'))['later'] > 0


def test_install_needs_a_json_body(client, exe):
    # 다른 사이트가 이 PC 의 서버로 보내는 폼 요청은 받지 않습니다.
    assert client.post('/api/update/install', data='x', headers={'Content-Type': 'text/plain'}).status_code == 422


def test_store_asks_the_store_every_time(exe, monkeypatch):
    # Store 판은 홈페이지가 아니라 Microsoft Store 에 묻고, 켤 때마다 묻습니다.
    monkeypatch.setenv('JOCBO_CHANNEL', 'store')
    calls = []

    class Version:
        major, minor, build = 2026, 11, 12

    class Update:
        class package:
            class id:
                version = Version

    def store_updates():
        calls.append(1)
        return None, [Update]
    monkeypatch.setattr(update, '_store_updates', store_updates)
    assert update.available()['version'] == '2026.11.12'
    assert update.available()['version'] == '2026.11.12'
    assert len(calls) == 2 and exe == []  # 홈페이지에는 묻지 않습니다.
    monkeypatch.setattr(update, '_store_updates', lambda: (None, []))
    assert update.available() is None


def test_store_failure_is_quiet(exe, monkeypatch):
    monkeypatch.setenv('JOCBO_CHANNEL', 'store')

    def fail():
        raise OSError('no store')
    monkeypatch.setattr(update, '_store_updates', fail)
    assert update.available() is None


def test_store_install_goes_through_the_store(client, exe, monkeypatch):
    monkeypatch.setenv('JOCBO_CHANNEL', 'store')
    called = []
    monkeypatch.setattr(update, 'store_install', lambda: called.append(1) or 3)
    assert client.post('/api/update/install', json={}).json() == {'version': '', 'store': True}
    assert called == [1] and update.pending is None  # 설치 파일을 받지 않습니다.
