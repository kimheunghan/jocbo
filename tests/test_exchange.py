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


@pytest.mark.parametrize('kind', ['xlsx', 'ged'])
def test_edited_file_goes_back_into_its_book(client, kind, tmp_path):
    account(client)
    paid(client)
    bid = client.post('/api/books/sample').json()['id']
    sent = client.get(f'/api/books/{bid}/export', params={'format': kind}).content
    family = client.post('/api/import/preview', files={'file': (f'a.{kind}', sent)}).json()
    target = family['target']
    assert target['id'] == bid
    assert target['plan']['same'] == 20 and not target['plan']['added'] and not target['plan']['changed']
    # Edit as a person would: a new grandchild, a death date, one person left out.
    people = family['people']
    father = next(p for p in people if p['korean_name'] == '김민재')
    people.append({**father, 'key': 'new1', 'id': None, 'korean_name': '김새손', 'hanja_name': '', 'birth_date': '2018-04-05',
                   'death_date': '', 'note': '', 'generation': 30})
    family['parents'].append([father['key'], 'new1'])
    jiyoung = next(p for p in people if p['korean_name'] == '김지영')
    jiyoung['death_date'] = '2015-10-13'
    dropped = next(p for p in people if p['korean_name'] == '김도윤')
    people.remove(dropped)
    family['parents'] = [l for l in family['parents'] if dropped['key'] not in l]
    body = {k: family[k] for k in ('book', 'book_key', 'people', 'parents', 'spouses')}
    saved = client.post(f'/api/books/{bid}/merge', json=body)
    assert saved.status_code == 200, saved.text
    assert (saved.json()['added'], saved.json()['changed']) == (1, 1)
    back = client.get(f'/api/books/{bid}').json()
    names = {p['korean_name']: p for p in back['persons']}
    assert len(back['persons']) == 21 and '김도윤' in names
    assert names['김지영']['death_date'] == '2015-10-13'
    assert names['김새손']['generation'] == 30
    child_parents = {r['source_id'] for r in back['relations'] if r['kind'] == 'parent' and r['target_id'] == names['김새손']['id']}
    assert names['김민재']['id'] in child_parents
    # 김도윤 was left out of the file: kept, with the parents he had.
    assert any(r['target_id'] == names['김도윤']['id'] for r in back['relations'] if r['kind'] == 'parent')
    from backend import main as m
    assert list((m.UPLOADS.parent / 'backups').glob('*.ged'))
    assert len(client.get('/api/books').json()) == 1


def add(client, bid, name, gender='남'):
    r = client.post(f'/api/books/{bid}/persons', json={'korean_name': name, 'gender': gender})
    assert r.status_code == 201
    return r.json()['id']


def link(client, a, b, kind='parent'):
    assert client.post('/api/relations', json={'source_id': a, 'target_id': b, 'kind': kind}).status_code == 201


def awkward_book(client):
    """Links a tree cannot draw: a wife's child by an earlier marriage, and cousins who married."""
    bid = client.post('/api/books', json={'title': '어려운 족보', 'clan_name': '김씨'}).json()['id']
    gap, wife = add(client, bid, '김갑'), add(client, bid, '이씨', '여')
    link(client, gap, wife, 'spouse')
    son, daughter = add(client, bid, '김을'), add(client, bid, '김병녀', '여')
    for child in (son, daughter):
        link(client, gap, child)
        link(client, wife, child)
    son_wife, daughter_husband = add(client, bid, '박씨', '여'), add(client, bid, '최서방')
    link(client, son, son_wife, 'spouse')
    link(client, daughter, daughter_husband, 'spouse')
    grandson, granddaughter = add(client, bid, '김정'), add(client, bid, '최희', '여')
    link(client, son, grandson)
    link(client, son_wife, grandson)
    link(client, daughter, granddaughter)
    link(client, daughter_husband, granddaughter)
    link(client, grandson, granddaughter, 'spouse')
    earlier = add(client, bid, '정아', '여')
    link(client, wife, earlier)
    return bid


def sheets(content):
    names = [x.TREE_SHEET, x.EXTRA_SHEET, x.INFO_SHEET]
    return {name: x.read_xlsx(content, name, fallback=False) for name in names}


def rebuild(parts):
    return x.write_xlsx([(name, rows, [12] * 20, ()) for name, rows in parts.items()])


