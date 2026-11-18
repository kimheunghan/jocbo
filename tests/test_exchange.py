"""엑셀 가계도와 GEDCOM의 내보내기·불러오기·기존 족보 반영 (docs/불러오기-내보내기-기획.md 9장)."""
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
    """사람과 관계(입양 여부, 남편·아내별 혼인 순서 포함)를 이름으로 적은 것."""
    name = {p['id']: p['korean_name'] for p in book['persons']}
    people = sorted((p['korean_name'], p['hanja_name'], p['generation'], p['gender'], p['bon_gwan'],
                     p['birth_date'], p['death_date'], p['note']) for p in book['persons'])
    links = sorted(('parent', name[r['source_id']], name[r['target_id']], bool(r.get('adopted')))
                   for r in book['relations'] if r['kind'] == 'parent')
    spouses = sorted(tuple(sorted((name[r['source_id']], name[r['target_id']]))) for r in book['relations'] if r['kind'] == 'spouse')
    return people, links, spouses, wife_order(book)


def wife_order(book):
    """사람마다 배우자를 혼인 순서대로 적은 것: {이름: [첫째, 둘째 …]}."""
    name = {p['id']: p['korean_name'] for p in book['persons']}
    links = {}
    for r in book['relations']:
        if r['kind'] == 'spouse':
            for one, other in ((r['source_id'], r['target_id']), (r['target_id'], r['source_id'])):
                links.setdefault(name[one], []).append((r, name[other]))
    return {who: [mate for _, mate in x.in_marriage_order(items)] for who, items in links.items() if len(items) > 1}


def body(family):
    return {k: family[k] for k in ('book', 'book_key', 'people', 'parents', 'spouses')}


def bring_in(client, name, content):
    preview = client.post('/api/import/preview', files={'file': (name, content)})
    assert preview.status_code == 200, preview.text
    family = preview.json()
    assert family['errors'] == []
    saved = client.post('/api/books/import', json=body(family))
    assert saved.status_code == 201, saved.text
    return family, client.get(f"/api/books/{saved.json()['id']}").json()


def add(client, bid, name, gender='남', **fields):
    r = client.post(f'/api/books/{bid}/persons', json={'korean_name': name, 'gender': gender, **fields})
    assert r.status_code == 201
    return r.json()['id']


def link(client, a, b, kind='parent'):
    r = client.post('/api/relations', json={'source_id': a, 'target_id': b, 'kind': kind})
    assert r.status_code == 201
    return r.json()['id']


def remarried_book(client):
    """본처와 후처, 각 부인의 자녀, 양자 하나, 딸과 사위가 있는 족보."""
    bid = client.post('/api/books', json={'title': '재혼 족보', 'clan_name': '金氏'}).json()['id']
    father = add(client, bid, '김갑', hanja_name='金甲', generation=25)
    first, second = add(client, bid, '이씨', '여', hanja_name='李氏'), add(client, bid, '박씨', '여', hanja_name='朴氏')
    link(client, father, first, 'spouse')
    rid = link(client, father, second, 'spouse')
    assert client.put(f'/api/relations/{rid}', json={'marriage_order': 2}).status_code == 200
    older, younger = add(client, bid, '김을', hanja_name='金乙'), add(client, bid, '김병', hanja_name='金丙')
    daughter, adopted = add(client, bid, '김순', '여', hanja_name='金順'), add(client, bid, '김계', hanja_name='金繼')
    for child, mother in ((older, first), (younger, second), (daughter, second), (adopted, first)):
        link(client, father, child)
        link(client, mother, child)
    for r in client.get(f'/api/books/{bid}').json()['relations']:
        if r['kind'] == 'parent' and r['target_id'] == adopted:
            assert client.put(f"/api/relations/{r['id']}", json={'adopted': True}).status_code == 200
    son_in_law = add(client, bid, '정모', hanja_name='鄭某')
    link(client, daughter, son_in_law, 'spouse')
    return bid


# 1. 내보낸 뒤 새 족보로 불러오면 같습니다.
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


