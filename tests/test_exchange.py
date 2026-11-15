"""GEDCOM and Excel tree, out and back in."""
import io
import zipfile

import pytest

from backend import exchange as x
from test_api import account, client  # noqa: F401  (fixture)


def paid(client):
    from backend import main as m
    with m.engine.begin() as c:
        c.execute(m.users.update().values(plan='paid'))


def signature(book):
    name = {p['id']: p['korean_name'] for p in book['persons']}
    people = sorted((p['korean_name'], p['hanja_name'], p['generation'], p['gender'], p['bon_gwan'],
                     p['birth_date'], p['death_date'], p['note']) for p in book['persons'])
    links = sorted((r['kind'], *((name[r['source_id']], name[r['target_id']]) if r['kind'] == 'parent'
                                 else sorted((name[r['source_id']], name[r['target_id']])))) for r in book['relations'])
    return people, links


def bring_in(client, name, content):
    preview = client.post('/api/import/preview', files={'file': (name, content)})
    assert preview.status_code == 200, preview.text
    family = preview.json()
    assert family['errors'] == []
    saved = client.post('/api/books/import', json={k: family[k] for k in ('book', 'people', 'parents', 'spouses')})
    assert saved.status_code == 201, saved.text
    return family, client.get(f"/api/books/{saved.json()['id']}").json()


@pytest.mark.parametrize('kind', ['ged', 'xlsx'])
def test_sample_book_comes_back_the_same(client, kind):
    account(client)
    paid(client)
    bid = client.post('/api/books/sample').json()['id']
    original = client.get(f'/api/books/{bid}').json()
    sent = client.get(f'/api/books/{bid}/export', params={'format': kind})
    assert sent.status_code == 200
    assert "filename*=UTF-8''" in sent.headers['content-disposition']
    family, back = bring_in(client, f'金海金氏族譜 가계도.{kind}', sent.content)
    assert signature(back) == signature(original)
    for field in ('title', 'clan_name', 'bon_gwan', 'branch_name', 'founder', 'description'):
        assert back[field] == original[field]


def test_free_account_keeps_its_limit_on_import(client):
    account(client)
    bid = client.post('/api/books/sample').json()['id']
    sent = client.get(f'/api/books/{bid}/export', params={'format': 'ged'}).content
    family = client.post('/api/import/preview', files={'file': ('a.ged', sent)}).json()
    saved = client.post('/api/books/import', json={k: family[k] for k in ('book', 'people', 'parents', 'spouses')})
    assert saved.status_code == 402
    assert len(client.get('/api/books').json()) == 1


OTHER_PROGRAM = '''0 HEAD
1 SOUR MYHERITAGE
1 GEDC
2 VERS 5.5.1
1 CHAR UTF-8
1 FILE Park family.ged
0 @I1@ INDI
1 NAME 철수 /박/
2 GIVN 철수
2 SURN 박
1 NAME Cheolsu /Park/
2 TYPE aka
1 SEX M
1 BIRT
2 DATE ABT 1850
2 PLAC 경상북도 경주
1 DEAT
2 DATE 3 JAN 1920
1 NOTE 긴 메모의 첫 부분이고
2 CONC  이어지는 부분입니다
2 CONT 둘째 줄
1 FAMS @F1@
0 @I2@ INDI
1 NAME 李氏
1 SEX F
1 NOTE @N1@
1 FAMS @F1@
0 @I3@ INDI
1 NAME 영희 /박/
1 SEX F
1 BIRT
2 DATE MAR 1880
1 FAMC @F1@
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I9@
0 @N1@ NOTE 공유 메모
0 TRLR
'''


def test_gedcom_from_another_program():
    family = x.read_family('Park family.ged', OTHER_PROGRAM.encode('utf-8'))
    assert family['errors'] == []
    people = {p['key']: p for p in family['people']}
    father, mother, daughter = people['I1'], people['I2'], people['I3']
    assert father['korean_name'] == '박철수' and father['gender'] == '남'
    assert father['birth_date'] == '' and '출생 ABT 1850' in father['note']
    assert '출생지 경상북도 경주' in father['note'] and '영문 이름 Cheolsu Park' in father['note']
    assert '긴 메모의 첫 부분이고 이어지는 부분입니다\n둘째 줄' in father['note']
    assert father['death_date'] == '1920-01-03'
    assert mother['hanja_name'] == '李氏' and mother['korean_name'] == '이씨' and mother['note'] == '공유 메모'
    assert daughter['birth_date'] == '1880-03'
    assert sorted(family['parents']) == [['I1', 'I3'], ['I2', 'I3']]
    assert family['spouses'] == [['I1', 'I2']]
    assert (father['generation'], daughter['generation']) == (1, 2)
    assert family['book']['title'] == 'Park family'
    assert any('찾지 못해' in w for w in family['warnings'])