def test_links_a_tree_cannot_draw_survive_excel(client):
    account(client)
    paid(client)
    bid = awkward_book(client)
    original = client.get(f'/api/books/{bid}').json()
    sent = client.get(f'/api/books/{bid}/export', params={'format': 'xlsx'}).content
    parts = sheets(sent)
    assert len(parts[x.EXTRA_SHEET]) > 1
    tree = [[v for v in row if v is not None] for row in parts[x.TREE_SHEET]]
    assert any(isinstance(v, str) and '→ 번호' in v for row in tree for v in row)
    # A row inserted near the top moves every row below it; the references must still hold.
    parts[x.TREE_SHEET].insert(2, [None] * len(parts[x.TREE_SHEET][0]))
    edited = rebuild(parts)
    family = x.read_family('b.xlsx', edited)
    assert family['errors'] == []
    family, back = bring_in(client, 'b.xlsx', edited)
    assert signature(back)[1] == signature(original)[1]


def test_old_row_references_still_read():
    # Cousins who married, written the 2026.11.1–11.5 way: → 7행.
    rows = [['1세', '2세', '3세'], ['김갑', None, None], [None, '김을', None], [None, None, '김정'],
            [None, None, '配 최희 → 7행'], [None, '김병', None], [None, None, '최희']]
    family = x.tree_family(rows)
    assert family['errors'] == []
    assert family['spouses'] == [['r4', 'r7']]


def find_row(rows, text):
    return next(i for i, row in enumerate(rows) if any(isinstance(v, str) and v.startswith(text) for v in row))


def test_excel_edits_go_back_into_the_book(client):
    account(client)
    paid(client)
    bid = client.post('/api/books/sample').json()['id']
    parts = sheets(client.get(f'/api/books/{bid}/export', params={'format': 'xlsx'}).content)
    tree = parts[x.TREE_SHEET]
    head = [x._cell_text(v) for v in tree[0]]
    col = {name: head.index(name) for name in x.DETAIL_HEADS}
    width = len(head)
    # A new grandchild under 金民宰, typed into an inserted row without a number.
    at = find_row(tree, '金道允')
    new = [None] * width
    new[next(i for i, v in enumerate(tree[at]) if isinstance(v, str))] = '김새손'
    new[col['성별']], new[col['출생일']] = '남', '2018-04-05'
    tree.insert(at + 1, new)
    # A death date filled in.
    tree[find_row(tree, '金志英')][col['사망일']] = '2015-10-13'
    # A daughter moved from 金志勳 to his brother 金志英.
    moved = tree.pop(find_row(tree, '金泰恩'))
    tree.insert(find_row(tree, '配 姜淑子') + 1, moved)
    # A row deleted.
    tree.pop(find_row(tree, '金民瑞'))
    # The book's branch renamed on the 족보 정보 sheet.
    info = parts[x.INFO_SHEET]
    info[next(i for i, r in enumerate(info) if r and r[0] == '파명')][1] = '例示二派'

    family = client.post('/api/import/preview', files={'file': ('a.xlsx', rebuild(parts))}).json()
    assert family['errors'] == []
    plan = family['target']['plan']
    assert plan['added'] == ['김새손'] and plan['missing'] == ['金民瑞(김민서)']
    assert {c['name'] for c in plan['changed']} == {'金志英(김지영)'}
    assert plan['book_changes'] == [['파명', '例示派', '例示二派']]
    assert plan['links_added'] >= 3 and plan['links_removed'] >= 2

    body = {k: family[k] for k in ('book', 'book_key', 'people', 'parents', 'spouses')}
    assert client.post(f'/api/books/{bid}/merge', json=body).status_code == 200
    back = client.get(f'/api/books/{bid}').json()
    names = {p['korean_name']: p['id'] for p in back['persons']}
    parents = lambda who: {r['source_id'] for r in back['relations'] if r['kind'] == 'parent' and r['target_id'] == names[who]}
    assert back['branch_name'] == '例示二派'
    assert parents('김태은') == {names['김지영'], names['강숙자']}
    assert parents('김새손') == {names['김민재'], names['이서연']}
    assert '김민서' in names and parents('김민서') == {names['김태호'], names['최미경']}

    backups = client.get('/api/backups').json()
    assert len(backups) == 1 and backups[0]['title'] == '金海金氏族譜'
    restored = client.post('/api/import/backup', json={'name': backups[0]['name']})
    assert restored.status_code == 200 and len(restored.json()['people']) == 20
    assert client.post('/api/import/backup', json={'name': '../jocbo.db'}).status_code == 404