# 1·3. 본처·후처, 자녀의 어머니, 양자가 엑셀과 GEDCOM을 오가도 그대로입니다.
@pytest.mark.parametrize('kind', ['xlsx', 'ged'])
def test_wives_mothers_and_adoption_survive(client, kind):
    account(client)
    bid = remarried_book(client)
    original = client.get(f'/api/books/{bid}').json()
    assert wife_order(original) == {'김갑': ['이씨', '박씨']}
    sent = client.get(f'/api/books/{bid}/export', params={'format': kind}).content
    if kind == 'xlsx':
        tree = x.read_xlsx(sent, x.TREE_SHEET, fallback=False)
        assert x._cell_text(tree[0][0]) == x.CORNER.strip()
        kinds = {x.split_name(next(v for v in row[1:] if isinstance(v, str)))[0]: row[0] for row in tree[1:]}
        assert kinds == {'김갑': '子(아들)', '이씨': '配(본처)', '박씨': '繼配(후처)', '김을': '子(아들)',
                         '김계': '系子(양자)', '김병': '子(아들)', '김순': '女(딸)', '정모': '壻(사위)'}
        for text in ('子', '아들', '子(아들)', '子 (아들)', '子（아들）'):
            assert x.kind_meaning(text) == x.KINDS['子']
        assert x.kind_meaning('子(딸)') is None
    family, back = bring_in(client, f'재혼.{kind}', sent)
    assert signature(back) == signature(original)


# 2. 엑셀 양식은 예시가 채워져 있고, 그대로 불러오면 예시 인물이 남았다고 알립니다.
def test_templates(client):
    account(client)
    sheet = client.get('/api/import/template')
    assert sheet.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(sheet.content)).testzip() is None
    workbook = zipfile.ZipFile(io.BytesIO(sheet.content)).read('xl/workbook.xml').decode()
    assert '가계도' in workbook and '작성 안내' in workbook
    family = x.read_family('가계도 양식.xlsx', sheet.content)
    assert family['errors'] == [] and len(family['people']) == 11
    assert '예시 인물' in family['warnings'][0]
    people = {p['korean_name']: p for p in family['people']}
    key = {p['key']: p['korean_name'] for p in family['people']}
    parents = {(key[a], key[b], adopted) for a, b, adopted in family['parents']}
    assert ('이정숙', '김일남', 0) in parents and ('박영순', '김순', 0) in parents and ('박영순', '김이남', 0) in parents
    assert ('김일남', '김계손', 1) in parents and ('김시조', '김정', 1) in parents
    orders = {tuple(sorted((key[a], key[b]))): order for a, b, order in family['spouses']}
    assert orders[('김시조', '이정숙')] == 1 and orders[('김시조', '박영순')] == 2
    assert people['정재덕']['gender'] == '남' and people['김정']['gender'] == '여'
    guide = x.read_xlsx(sheet.content, x.GUIDE_SHEET, fallback=False)
    text = '\n'.join(x._cell_text(row[0]) for row in guide if row)
    assert '칸을 비우면 족보의 기존 내용이 지워집니다' in text and '① 구분' in text and '⑨ 번호' in text
    ged = client.get('/api/import/template', params={'format': 'ged'})
    family = x.read_family('GEDCOM 양식.ged', ged.content)
    assert family['errors'] == [] and len(family['people']) == 11
    assert sum(adopted for *_, adopted in family['parents']) == 4


def sheets(content):
    names = [x.TREE_SHEET, x.PROGRAM_SHEET]
    return {name: x.read_xlsx(content, name, fallback=False) for name in names}


def rebuild(parts):
    return x.write_xlsx([(name, rows, [12] * 20, (), {'hidden': name == x.PROGRAM_SHEET})
                         for name, rows in parts.items()])


def find_row(rows, text):
    return next(i for i, row in enumerate(rows) if any(isinstance(v, str) and v.startswith(text) for v in row))


