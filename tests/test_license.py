"""The full version, with Lemon Squeezy stood in for by a fake license server."""
import pytest

from backend import license as paid
from backend import main as m
from tests.test_api import account, client  # noqa: F401 - fixture and helpers


class FakeLemon:
    """Two places per key, as the product is set up; one key for another product."""

    def __init__(self):
        self.instances = {'JOCBO-KEY-1': [], 'FINDINSIDE-KEY': []}
        self.down = False

    def __call__(self, action, **fields):
        if self.down:
            raise paid.LicenseError('라이선스 서버에 연결하지 못했습니다. 인터넷 연결을 확인해 주십시오.')
        key = fields['license_key']
        if key not in self.instances:
            raise paid.LicenseError(paid.explain('license_key not found.'))
        used = self.instances[key]
        if action == 'activate':
            if len(used) >= 2:
                return {'activated': False, 'error': 'This license key has reached the activation limit.'}
            used.append(f'inst-{len(used) + 1}')
            product = '우리의 족보 정식판' if key.startswith('JOCBO') else 'FindInside'
            return {'activated': True, 'instance': {'id': used[-1]}, 'meta': {'product_name': product}}
        used.remove(fields['instance_id'])
        return {'deactivated': True}


@pytest.fixture
def lemon(monkeypatch):
    fake = FakeLemon()
    monkeypatch.setattr(paid, 'call', fake)
    return fake


def test_a_key_lifts_the_limit_and_frees_its_place_when_taken_out(client, lemon):
    account(client)
    assert client.get('/api/me').json()['licensed'] is False
    bid = client.post('/api/books/sample').json()['id']
    extra = {'korean_name': '스물한째', 'generation': 30}
    assert client.post(f'/api/books/{bid}/persons', json=extra).status_code == 402

    assert client.post('/api/license', json={'key': 'JOCBO-KEY-1'}).json() == {'plan': 'paid'}
    me = client.get('/api/me').json()
    assert me['plan'] == 'paid' and me['licensed'] is True
    assert client.post(f'/api/books/{bid}/persons', json=extra).status_code == 201
    assert lemon.instances['JOCBO-KEY-1'] == ['inst-1']

    assert client.delete('/api/license').json() == {'plan': 'free'}
    assert lemon.instances['JOCBO-KEY-1'] == []
    assert client.get('/api/me').json()['licensed'] is False
    assert client.post(f'/api/books/{bid}/persons', json=extra).status_code == 402


def test_a_key_for_another_product_or_a_wrong_key_is_turned_down(client, lemon):
    account(client)
    r = client.post('/api/license', json={'key': 'FINDINSIDE-KEY'})
    assert r.status_code == 400 and '정식판 키가 아닙니다' in r.json()['detail']
    # The place it took for a moment is given back.
    assert lemon.instances['FINDINSIDE-KEY'] == []
    r = client.post('/api/license', json={'key': 'NO-SUCH-KEY'})
    assert r.status_code == 400 and '키가 맞지 않습니다' in r.json()['detail']
    assert client.get('/api/me').json()['plan'] == 'free'


def test_a_third_pc_is_told_to_free_one_first(client, lemon):
    lemon.instances['JOCBO-KEY-1'] = ['inst-a', 'inst-b']
    account(client)
    r = client.post('/api/license', json={'key': 'JOCBO-KEY-1'})
    assert r.status_code == 400 and 'PC 2대' in r.json()['detail']


def test_offline_says_so_and_changes_nothing(client, lemon):
    account(client)
    lemon.down = True
    r = client.post('/api/license', json={'key': 'JOCBO-KEY-1'})
    assert r.status_code == 400 and '연결하지 못했습니다' in r.json()['detail']
    assert client.get('/api/me').json()['plan'] == 'free'


def test_an_account_without_a_key_has_nothing_to_take_out(client, lemon):
    account(client)
    assert client.delete('/api/license').status_code == 400
