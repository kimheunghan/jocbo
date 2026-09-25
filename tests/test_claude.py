"""Reading with Claude, held to the shape the page grammar gives, with Claude
itself stood in for: no key, no network and no charge are needed to run these."""
import io
import json
from types import SimpleNamespace

from PIL import Image

from backend import claude_read
from test_api import account, book, client  # noqa: F401  (client is a fixture)


def picture():
    buffer = io.BytesIO()
    Image.new('RGB', (600, 400), 'white').save(buffer, 'JPEG')
    return buffer.getvalue()


def answering(people, seen):
    """A Claude that answers with these people and notes what it was asked."""
    class Stream:
        def __init__(self, **request):
            seen.update(request)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def get_final_message(self):
            return SimpleNamespace(
                stop_reason='end_turn',
                content=[SimpleNamespace(type='text', text=json.dumps({'people': people}, ensure_ascii=False))],
                usage=SimpleNamespace(input_tokens=1000, output_tokens=500))
    return lambda key=None: SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=Stream)))


def line(**values):
    base = {'hanja_name': '', 'korean_name': '', 'gender': '미상', 'generation': 30, 'bon_gwan': '',
            'birth_date': '', 'death_date': '', 'married_in': False, 'note': '', 'family': 0, 'spouse': -1}
    base.update(values)
    return base


def test_a_page_read_by_claude_comes_back_as_the_local_reading_does(client, monkeypatch, tmp_path):
    monkeypatch.setattr(claude_read, 'ENV_FILE', tmp_path / '.env')
    account(client)
    bid = book(client)
    sid = client.post(f'/api/books/{bid}/scans', files={'file': ('618쪽.jpg', picture(), 'image/jpeg')}).json()['id']
    seen = {}
    monkeypatch.setattr(claude_read, 'client', answering([
        line(hanja_name='金順熙', korean_name='김순희', gender='여', birth_date='1952-02-29',
             note='연세대학원 석사 · 夫 金熙旋(김희선) 瑞興(서흥)人 父 學龍(학룡) · 子 東炫 · 女 志娟'),
        line(hanja_name='金熙旋', korean_name='김희선', gender='남', bon_gwan='瑞興', married_in=True,
             note='女 金順熙의 夫 · 父 學龍', spouse=0),
        line(hanja_name='朴順南', korean_name='박순남', gender='여', bon_gwan='密陽', married_in=True,
             note='父 泰鎬(태호)', spouse=7),
    ], seen))

    read = client.post(f'/api/scans/{sid}/read?engine=claude')
    assert read.status_code == 200
    people = read.json()['people']
    # The hangul the page prints is kept as read, and so is the whole note.
    assert (people[0]['korean_name'], people[0]['note'].startswith('연세대학원')) == ('김순희', True)
    assert (people[1]['spouse'], people[1]['key']) == (0, 1)
    # A partner the list does not hold is no partner.
    assert people[2]['spouse'] is None
    assert people[2]['note'] == '父 泰鎬(태호)'

    # The page is sent as a picture, with the grammar, to the model, with a
    # fallback should it decline, and the answer is held to a schema.
    assert seen['model'] == claude_read.MODEL
    assert seen['fallbacks'] == 'default'
    assert seen['output_config']['format']['type'] == 'json_schema'
    images = [part for part in seen['messages'][0]['content'] if part['type'] == 'image']
    assert len(images) == 1


def test_the_key_is_kept_beside_the_program_only_once_anthropic_takes_it(client, monkeypatch, tmp_path):
    monkeypatch.setattr(claude_read, 'ENV_FILE', tmp_path / '.env')
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    (tmp_path / '.env').write_text('COOKIE_SECURE=0\n', encoding='utf-8')
    account(client)
    assert client.get('/api/claude').json()['configured'] is False

    tried = []
    monkeypatch.setattr(claude_read, 'check_key', lambda key: tried.append(key))
    assert client.put('/api/claude/key', json={'key': 'sk-ant-test'}).json() == {'configured': True}
    assert tried == ['sk-ant-test']
    assert client.get('/api/claude').json()['configured'] is True
    # What else the file held is left as it was.
    assert (tmp_path / '.env').read_text(encoding='utf-8') == 'COOKIE_SECURE=0\nANTHROPIC_API_KEY=sk-ant-test\n'

    assert client.put('/api/claude/key', json={'key': ''}).json() == {'configured': False}
    assert (tmp_path / '.env').read_text(encoding='utf-8') == 'COOKIE_SECURE=0\n'