# 4~8, 10. 엑셀에서 고친 파일을 원래 족보에 반영합니다.
def test_excel_edits_go_back_into_the_book(client):
    account(client)
    paid(client)
    bid = client.post('/api/books/sample').json()['id']
    parts = sheets(client.get(f'/api/books/{bid}/export', params={'format': 'xlsx'}).content)
    tree = parts[x.TREE_SHEET]
    head = [x._cell_text(v) for v in tree[0]]
    col = {name: head.index(name) for name in x.DETAIL_HEADS}
    # 4. 金道允 아래에 줄을 끼워 새 손주를 적습니다(번호는 비워 둠).
    at = find_row(tree, '金道允')
    new = [None] * len(head)
    new[0] = '子'
    new[next(i for i, v in enumerate(tree[at]) if i and isinstance(v, str))] = '김새손'
    new[col['출생일']] = '2018-04-05'
    tree.insert(at + 1, new)
    # 5. 사망일을 고칩니다.
    tree[find_row(tree, '金志英')][col['사망일']] = '2015-10-13'
    # 6. 사망일 칸을 비웁니다.
    tree[find_row(tree, '金志勳')][col['사망일']] = None
    # 8. 딸의 줄을 동생 金志英 아래로 옮깁니다.
    moved = tree.pop(find_row(tree, '金泰恩'))
    tree.insert(find_row(tree, '姜淑子') + 1, moved)
    # 7. 줄을 지웁니다.
    tree.pop(find_row(tree, '金民瑞'))

    family = client.post('/api/import/preview', files={'file': ('a.xlsx', rebuild(parts))}).json()
    assert family['errors'] == []
    plan = family['target']['plan']
    assert plan['added'] == ['김새손'] and plan['missing'] == ['金民瑞(김민서)']
    assert [c['name'] for c in plan['changed']] == ['金志英(김지영)']
    assert plan['erased'] == [{'name': '金志勳(김지훈)', 'word': '사망일', 'old': '2008-01-17'}]
    assert plan['links_added'] >= 3 and plan['links_removed'] >= 2

    saved = client.post(f'/api/books/{bid}/merge', json=body(family))
    assert saved.status_code == 200 and saved.json()['erased'] == 1
    back = client.get(f'/api/books/{bid}').json()
    people = {p['korean_name']: p for p in back['persons']}
    ids = {k: p['id'] for k, p in people.items()}
    parents = lambda who: {r['source_id'] for r in back['relations'] if r['kind'] == 'parent' and r['target_id'] == ids[who]}
    assert people['김지영']['death_date'] == '2015-10-13'
    assert people['김지훈']['death_date'] == ''
    assert parents('김태은') == {ids['김지영'], ids['강숙자']}
    assert parents('김새손') == {ids['김민재'], ids['이서연']}
    assert '김민서' in ids and parents('김민서') == {ids['김태호'], ids['최미경']}

    # 10. 반영 직전의 백업이 생기고, 다시 읽을 수 있습니다.
    backups = client.get('/api/backups').json()
    assert len(backups) == 1 and backups[0]['title'] == '金海金氏族譜'
    restored = client.post('/api/import/backup', json={'name': backups[0]['name']})
    assert restored.status_code == 200 and len(restored.json()['people']) == 20
    assert client.post('/api/import/backup', json={'name': '../jocbo.db'}).status_code == 404


def test_links_a_tree_cannot_draw_survive_excel(client):
    """배우자의 전혼 자녀, 집안끼리의 혼인처럼 트리로 그릴 수 없는 관계."""
    account(client)
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
    link(client, wife, add(client, bid, '정아', '여'))
    original = client.get(f'/api/books/{bid}').json()
    sent = client.get(f'/api/books/{bid}/export', params={'format': 'xlsx'}).content
    parts = sheets(sent)
    assert any(row and x._cell_text(row[0]) in ('부모-자녀', '배우자') for row in parts[x.PROGRAM_SHEET])
    assert any(isinstance(v, str) and '→ 번호' in v for row in parts[x.TREE_SHEET] for v in row)
    # 위쪽에 빈 줄을 끼워 아래 줄 번호가 모두 밀려도 참조는 그대로입니다.
    parts[x.TREE_SHEET].insert(2, [None] * len(parts[x.TREE_SHEET][0]))
    family, back = bring_in(client, 'b.xlsx', rebuild(parts))
    assert signature(back)[1:3] == signature(original)[1:3]