def test_backups_belong_to_their_account(client):
    account(client)
    paid(client)
    bid = client.post('/api/books/sample').json()['id']
    sent = client.get(f'/api/books/{bid}/export', params={'format': 'ged'}).content
    family = client.post('/api/import/preview', files={'file': ('a.ged', sent)}).json()
    body = {k: family[k] for k in ('book', 'book_key', 'people', 'parents', 'spouses')}
    assert client.post(f'/api/books/{bid}/merge', json=body).status_code == 200
    name = client.get('/api/backups').json()[0]['name']
    client.post('/api/logout')
    account(client)
    assert client.get('/api/backups').json() == []
    assert client.post('/api/import/backup', json={'name': name}).status_code == 404


def test_free_account_merge_keeps_the_limit(client):
    account(client)
    bid = client.post('/api/books/sample').json()['id']
    sent = client.get(f'/api/books/{bid}/export', params={'format': 'ged'}).content
    family = client.post('/api/import/preview', files={'file': ('a.ged', sent)}).json()
    family['people'].append({**family['people'][-1], 'key': 'extra', 'id': None, 'korean_name': '한 명 더'})
    body = {k: family[k] for k in ('book', 'book_key', 'people', 'parents', 'spouses')}
    assert client.post(f'/api/books/{bid}/merge', json=body).status_code == 402
    assert len(client.get(f'/api/books/{bid}').json()['persons']) == 20
    assert client.get('/api/backups').json() == []


def test_book_list_counts_people(client):
    account(client)
    client.post('/api/books/sample')
    client.post('/api/books', json={'title': '빈 족보'})
    assert [(b['title'], b['people']) for b in client.get('/api/books').json()] == [('金海金氏族譜', 20), ('빈 족보', 0)]


def test_merge_refuses_a_file_from_another_book(client):
    account(client)
    paid(client)
    first = client.post('/api/books/sample').json()['id']
    second = client.post('/api/books/sample').json()['id']
    sent = client.get(f'/api/books/{first}/export', params={'format': 'ged'}).content
    family = client.post('/api/import/preview', files={'file': ('a.ged', sent)}).json()
    assert family['target']['id'] == first
    body = {k: family[k] for k in ('book', 'book_key', 'people', 'parents', 'spouses')}
    assert client.post(f'/api/books/{second}/merge', json=body).status_code == 400


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


def test_gedcom_tags_passed_on_by_gramps():
    # Gramps keeps tags it does not know as typed events.
    text = ('0 HEAD\n1 CHAR UTF-8\n0 @I1@ INDI\n1 NAME 영조 /김/\n1 NAME 永祖 /金/\n'
            '1 EVEN 25\n2 TYPE _GEN\n1 EVEN 金海\n2 TYPE _BONGWAN\n0 TRLR\n')
    person = x.read_family('g.ged', text.encode('utf-8'))['people'][0]
    assert (person['korean_name'], person['hanja_name']) == ('김영조', '金永祖')
    assert (person['generation'], person['bon_gwan']) == (25, '金海')


def test_book_fields_old_and_new_header():
    old = ('0 HEAD\n1 CHAR UTF-8\n1 _BOOK\n2 TITL 옛 족보\n2 _KEY abc\n2 _CLAN 金氏\n2 NOTE 첫 줄\n3 CONT 둘째 줄\n'
           '0 @I1@ INDI\n1 NAME 김갑\n0 TRLR\n')
    family = x.read_family('old.ged', old.encode('utf-8'))
    assert (family['book']['title'], family['book']['clan_name'], family['book_key']) == ('옛 족보', '金氏', 'abc')
    book = {'title': '새 족보', 'clan_name': '金氏', 'book_key': 'k1', 'description': '첫 줄\n둘째 줄: 콜론',
            'persons': [{'id': 1, 'korean_name': '김갑', 'hanja_name': '', 'generation': 1, 'gender': '남',
                         'bon_gwan': '', 'birth_date': '', 'death_date': '', 'note': ''}], 'relations': []}
    family = x.read_family('new.ged', x.gedcom(book).encode('utf-8'))
    assert family['book']['description'] == '첫 줄\n둘째 줄: 콜론' and family['book_key'] == 'k1'
    assert '_BOOK' not in x.gedcom(book)


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
