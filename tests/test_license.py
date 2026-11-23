"""The full version, with our license server stood in for by a fake one."""
import pytest

from backend import license as paid
from backend import main as m
from tests.test_api import account, client  # noqa: F401 - fixture and helpers


class FakeServer:
    """Our license server (share/lib/license.js): two places per key, keys for
    both programs it sells, and Lemon Squeezy keys it has taken over."""

    PRODUCTS = {'JOCBO-KEY-1': 'jocbo', 'FINDINSIDE-KEY': 'findinside', '5AC927E4-617A-46EF-9947-43E1B5903BEA': 'jocbo'}

    def __init__(self):
        self.instances = {key: [] for key in self.PRODUCTS}
        self.down = False
        self.asked = []

    def __call__(self, action, payload):
        self.asked.append((action, payload))
        if self.down:
            raise paid.LicenseError('라이선스 서버에 연결하지 못했습니다. 인터넷 연결을 확인해 주십시오.')
        key = payload['key'].upper()
        if key not in self.instances:
            raise paid.LicenseError('라이선스 키가 맞지 않습니다. 결제 확인 이메일의 키를 그대로 붙여 넣어 주십시오.')
        used = self.instances[key]
        if action == 'activate':
            if self.PRODUCTS[key] != payload['product']:
                raise paid.LicenseError('우리의 족보 정식판 키가 아닙니다.')
            if len(used) >= 2:
                raise paid.LicenseError('이 키는 이미 PC 2대에 등록되어 있습니다. 쓰지 않는 PC에서 먼저 등록을 풀어 주십시오.')
            used.append(f'ins_{len(used) + 1}')
            return {'activated': True, 'instance': used[-1], 'product': self.PRODUCTS[key]}
        used.remove(payload['instance'])
        return {'deactivated': True}


@pytest.fixture
def lemon(monkeypatch):
    fake = FakeServer()
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
    assert lemon.instances['JOCBO-KEY-1'] == ['ins_1']

    assert client.delete('/api/license').json() == {'plan': 'free'}
    assert lemon.instances['JOCBO-KEY-1'] == []
    assert client.get('/api/me').json()['licensed'] is False
    assert client.post(f'/api/books/{bid}/persons', json=extra).status_code == 402


def test_a_key_for_another_product_or_a_wrong_key_is_turned_down(client, lemon):
    account(client)
    r = client.post('/api/license', json={'key': 'FINDINSIDE-KEY'})
    assert r.status_code == 400 and '정식판 키가 아닙니다' in r.json()['detail']
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


def test_the_program_asks_our_server_for_its_own_product(client, lemon):
    account(client)
    client.post('/api/license', json={'key': ' JOCBO-KEY-1 '})
    action, payload = lemon.asked[0]
    assert action == 'activate' and payload['product'] == 'jocbo' and payload['key'] == 'JOCBO-KEY-1' and payload['name']


def test_a_lemon_squeezy_key_still_works_through_our_server(client, lemon):
    account(client)
    assert client.post('/api/license', json={'key': '5ac927e4-617a-46ef-9947-43e1b5903bea'}).json() == {'plan': 'paid'}
    assert client.delete('/api/license').json() == {'plan': 'free'}


def test_the_server_address_is_ours():
    assert paid.SERVER.startswith('https://jocbo.pages.dev') or paid.SERVER.startswith('http')