# 9. 다른 프로그램의 GEDCOM을 기존 족보에 반영합니다.
def test_other_programs_gedcom_into_a_book(client):
    account(client)
    paid(client)
    bid = client.post('/api/books/sample').json()['id']
    second = add(client, bid, '김민재', generation=29)  # 동명이인
    text = ('0 HEAD\n1 SOUR OTHER\n1 CHAR UTF-8\n'
            '0 @I1@ INDI\n1 NAME 지영 /김/\n1 SEX M\n1 DEAT\n2 DATE 13 OCT 2015\n1 FAMS @F1@\n'
            '0 @I2@ INDI\n1 NAME 태준 /김/\n1 SEX M\n1 FAMC @F1@\n'
            '0 @I3@ INDI\n1 NAME 새손 /김/\n1 SEX M\n1 FAMC @F1@\n'
            '0 @I4@ INDI\n1 NAME 민재 /김/\n1 SEX M\n'
            '0 @F1@ FAM\n1 HUSB @I1@\n1 CHIL @I2@\n1 CHIL @I3@\n0 TRLR\n')
    family = client.post('/api/import/preview', files={'file': ('other.ged', text.encode())}).json()
    assert family['errors'] == [] and family['target'] is None
    preview = client.post(f'/api/books/{bid}/merge/preview', json=body(family))
    assert preview.status_code == 200
    plan = preview.json()['plan']
    assert plan['ambiguous'] == ['김민재']
    assert sorted(plan['added']) == ['김민재', '김새손']
    assert [c['name'] for c in plan['changed']] == ['金志英(김지영)'] and plan['erased'] == []
    assert client.post(f'/api/books/{bid}/merge', json=body(family)).status_code == 200
    back = client.get(f'/api/books/{bid}').json()
    people = {p['korean_name']: p for p in back['persons'] if p['id'] != second}
    # 다른 프로그램 파일에 없는 세·본관·기록은 지워지지 않습니다.
    assert people['김지영']['death_date'] == '2015-10-13'
    assert (people['김지영']['generation'], people['김지영']['bon_gwan']) == (27, '金海')
    assert people['김지영']['note'].startswith('字 汝英')
    assert people['김새손']['generation'] == 28


def test_a_file_from_another_book_matches_by_name(client):
    account(client)
    paid(client)
    first = client.post('/api/books/sample').json()['id']
    second = client.post('/api/books/sample').json()['id']
    sent = client.get(f'/api/books/{first}/export', params={'format': 'ged'}).content
    family = client.post('/api/import/preview', files={'file': ('a.ged', sent)}).json()
    assert family['target']['id'] == first
    plan = client.post(f'/api/books/{second}/merge/preview', json=body(family)).json()['plan']
    assert plan['same'] == 20 and not plan['added'] and not plan['changed']


def test_backups_belong_to_their_account(client):
    account(client)
    paid(client)
    bid = client.post('/api/books/sample').json()['id']
    sent = client.get(f'/api/books/{bid}/export', params={'format': 'ged'}).content
    family = client.post('/api/import/preview', files={'file': ('a.ged', sent)}).json()
    assert client.post(f'/api/books/{bid}/merge', json=body(family)).status_code == 200
    name = client.get('/api/backups').json()[0]['name']
    client.post('/api/logout')
    account(client)
    assert client.get('/api/backups').json() == []
    assert client.post('/api/import/backup', json={'name': name}).status_code == 404


# 11. 무료판은 반영으로 20명을 넘을 수 없습니다.
def test_free_account_merge_keeps_the_limit(client):
    account(client)
    bid = client.post('/api/books/sample').json()['id']
    sent = client.get(f'/api/books/{bid}/export', params={'format': 'ged'}).content
    family = client.post('/api/import/preview', files={'file': ('a.ged', sent)}).json()
    family['people'].append({**family['people'][-1], 'key': 'extra', 'id': None, 'korean_name': '한 명 더'})
    assert client.post(f'/api/books/{bid}/merge', json=body(family)).status_code == 402
    assert len(client.get(f'/api/books/{bid}').json()['persons']) == 20
    assert client.get('/api/backups').json() == []


def test_free_account_keeps_its_limit_on_import(client):
    account(client)
    bid = client.post('/api/books/sample').json()['id']
    sent = client.get(f'/api/books/{bid}/export', params={'format': 'ged'}).content
    family = client.post('/api/import/preview', files={'file': ('a.ged', sent)}).json()
    assert client.post('/api/books/import', json=body(family)).status_code == 402
    assert len(client.get('/api/books').json()) == 1


# 12. 내보내기 창의 족보 목록에는 인원이 함께 나옵니다.
def test_book_list_counts_people(client):
    account(client)
    client.post('/api/books/sample')
    client.post('/api/books', json={'title': '빈 족보'})
    assert [(b['title'], b['people']) for b in client.get('/api/books').json()] == [('金海金氏族譜', 20), ('빈 족보', 0)]