def test_gedcom_dates():
    for ours in ('1956', '1956-03', '1956-03-02', '--03-02'):
        assert x.from_gedcom_date(x.to_gedcom_date(ours)) == ours
    for vague in ('ABT 1850', 'BET 1850 AND 1860', '@#DJULIAN@ 1700', 'FROM 1900 TO 1910'):
        assert x.from_gedcom_date(vague) is None


def rows_to_xlsx(rows):
    sheet = [[(v if not isinstance(v, str) else (v, 'plain')) for v in row] for row in rows]
    return x.write_xlsx([('가계도', sheet, [12] * 12, ())])


def test_hand_drawn_tree():
    rows = [
        ['25세', '26세', '27세', '세', '성별', '출생일', '다른 부모', '기록'],
        ['金甲(김갑)', None, None, None, '남', 1900.0, None, None],
        ['配 박씨', None, None, None, '여', None, None, None],
        ['配 최씨', None, None, None, '여', None, None, None],
        [None, '김을', None, None, '남', '1925.3.2', '최씨', None],
        [None, '김병', None, None, '남', 'ABT 1930', None, None],
        [None, None, '金丁', None, None, '5월 1일', None, None],
        [None, '김무', None, None, '여', 30000.0, '(미상)', None],
    ]
    family = x.read_family('손으로 그린 가계도.xlsx', rows_to_xlsx(rows))
    assert family['errors'] == []
    people = {p['key']: p for p in family['people']}
    assert people['r2']['birth_date'] == '1900' and people['r2']['generation'] == 25
    assert people['r5']['birth_date'] == '1925-03-02'
    assert people['r7']['korean_name'] == '김정' and people['r7']['birth_date'] == '--05-01' and people['r7']['generation'] == 27
    assert people['r8']['birth_date'] == '1982-02-18'
    assert '출생 ABT 1930' in people['r6']['note']
    parents = sorted(map(tuple, family['parents']))
    assert ('r2', 'r5') in parents and ('r4', 'r5') in parents and ('r3', 'r5') not in parents
    assert ('r2', 'r8') in parents and not any(c == 'r8' and p != 'r2' for p, c in parents)
    # 김병 has no 다른 부모 while 김갑 has two wives: only the father is linked, with a warning.
    assert [p for p, c in parents if c == 'r6'] == ['r2']
    assert any(w.startswith('6행') for w in family['warnings'])
    assert family['book']['title'] == '손으로 그린'


def test_tree_mistakes_are_named_by_row():
    rows = [
        ['1세', '2세', '3세', '성별'],
        ['김갑', None, None, None],
        [None, None, '김손', None],
        ['配 이씨', '김을', None, None],
        [None, '배 최씨', None, None],
        [None, '김병 → 40행', None, None],
    ]
    family = x.tree_family(rows)
    joined = '\n'.join(family['errors'])
    assert '3행' in joined and '4행' in joined and '6행' in joined


def test_csv_and_old_excel():
    text = '1세,2세,성별\n김갑,,남\n,김을,남\n'
    family = x.read_family('tree.csv', text.encode('cp949'))
    assert [p['korean_name'] for p in family['people']] == ['김갑', '김을']
    assert family['parents'] == [['r2', 'r3']]
    with pytest.raises(x.ExchangeError, match='xls'):
        x.read_family('old.xls', b'\xd0\xcf\x11\xe0' + b'\0' * 100)
    with pytest.raises(x.ExchangeError):
        x.read_family('photo.png', b'\x89PNG....')


def test_loops_are_refused():
    people = [x.blank_person(k) for k in 'abc']
    with pytest.raises(x.ExchangeError, match='순환'):
        x.settle_generations(people, [('a', 'b'), ('b', 'c'), ('c', 'a')], [])


def test_template_reads_back(client):
    account(client)
    sheet = client.get('/api/import/template')
    assert sheet.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(sheet.content)).testzip() is None
    family = x.read_family('가계도 양식.xlsx', sheet.content)
    assert family['errors'] == [] and len(family['people']) == 7
    assert family['book']['title'] == '가계도 양식'
    sheet = client.get('/api/import/template', params={'format': 'ged'})
    assert sheet.status_code == 200 and sheet.content.startswith(b'0 HEAD')
    family = x.read_family('GEDCOM 양식.ged', sheet.content)
    assert family['errors'] == [] and len(family['people']) == 7
    assert len(family['parents']) == 8 and len(family['spouses']) == 2
    assert sorted(p['generation'] for p in family['people']) == [1, 1, 2, 2, 2, 3, 3]