# 13. 가족 관계 화면에서 혼인 순서와 입양 여부를 고칩니다.
def test_relation_order_and_adoption(client):
    account(client)
    bid = client.post('/api/books', json={'title': '관계'}).json()['id']
    a, b, c = add(client, bid, '김갑'), add(client, bid, '이씨', '여'), add(client, bid, '김을')
    spouse, parent = link(client, a, b, 'spouse'), link(client, a, c)
    assert client.put(f'/api/relations/{spouse}', json={'marriage_order': 2}).status_code == 200
    assert client.put(f'/api/relations/{parent}', json={'adopted': True}).status_code == 200
    assert client.put(f'/api/relations/{spouse}', json={'adopted': True}).status_code == 400
    assert client.put(f'/api/relations/{parent}', json={'marriage_order': 1}).status_code == 400
    found = {r['id']: r for r in client.get(f'/api/books/{bid}').json()['relations']}
    assert found[spouse]['marriage_order'] == 2 and found[parent]['adopted'] == 1


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
1 FAMS @F2@
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
0 @I4@ INDI
1 NAME 崔氏
1 SEX F
1 FAMS @F2@
0 @I5@ INDI
1 NAME 양자 /박/
1 SEX M
1 FAMC @F2@
2 PEDI adopted
0 @F1@ FAM
1 HUSB @I1@
1 WIFE @I2@
1 CHIL @I3@
1 CHIL @I9@
0 @F2@ FAM
1 HUSB @I1@
1 WIFE @I4@
1 CHIL @I5@
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
    assert sorted(family['parents']) == [['I1', 'I3', 0], ['I1', 'I5', 1], ['I2', 'I3', 0], ['I4', 'I5', 1]]
    assert sorted(family['spouses']) == [['I1', 'I2', 1], ['I1', 'I4', 2]]
    assert (father['generation'], daughter['generation']) == (1, 2)
    assert family['book']['title'] == 'Park family'
    assert any('찾지 못해' in w for w in family['warnings'])
    # 다른 프로그램의 파일: 들어 있는 항목만 "있는 칸"입니다.
    assert set(father['present']) == {'korean_name', 'gender', 'death_date', 'note'}


def test_gedcom_tags_passed_on_by_gramps():
    # Gramps는 모르는 태그를 EVEN + TYPE으로 바꿔 둡니다.
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


def pairs(family):
    return sorted((a, b) for a, b, *_ in family['parents'])


def test_hand_drawn_tree_with_kinds():
    rows = [
        ['세대/구분', '25세', '26세', '세', '출생일', '어머니(아버지)'],
        ['아들', '金甲(김갑)', None, None, 1900.0, None],
        ['본처', '박씨', None, None, None, None],
        ['후처', '최씨', None, None, None, None],
        ['子', None, '김을', None, '1925.3.2', '최씨'],
        ['양자', None, '김병', None, None, '박씨'],
        ['딸', None, '김무', None, 30000.0, '(미상)'],
        ['사위', None, '이서방', None, None, None],
    ]
    family = x.read_family('손으로 그린 가계도.xlsx', rows_to_xlsx(rows))
    assert family['errors'] == []
    people = {p['key']: p for p in family['people']}
    assert (people['r2']['gender'], people['r3']['gender'], people['r8']['gender']) == ('남', '여', '남')
    assert people['r5']['birth_date'] == '1925-03-02' and people['r7']['birth_date'] == '1982-02-18'
    assert ['r2', 'r6', 1] in family['parents'] and ['r3', 'r6', 1] in family['parents']
    assert ('r4', 'r5') in pairs(family) and ('r3', 'r5') not in pairs(family)
    assert [a for a, b in pairs(family) if b == 'r7'] == ['r2']
    assert sorted(family['spouses']) == [['r2', 'r3', 1], ['r2', 'r4', 2], ['r7', 'r8', 1]]
    assert family['book']['title'] == '손으로 그린'


def test_old_layout_still_reads():
    # 2026.11.1~11.6: 구분 열 없이 "配 "를 붙이고, 성별·다른 부모 칸, → 12행 참조.
    rows = [
        ['25세', '26세', '27세', '세', '성별', '출생일', '다른 부모'],
        ['金甲(김갑)', None, None, None, '남', None, None],
        ['配 박씨', None, None, None, '여', None, None],
        ['配 최씨', None, None, None, '여', None, None],
        [None, '김을', None, None, '남', None, '최씨'],
        [None, None, '김정', None, '남', None, None],
        [None, None, '配 최희 → 9행', None, None, None, None],
        [None, '김병', None, None, '남', None, '박씨'],
        [None, None, '최희', None, '여', None, None],
    ]
    family = x.read_family('old.xlsx', rows_to_xlsx(rows))
    assert family['errors'] == []
    assert ('r4', 'r5') in pairs(family) and ('r3', 'r8') in pairs(family)
    assert ['r6', 'r9', 1] in family['spouses']


def test_tree_mistakes_are_named_by_row():
    rows = [
        ['구분', '1세', '2세', '3세'],
        ['子', '김갑', None, None],
        ['子', None, None, '김손'],
        ['配', '이씨', '김을', None],
        ['配', None, '최씨', None],
        ['子', None, '김병 → 번호 40', None],
        ['손자', None, '김정', None],
    ]
    family = x.tree_family(rows)
    joined = '\n'.join(family['errors'])
    for row in ('3행', '4행', '5행', '6행', '7행'):
        assert row in joined
    assert '쓸 수 없는 말' in joined


def test_csv_and_old_excel():
    text = '1세,2세,성별\n김갑,,남\n,김을,남\n'
    family = x.read_family('tree.csv', text.encode('cp949'))
    assert [p['korean_name'] for p in family['people']] == ['김갑', '김을']
    assert family['parents'] == [['r2', 'r3', 0]]
    with pytest.raises(x.ExchangeError, match='xls'):
        x.read_family('old.xls', b'\xd0\xcf\x11\xe0' + b'\0' * 100)
    with pytest.raises(x.ExchangeError):
        x.read_family('photo.png', b'\x89PNG....')


def test_loops_are_refused():
    people = [x.blank_person(k) for k in 'abc']
    with pytest.raises(x.ExchangeError, match='순환'):
        x.settle_generations(people, [('a', 'b'), ('b', 'c'), ('c', 'a')], [])


# 본관은 한자 옆에 한글, 한글 옆에 한자를 괄호로 적고, 다시 불러와도 바뀐 것으로 보지 않습니다.
def test_bongwan_written_with_its_pair():
    assert x.bongwan_cell('金海') == '金海(김해)'
    assert x.bongwan_cell('김해') == '김해(金海)'
    assert x.bongwan_cell('昌寧') == '昌寧(창녕)'
    assert x.bongwan_cell('') == ''
    assert x.bongwan_value('金海(김해)') == '金海'
    assert x.bongwan_value('김해 (金海)') == '김해'
    assert x.same_bongwan('金海', '김해') and x.same_bongwan('金海', '金海(김해)')
    assert not x.same_bongwan('金海', '全州') and not x.same_bongwan('金海', '')


def test_bongwan_in_either_script_comes_back_unchanged(client):
    account(client)
    bid = client.post('/api/books', json={'title': '본관'}).json()['id']
    for name, bon in (('김갑', '金海'), ('김을', '김해')):
        client.post(f'/api/books/{bid}/persons', json={'korean_name': name, 'generation': 1, 'bon_gwan': bon})
    sent = client.get(f'/api/books/{bid}/export', params={'format': 'xlsx'}).content
    cells = {v for row in x.read_xlsx(sent, x.TREE_SHEET, fallback=False) for v in row if isinstance(v, str)}
    assert {'金海(김해)', '김해(金海)'} <= cells
    family = client.post('/api/import/preview', files={'file': ('a.xlsx', sent)}).json()
    plan = client.post(f'/api/books/{bid}/merge/preview', json=body(family)).json()['plan']
    assert plan['changed'] == [] and plan['erased'] == [] and plan['same'] == 2
    assert client.post(f'/api/books/{bid}/merge', json=body(family)).status_code == 200
    kept = {p['korean_name']: p['bon_gwan'] for p in client.get(f'/api/books/{bid}').json()['persons']}
    assert kept == {'김갑': '金海', '김을': '김해'}


# 이름 없이 성에 씨를 붙인 부인도 다른 족보 프로그램에서 성으로 묶이고, 돌아와도 이름이 그대로입니다.
def test_wife_known_by_clan_keeps_her_name_and_gets_a_surname():
    assert x.gedcom_name('崔氏') == ('氏 /崔/', '氏', '崔')
    assert x.gedcom_name('전주최씨') == ('전주최씨', '', '최')
    assert x.gedcom_name('김영조') == ('영조 /김/', '영조', '김')
    for line, name in (('씨 /최/', '최씨'), ('전주최씨 /최/', '전주최씨'), ('全州崔氏 //', '全州崔氏'), ('영조 /김/', '김영조')):
        assert x._name_text({'value': line, 'children': []}) == name
