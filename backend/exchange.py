"""A book carried in and out: GEDCOM for other genealogy programs, an Excel tree for people.

Both directions go through one plain shape, a *family*:

    {'book': {...the book's fields...},
     'people': [{'key', 'korean_name', 'hanja_name', 'bon_gwan', 'generation',
                 'gender', 'birth_date', 'death_date', 'note'}, ...],
     'parents': [[parent_key, child_key], ...],
     'spouses': [[key, key], ...],
     'warnings': [...], 'errors': [...]}

Reading a file gives one back; nothing is filed until it is sent back to be saved,
so a file that is read wrong never leaves half a book behind.

Everything here is the standard library only, so the installed app needs nothing new.
"""
import csv
import io
import json
import re
import zipfile
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

HANJA = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')
HANGUL = re.compile(r'[\uac00-\ud7a3]')
MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
LIMITS = {'korean_name': 100, 'hanja_name': 100, 'bon_gwan': 200, 'note': 10000}
BOOK_LIMITS = {'title': 200, 'clan_name': 200, 'bon_gwan': 200, 'branch_name': 200, 'volume': 50,
               'founder': 200, 'page': 50, 'lineage': 200, 'page_breaks': 200, 'description': 5000}
MAX_PEOPLE = 20000


class ExchangeError(ValueError):
    """A file that cannot be read at all; the message is shown as it stands."""


# ── 날짜 ──────────────────────────────────────────────────────────────

def partial_date(value):
    """A book often knows only part of a date: 1956, 1956-03, 1956-03-02, or --03-02 without a year."""
    whole = re.fullmatch(r'(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?', value)
    yearless = re.fullmatch(r'--(\d{2})-(\d{2})', value)
    if whole:
        year, month, day = whole.groups()
    elif yearless:
        # A leap year, so that 29 February stands when the year is not known.
        year, (month, day) = '2000', yearless.groups()
    else:
        return False
    try:
        date(int(year), int(month or 1), int(day or 1))
    except ValueError:
        return False
    return True


def _ymd(year, month=None, day=None):
    text = f'{int(year):04d}'
    if month:
        text += f'-{int(month):02d}'
        if day:
            text += f'-{int(day):02d}'
    return text


def text_date(value):
    """A date as people type it into a sheet, or None: 1956, 1956-03-02, 1956.3.2, 1956년 3월 2일, 3월 2일."""
    if value is None or value == '':
        return ''
    if isinstance(value, (int, float)):
        number = float(value)
        if 1000 <= number <= 2999 and number == int(number):
            return f'{int(number):04d}'
        # Excel keeps a typed date as days since 1899-12-30.
        if 3000 <= number <= 2958465:
            return (date(1899, 12, 30) + timedelta(days=int(number))).isoformat()
        return None
    text = str(value).strip()
    if not text:
        return ''
    if re.fullmatch(r'--\d{2}-\d{2}', text):
        return text
    found = re.fullmatch(r'(\d{4})(?:\s*[-./년]\s*(\d{1,2})(?:\s*[-./월]\s*(\d{1,2})\s*일?)?\s*월?)?\s*[.년]?', text)
    if found:
        return _ymd(*found.groups())
    found = (re.fullmatch(r'(\d{1,2})\s*월\s*(\d{1,2})\s*일?', text)
             or re.fullmatch(r'(?:미상|\?{2,4}|0000)\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})', text))
    if found:
        return f'--{int(found[1]):02d}-{int(found[2]):02d}'
    return None


def to_gedcom_date(value):
    if not value:
        return ''
    if value.startswith('--'):
        # GEDCOM has no date without a year; a phrase in brackets keeps it.
        return f'({int(value[2:4])}월 {int(value[5:7])}일)'
    parts = value.split('-')
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f'{MONTHS[int(parts[1]) - 1]} {parts[0]}'
    return f'{int(parts[2])} {MONTHS[int(parts[1]) - 1]} {parts[0]}'


def from_gedcom_date(text):
    """Our partial date for an exact GEDCOM date; None for ABT 1850, BET … AND …, other calendars."""
    raw = text.strip()
    found = re.fullmatch(r'\(\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일\s*\)', raw)
    if found:
        return f'--{int(found[1]):02d}-{int(found[2]):02d}'
    upper = re.sub(r'^@#DGREGORIAN@\s*', '', raw.upper())
    found = re.fullmatch(r'(?:(\d{1,2})\s+)?(?:([A-Z]{3})\s+)?(\d{1,4})', upper)
    if not found:
        return None
    day, month, year = found.groups()
    if (day and not month) or (month and month not in MONTHS) or int(year) < 1:
        return None
    return _ymd(year, MONTHS.index(month) + 1 if month else None, day)


def settle_dates(person, where, warnings):
    """Keep only dates the book can hold; anything else is moved into the note, not lost."""
    latest = (date.today() + timedelta(days=1)).isoformat()
    for field, label in (('birth_date', '출생'), ('death_date', '사망')):
        value = person.get(field, '')
        if not value:
            continue
        if not partial_date(value) or (not value.startswith('--') and value > latest[:len(value)]):
            person[field] = ''
            add_note(person, f'{label} {value}')
            warnings.append(f'{where}: {label}일 "{value}"은(는) 날짜로 받을 수 없어 기록(메모)에 옮겼습니다.')
    birth, death = person.get('birth_date', ''), person.get('death_date', '')
    if birth and death and not birth.startswith('--') and not death.startswith('--'):
        known = min(len(birth), len(death))
        if birth[:known] > death[:known]:
            person['death_date'] = ''
            add_note(person, f'사망 {death}')
            warnings.append(f'{where}: 사망일이 출생일보다 빨라 사망일을 기록(메모)에 옮겼습니다.')


def add_note(person, line):
    person['note'] = (person.get('note', '') + '\n' + line).strip('\n') if line else person.get('note', '')


# ── 이름 ──────────────────────────────────────────────────────────────

# A surname reads as a surname, and the given name takes the initial-sound rule:
# the same two corrections the page makes (frontend/app.js readingOf).
HANJA_SURNAME = {'金': '김', '李': '이', '柳': '유', '劉': '유', '羅': '나', '盧': '노', '梁': '양', '林': '임',
                 '呂': '여', '龍': '용', '廉': '염', '雷': '뇌', '陸': '육', '陰': '음'}
INITIAL_SOUND = {'라': '나', '래': '내', '로': '노', '뢰': '뇌', '루': '누', '르': '느', '리': '이', '량': '양',
                 '려': '여', '력': '역', '련': '연', '렬': '열', '렴': '염', '령': '영', '례': '예', '룡': '용',
                 '류': '유', '륙': '육', '륜': '윤', '률': '율', '름': '늠', '릉': '능', '림': '임', '립': '입',
                 '녀': '여', '뇨': '요', '뉴': '유', '니': '이', '냑': '약', '녕': '영'}
_readings = None


def _reading_table():
    global _readings
    if _readings is None:
        try:
            path = Path(__file__).resolve().parents[1] / 'frontend' / 'hanjaeum.json'
            _readings = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            _readings = {}
    return _readings


def hangul_of(text):
    """金永祖 → 김영조, for a name that came in hanja only."""
    chars, out, given = list(text), [], -1
    for index, ch in enumerate(chars):
        if not HANJA.match(ch):
            out.append(ch)
            continue
        after = chars[index + 1] if index + 1 < len(chars) else ''
        if ch in HANJA_SURNAME and (index == 0 or not HANJA.match(chars[index - 1]) or after == '氏'):
            if after != '氏':
                given = index + 1
            out.append(HANJA_SURNAME[ch])
            continue
        reading = re.split(r'[,/\s]+', _reading_table().get(ch, ''))[0]
        if not reading:
            out.append(ch)
            continue
        if index in (0, given) and reading in INITIAL_SOUND:
            reading = INITIAL_SOUND[reading]
        out.append(reading)
    return ''.join(out)


# 흔한 본관의 한자와 한글. 같은 한글에 한자가 여럿이면 앞의 것을 씁니다.
BONGWAN = dict(pair.split(':') for pair in (
    '金海:김해 密陽:밀양 全州:전주 慶州:경주 晉州:진주 晋州:진주 安東:안동 光山:광산 坡平:파평 南陽:남양 '
    '淸州:청주 清州:청주 延安:연안 昌寧:창녕 豊山:풍산 豐山:풍산 驪興:여흥 靑松:청송 青松:청송 東萊:동래 '
    '尙州:상주 尚州:상주 天安:천안 晉陽:진양 淸道:청도 清道:청도 潘南:반남 瑞興:서흥 金寧:김녕 全義:전의 '
    '平山:평산 海州:해주 順興:순흥 漢陽:한양 光州:광주 羅州:나주 文化:문화 原州:원주 驪州:여주 水原:수원 '
    '仁同:인동 星州:성주 義城:의성 陜川:합천 咸安:함안 咸陽:함양 咸從:함종 慶山:경산 達城:달성 大邱:대구 '
    '草溪:초계 宜寧:의령 寧越:영월 寧海:영해 礪山:여산 長興:장흥 長水:장수 濟州:제주 高靈:고령 恩津:은진 '
    '德水:덕수 杞溪:기계 交河:교하 豐壤:풍양 豊壤:풍양 楊州:양주 開城:개성 南原:남원 海南:해남 靈光:영광 '
    '牙山:아산 溫陽:온양 善山:선산 一善:일선 仁川:인천 江陵:강릉 三陟:삼척 平海:평해 蔚山:울산 固城:고성 '
    '河東:하동 昌原:창원 金浦:김포 鎭川:진천 忠州:충주 公州:공주 扶安:부안 潭陽:담양 寶城:보성 竹山:죽산 '
    '驪陽:여양 載寧:재령 平壤:평양 延日:연일 迎日:영일 興德:흥덕 淸風:청풍 丹陽:단양 安城:안성 利川:이천 '
    '新平:신평 長淵:장연 谷城:곡성 南平:남평 綾城:능성 和順:화순 光陽:광양 豐川:풍천 豊川:풍천 鐵原:철원 '
    '碧珍:벽진 錦山:금산 瑞山:서산 洪州:홍주 結城:결성 白川:백천 密城:밀성 文義:문의 求禮:구례 平昌:평창 '
    '玄風:현풍 咸平:함평 長城:장성 靈山:영산 慶源:경원 晉山:진산 宜春:의춘 高興:고흥 康津:강진 靈巖:영암 '
    '務安:무안 珍島:진도 寧山:영산 原城:원성 江華:강화 坡州:파주 驪江:여강 林川:임천 韓山:한산 舒川:서천 '
    '扶餘:부여 禮山:예산 唐津:당진 沔川:면천 洪城:홍성 保寧:보령 藍浦:남포 鴻山:홍산 恩山:은산 連山:연산 '
    '慶興:경흥 安岳:안악 遂安:수안 谷山:곡산 祥原:상원 中和:중화 順天:순천 麗水:여수 樂安:낙안 興陽:흥양 '
    '靈巖:영암 長澤:장택 晉原:진원 茂長:무장 高敞:고창 井邑:정읍 泰仁:태인 益山:익산 沃川:옥천 報恩:보은 '
    '永同:영동 黃澗:황간 淸安:청안 槐山:괴산 延豐:연풍 堤川:제천 寧川:영천 永川:영천 榮川:영천 醴泉:예천 '
    '奉化:봉화 榮州:영주 順天:순천 聞慶:문경 咸昌:함창 開寧:개령 金山:김산 漆原:칠원 居昌:거창 安陰:안음 '
    '晉陽:진양 泗川:사천 南海:남해 巨濟:거제 熊川:웅천 金堤:김제 萬頃:만경 臨陂:임피 沃溝:옥구').split())
BONGWAN_HANJA = {}
for _hanja, _hangul in BONGWAN.items():
    BONGWAN_HANJA.setdefault(_hangul, _hanja)


def bongwan_cell(text):
    """본관을 엑셀 칸에 적는 모양: 한자는 金海(김해), 한글은 김해(金海). 짝을 모르면 그대로."""
    text = (text or '').strip()
    if not text or '(' in text or '（' in text:
        return text
    if HANJA.search(text) and not HANGUL.search(text):
        reading = BONGWAN.get(text) or hangul_of(text)
        return f'{text}({reading})' if reading and reading != text and not HANJA.search(reading) else text
    if HANGUL.search(text) and not HANJA.search(text) and text in BONGWAN_HANJA:
        return f'{text}({BONGWAN_HANJA[text]})'
    return text


def sheet_date(value):
    """엑셀 칸에 적는 날짜. 연도를 모르는 --09-19는 다른 날짜와 같은 모양으로 미상-09-19라고 적습니다."""
    found = re.fullmatch(r'--(\d{2})-(\d{2})', value or '')
    return f'미상-{found[1]}-{found[2]}' if found else value


def bongwan_value(text):
    """엑셀 칸의 金海(김해)·김해(金海) → 저장할 본관(괄호 앞의 말)."""
    text = re.sub(r'\s+', ' ', text or '').strip()
    found = re.fullmatch(r'(.+?)\s*[(（]\s*(.*?)\s*[)）]', text)
    return found[1] if found else text


def same_bongwan(a, b):
    """金海, 김해, 金海(김해)처럼 적는 모양만 다르고 같은 본관인가."""
    def forms(text):
        text = (text or '').strip()
        found = re.fullmatch(r'(.+?)\s*[(（]\s*(.*?)\s*[)）]', text)
        words = {found[1], found[2]} if found else {text}
        out = set()
        for word in words:
            out |= {word, BONGWAN.get(word, ''), BONGWAN_HANJA.get(word, '')}
            if HANJA.search(word) and not HANGUL.search(word):
                out.add(hangul_of(word))
        return out - {''}
    a, b = (a or '').strip(), (b or '').strip()
    return a == b or (bool(a) and bool(b) and bool(forms(a) & forms(b)))


def split_name(text):
    """'金永祖(김영조)', '김영조(金永祖)', '김영조' or '金永祖' → (한글명, 한자명)."""
    text = re.sub(r'\s+', ' ', str(text)).strip()
    found = re.fullmatch(r'(.+?)\s*[(（]\s*(.+?)\s*[)）]', text)
    parts = [found[1], found[2]] if found else [text]
    korean = hanja = ''
    for part in parts:
        if HANJA.search(part) and not HANGUL.search(part):
            hanja = hanja or part
        else:
            korean = korean or part
    if not korean and hanja:
        korean = hangul_of(hanja)
    return korean, hanja


def label(person):
    """How a person is written in a tree cell: 金永祖(김영조), or the hangul alone."""
    hanja, korean = person.get('hanja_name', ''), person.get('korean_name', '')
    return f'{hanja}({korean})' if hanja and hanja != korean else korean


def fit(person, where, warnings):
    for field, limit in LIMITS.items():
        value = person.get(field, '')
        if len(value) > limit:
            person[field] = value[:limit]
            warnings.append(f'{where}: {FIELD_NAMES[field]}이(가) {limit}자를 넘어 뒷부분을 잘랐습니다.')
    if not person.get('korean_name'):
        person['korean_name'] = '이름 미상'
        warnings.append(f'{where}: 이름이 없어 "이름 미상"으로 적었습니다.')


FIELD_NAMES = {'korean_name': '한글명', 'hanja_name': '한자명', 'bon_gwan': '본관', 'note': '기록'}


def blank_person(key):
    # id: 파일을 내보낸 족보 안의 사람 번호(파일에 있을 때).
    # present: 파일에 실제로 있는 칸. None이면 모든 칸이 있는 것으로 봅니다.
    #   반영할 때 있는 칸이 비어 있으면 지우고, 없는 칸은 건드리지 않습니다.
    return {'key': key, 'id': None, 'korean_name': '', 'hanja_name': '', 'bon_gwan': '', 'generation': None,
            'gender': '미상', 'birth_date': '', 'death_date': '', 'note': '', 'present': None}


def person_number(value):
    text = _cell_text(value) if not isinstance(value, str) else value.strip()
    return int(text) if re.fullmatch(r'\d{1,12}', text or '') else None


# ── 기존 족보에 반영 ──────────────────────────────────────────────────

PERSON_FIELDS = [('korean_name', '한글명'), ('hanja_name', '한자명'), ('bon_gwan', '본관'), ('generation', '세'),
                 ('gender', '성별'), ('birth_date', '출생일'), ('death_date', '사망일'), ('note', '기록')]


def _names(person):
    return {person.get('korean_name') or '', person.get('hanja_name') or ''} - {''}


def match_people(book, family, by_number):
    """파일의 사람과 족보의 사람을 짝짓습니다. {파일 key: 족보 번호}, 동명이인 이름 목록.

    by_number: 이 족보에서 내보낸 파일이면 번호로만 짝짓습니다. 번호가 없는 줄은 새로 끼운
    사람입니다. 다른 파일이면 이름(한글명·한자명)과 세로 찾고, 여럿이면 부모 이름까지 봅니다.
    """
    current = {p['id']: p for p in book['persons']}
    matched, used, ambiguous = {}, set(), []
    if by_number:
        for person in family['people']:
            number = person.get('id')
            if number in current and number not in used:
                matched[person['key']] = number
                used.add(number)
        return matched, ambiguous
    by_name = defaultdict(set)
    for p in book['persons']:
        for name in _names(p):
            by_name[name].add(p['id'])
    book_parents = defaultdict(set)
    for r in book['relations']:
        if r['kind'] == 'parent' and r['source_id'] in current:
            book_parents[r['target_id']].add(r['source_id'])
    in_file = {p['key']: p for p in family['people']}
    file_parents = defaultdict(set)
    for parent, child, *_ in family['parents']:
        file_parents[child].add(parent)
    for person in family['people']:
        found = {number for name in _names(person) for number in by_name.get(name, ())} - used
        present = person.get('present')
        if present is None or 'generation' in present:
            found = {number for number in found if current[number]['generation'] == person['generation']}
        if len(found) > 1:
            names = {name for key in file_parents[person['key']] for name in _names(in_file[key])}
            if names:
                found = {number for number in found
                         if names & {name for parent in book_parents[number] for name in _names(current[parent])}}
        if len(found) == 1:
            number = found.pop()
            matched[person['key']] = number
            used.add(number)
        elif len(found) > 1:
            ambiguous.append(label(person))
    return matched, ambiguous


def merge_plan(book, family, by_number=True):
    """파일을 기존 족보에 반영하면 무엇이 바뀌는지.

    같은 내용은 그대로 두고, 다른 내용은 파일대로 고치며, 파일에 있는 칸이 비어 있으면
    족보의 내용도 지웁니다(erased). 파일에 그 칸 자체가 없으면(present에 없으면) 건드리지
    않습니다. 족보에 없는 사람은 추가하고, 파일에 없는 사람은 지우지 않고 이름만 알립니다.
    파일에 있는 사람끼리의 부모·배우자 관계는 파일대로 맞춥니다.
    """
    current = {p['id']: p for p in book['persons']}
    matched, ambiguous = match_people(book, family, by_number)
    added, changed, erased, same = [], [], [], 0
    for person in family['people']:
        if person['key'] not in matched:
            added.append(label(person))
            continue
        old = current[matched[person['key']]]
        present = person.get('present')
        fields = []
        for field, word in PERSON_FIELDS:
            if present is not None and field not in present:
                continue
            before = old[field] if old[field] is not None else ''
            after = person[field] if person[field] is not None else ''
            # 성별 '미상'은 모른다는 뜻이지 지우라는 뜻이 아닙니다.
            if before == after or (field == 'gender' and after == '미상') or (field == 'bon_gwan' and same_bongwan(before, after)):
                continue
            if after == '':
                erased.append({'name': label(old), 'word': word, 'old': before})
            else:
                fields.append([word, before, after])
        if fields:
            changed.append({'name': label(old), 'fields': fields})
        elif not any(e['name'] == label(old) for e in erased):
            same += 1
    inside = set(matched.values())
    missing = [label(p) for number, p in current.items() if number not in inside]

    def link(kind, a, b):
        return (kind, *sorted((a, b))) if kind == 'spouse' else (kind, a, b)

    before = {link(r['kind'], r['source_id'], r['target_id']) for r in book['relations']
              if r['source_id'] in inside and r['target_id'] in inside}
    after = {link(kind, matched[a], matched[b]) for kind, pairs in (('parent', family['parents']), ('spouse', family['spouses']))
             for a, b, *_ in pairs if a in matched and b in matched}
    new_people_links = sum(1 for pairs in (family['parents'], family['spouses']) for a, b, *_ in pairs
                           if a not in matched or b not in matched)
    return {'matched': matched, 'added': added, 'changed': changed, 'erased': erased, 'same': same,
            'missing': missing, 'ambiguous': ambiguous,
            'links_added': len(after - before) + new_people_links, 'links_removed': len(before - after)}


GENDER = {'남': '남', '男': '남', 'M': '남', 'MALE': '남', '여': '여', '女': '여', 'F': '여', 'FEMALE': '여'}


# ── 세대 ──────────────────────────────────────────────────────────────

def tangles(keys, parents, spouses):
    """The links that keep the family from being laid out in 世, as (parent links, spouse links).

    A child must stand below its parents and a couple side by side, so a loop of
    such links (someone married to their own child, a person their own forebear)
    cannot be drawn. Only the people caught in such a loop are looked at again:
    their parent links are put back first, then their marriages, and a link that
    would close a loop is left out. Returns empty lists when nothing is wrong.
    """
    keys = list(keys)
    root = {k: k for k in keys}

    def find(k):
        while root[k] != k:
            root[k] = root[root[k]]
            k = root[k]
        return k

    for one, other, *_ in spouses:
        if one in root and other in root:
            root[find(one)] = find(other)
    # 부부를 한 덩어리로 묶고, 부모 → 자녀를 덩어리 사이의 화살표로 봅니다.
    arrows, looped = defaultdict(set), set()
    for parent, child, *_ in parents:
        if parent in root and child in root:
            a, b = find(parent), find(child)
            if a == b:
                looped.add(a)
            else:
                arrows[a].add(b)
    # 서로 이어져 도는 덩어리들(강연결요소)을 찾습니다.
    index, low, on, stack, counter = {}, {}, set(), [], [0]
    groups = {find(k) for k in keys}
    for start in groups:
        if start in index:
            continue
        work = [(start, iter(arrows[start]))]
        index[start] = low[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on.add(start)
        while work:
            node, rest = work[-1]
            nxt = next(rest, None)
            if nxt is not None:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter[0]
                    counter[0] += 1
                    stack.append(nxt)
                    on.add(nxt)
                    work.append((nxt, iter(arrows[nxt])))
                elif nxt in on:
                    low[node] = min(low[node], index[nxt])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                part = []
                while True:
                    top = stack.pop()
                    on.discard(top)
                    part.append(top)
                    if top == node:
                        break
                if len(part) > 1:
                    looped.update(part)
    caught = {k for k in keys if find(k) in looped}
    if not caught:
        return [], []
    # 걸린 사람들 사이의 관계만 다시 이어 봅니다. 부모-자녀를 먼저, 혼인을 나중에.
    kids, mates = defaultdict(list), defaultdict(list)

    def reaches(start, goal, need_parent):
        """start에서 goal까지 (부모 → 자녀, 배우자 양쪽으로) 갈 수 있는가. need_parent면 부모-자녀를 한 번은 거쳐야 합니다."""
        seen = {(start, False)}
        todo = [(start, False)]
        while todo:
            node, crossed = todo.pop()
            if node == goal and (crossed or not need_parent):
                return True
            for nxt, step in [(c, True) for c in kids[node]] + [(m, False) for m in mates[node]]:
                state = (nxt, crossed or step)
                if state not in seen:
                    seen.add(state)
                    todo.append(state)
        return False

    left_parents, left_spouses = [], []
    for link in parents:
        parent, child = link[0], link[1]
        if parent not in caught or child not in caught:
            continue
        if reaches(child, parent, False):
            left_parents.append(link)
        else:
            kids[parent].append(child)
    for link in spouses:
        one, other = link[0], link[1]
        if one not in caught or other not in caught:
            continue
        if reaches(one, other, True) or reaches(other, one, True):
            left_spouses.append(link)
        else:
            mates[one].append(other)
            mates[other].append(one)
    return left_parents, left_spouses


def who(person, key):
    """A person named in a message: the name, and where to find them in the file."""
    name = label(person) if person else ''
    place = f'{key[1:]}행' if re.fullmatch(r'r\d+', key) else key
    return f'{name}({place})' if name else place


def link_text(kind, a, b, by_key):
    if kind == 'parent':
        return f'{who(by_key.get(a), a)} → 자녀 {who(by_key.get(b), b)}'
    return f'{who(by_key.get(a), a)} ↔ 배우자 {who(by_key.get(b), b)}'


def tangle_text(people, parents, spouses, limit=5):
    """Name the links caught in a loop, for an error message."""
    by_key = {p['key']: p for p in people}
    left_parents, left_spouses = tangles(by_key, parents, spouses)
    found = [link_text('parent', l[0], l[1], by_key) for l in left_parents] + \
            [link_text('spouse', l[0], l[1], by_key) for l in left_spouses]
    if not found:
        return ''
    more = f' 외 {len(found) - limit}건' if len(found) > limit else ''
    return ' 맞지 않는 관계: ' + ', '.join(found[:limit]) + more + '.'


def settle_generations(people, parents, spouses, base=1):
    """Give everyone a 世: the one written down where there is one, else from the family.

    A child stands at least one below each parent and husband and wife stand
    together, as the page itself draws them. A parent line that loops back on
    itself, or one that cannot be laid out, is an error that names the links.
    """
    keys = [p['key'] for p in people]
    gen = {p['key']: p.get('generation') for p in people}
    children = defaultdict(list)
    has_parent = set()
    for parent, child, *_ in parents:
        children[parent].append(child)
        has_parent.add(child)
    # Parent loops first: no 世 can be given to someone who is their own forebear.
    state = {}
    for start in keys:
        if start in state:
            continue
        stack = [(start, iter(children[start]))]
        state[start] = 1
        while stack:
            node, rest = stack[-1]
            nxt = next(rest, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
            elif state.get(nxt) == 1:
                raise ExchangeError('부모-자녀 관계가 순환합니다. 어떤 사람이 자기 조상으로 이어져 있습니다.'
                                    + tangle_text(people, parents, spouses))
            elif nxt not in state:
                state[nxt] = 1
                stack.append((nxt, iter(children[nxt])))
    while any(value is None for value in gen.values()):
        changed = True
        while changed:
            changed = False
            for parent, child, *_ in parents:
                if gen[parent] is not None and gen[child] is None:
                    gen[child], changed = gen[parent] + 1, True
                elif gen[child] is not None and gen[parent] is None:
                    gen[parent], changed = gen[child] - 1, True
            for one, other, *_ in spouses:
                if gen[one] is None and gen[other] is not None:
                    gen[one], changed = gen[other], True
                elif gen[other] is None and gen[one] is not None:
                    gen[other], changed = gen[one], True
        unknown = [key for key in keys if gen[key] is None]
        if unknown:
            first = next((key for key in unknown if key not in has_parent), unknown[0])
            gen[first] = base
    for _ in range(len(keys) + 2):
        changed = False
        for parent, child, *_ in parents:
            if gen[child] < gen[parent] + 1:
                gen[child], changed = gen[parent] + 1, True
        for one, other, *_ in spouses:
            if gen[one] != gen[other]:
                gen[one] = gen[other] = max(gen[one], gen[other])
                changed = True
        if not changed:
            break
    else:
        raise ExchangeError('세대를 맞출 수 없습니다. 부부 관계와 부모 관계가 서로 맞지 않는 사람이 있습니다.'
                            + tangle_text(people, parents, spouses))
    lowest = min(gen.values(), default=1)
    if lowest < 1:
        gen = {key: value + 1 - lowest for key, value in gen.items()}
    if max(gen.values(), default=1) > 200:
        raise ExchangeError('세대가 200을 넘습니다. 세(世) 칸이나 들여쓰기를 확인해 주십시오.')
    for person in people:
        person['generation'] = gen[person['key']]


def finish(family):
    """Common last step of every reader: tidy the links, give 世, and check size."""
    keys = {p['key'] for p in family['people']}
    # 부모-자녀: [부모, 자녀, 입양 여부 0/1]. 배우자: [한 사람, 다른 사람, 혼인 순서(0은 모름)].
    parents = {}
    for parent, child, *rest in family['parents']:
        if parent in keys and child in keys and parent != child:
            adopted = int(bool(rest and rest[0]))
            parents[(parent, child)] = max(parents.get((parent, child), 0), adopted)
    spouses = {}
    for one, other, *rest in family['spouses']:
        if one in keys and other in keys and one != other:
            pair = tuple(sorted((one, other)))
            order = int(rest[0]) if rest and rest[0] else 0
            if pair not in spouses or (not spouses[pair] and order):
                spouses[pair] = order
    family['parents'] = [[a, b, adopted] for (a, b), adopted in parents.items()]
    family['spouses'] = [[a, b, order] for (a, b), order in spouses.items()]
    parents, spouses = family['parents'], family['spouses']
    if not family['people'] and not family['errors']:
        family['errors'].append('불러올 사람이 없습니다.')
    if len(family['people']) > MAX_PEOPLE:
        family['errors'].append(f'한 번에 {MAX_PEOPLE}명까지 불러올 수 있습니다.')
    if not family['errors']:
        try:
            settle_generations(family['people'], parents, spouses)
        except ExchangeError:
            # 옛 족보는 빠진 쪽, 잘못 옮겨 적은 곳이 흔합니다. 파일을 거부하지 않고, 세대가 서로
            # 맞지 않는 관계만 빼고 불러온 뒤, 누구의 어떤 관계를 뺐는지 알리고 기록 칸에도 적어 둡니다.
            set_aside(family)
            try:
                settle_generations(family['people'], family['parents'], family['spouses'])
            except ExchangeError as error:
                family['errors'].append(str(error))
    family['book'] = tidy_book(family['book'])
    return family


SET_ASIDE = '불러올 때 뺀 관계'


def set_aside(family):
    """Leave out the links that cannot be laid out in 世, and say which (warnings and each person's note)."""
    by_key = {p['key']: p for p in family['people']}
    left_parents, left_spouses = tangles(by_key, family['parents'], family['spouses'])
    if not left_parents and not left_spouses:
        return
    out_p = {(l[0], l[1]) for l in left_parents}
    out_s = {(l[0], l[1]) for l in left_spouses}
    family['parents'] = [l for l in family['parents'] if (l[0], l[1]) not in out_p]
    family['spouses'] = [l for l in family['spouses'] if (l[0], l[1]) not in out_s]
    lines = []
    for kind, links in (('parent', left_parents), ('spouse', left_spouses)):
        for a, b, *_ in links:
            lines.append(link_text(kind, a, b, by_key))
            one, other = by_key[a], by_key[b]
            if kind == 'parent':
                add_note(one, f'[{SET_ASIDE}] 자녀 {label(other)}')
                add_note(other, f'[{SET_ASIDE}] 부모 {label(one)}')
            else:
                add_note(one, f'[{SET_ASIDE}] 배우자 {label(other)}')
                add_note(other, f'[{SET_ASIDE}] 배우자 {label(one)}')
    for person in (by_key[k] for l in left_parents + left_spouses for k in l[:2]):
        if person.get('present') is not None and 'note' not in person['present']:
            person['present'].append('note')
        person['note'] = person['note'][:LIMITS['note']]
    head = (f'세대가 서로 맞지 않는 관계 {len(lines)}건은 빼고 불러옵니다. 자녀가 부모보다 아래 세대가 아니거나, '
            f'부부가 서로 다른 세대가 되는 관계입니다. 해당 인물의 기록 칸에 "[{SET_ASIDE}]"로 적어 두었으니, '
            '불러온 뒤 족보 원본과 맞춰 관계를 다시 이어 주십시오.')
    family['warnings'][:0] = [head] + [f'뺀 관계: {line}' for line in lines]


def tidy_book(book):
    """Every field of a book, each within its length, with a title and a volume."""
    book = {field: str(book.get(field, '') or '').strip()[:limit] for field, limit in BOOK_LIMITS.items()}
    book['title'] = book['title'] or '불러온 족보'
    book['volume'] = book['volume'] or '1'
    return book


def in_marriage_order(links):
    """한 사람의 혼인들을 순서대로. links: [(배우자 관계, 무엇이든), …].

    혼인 순서(marriage_order)를 정한 것은 그 순서를, 정하지 않은 것(0)은 그 사람의 배우자
    가운데 등록한 순서를 씁니다. 그래서 첫 부인은 그대로 두고 둘째만 2로 정해도 맞게 섭니다.
    """
    by_id = sorted(links, key=lambda item: item[0].get('id') or 0)
    rank = [((item[0].get('marriage_order') or index), item[0].get('id') or 0, item)
            for index, item in enumerate(by_id, start=1)]
    return [item for _, _, item in sorted(rank, key=lambda r: (r[0], r[1]))]


# ── 가계도 줄 세우기 (내보내기) ─────────────────────────────────────

def lay_out(book):
    """The tree as rows, the way the page draws it.

    Each marriage has one lineage member (the host) and the one who married in
    (the guest), chosen as the page chooses (frontend/app.js spouseHosts): who has
    parents in the book, then whose surname is the clan's. A guest stands on the
    row after the host, children below, sons before daughters and eldest first.
    Someone already written elsewhere gets a row that points to theirs.
    """
    people = book['persons']
    by_id = {p['id']: p for p in people}
    parents_of, children_of, spouses_of = defaultdict(list), defaultdict(list), defaultdict(list)
    for r in book['relations']:
        if r['source_id'] not in by_id or r['target_id'] not in by_id:
            continue
        if r['kind'] == 'parent':
            parents_of[r['target_id']].append(r['source_id'])
            children_of[r['source_id']].append(r['target_id'])
        else:
            spouses_of[r['source_id']].append(r['target_id'])
            spouses_of[r['target_id']].append(r['source_id'])
    clan = re.sub(r'[氏씨\s]', '', book.get('clan_name') or '')
    hanja_surname = clan[0] if clan and HANJA.match(clan[0]) else ''
    korean_surname = clan[0] if clan and HANGUL.match(clan[0]) else ''

    def score(p):
        value = 4 if parents_of[p['id']] else 0
        if hanja_surname and (p['hanja_name'] or '')[:1] == hanja_surname:
            value += 2
        if korean_surname and (p['korean_name'] or '')[:1] == korean_surname:
            value += 2
        return value

    married, host_of = defaultdict(list), {}
    spouse_links = [r for r in book['relations']
                    if r['kind'] == 'spouse' and r['source_id'] in by_id and r['target_id'] in by_id]
    for r in spouse_links:
        a, b = by_id[r['source_id']], by_id[r['target_id']]
        sa, sb = score(a), score(b)
        host, guest = (a, b) if (sa > sb or (sa == sb and a['id'] < b['id'])) else (b, a)
        married[host['id']].append((r, guest['id']))
        host_of[guest['id']] = host['id']
    for host, links in married.items():
        married[host] = [guest for _, guest in in_marriage_order(links)]
    adopted = {r['target_id'] for r in book['relations'] if r['kind'] == 'parent' and r.get('adopted')}

    def clan_kind(pid):
        gender = by_id[pid]['gender']
        if pid in adopted:
            return {'남': '系子', '여': '養女'}.get(gender, '系子')
        return {'남': '子', '여': '女'}.get(gender, '')

    def guest_kind(guest, host, index):
        gender = by_id[guest]['gender']
        if gender == '여' or (gender == '미상' and by_id[host]['gender'] != '여'):
            return '配' if index == 0 else '繼配'
        return '壻'

    rank = {'남': 0, '미상': 1, '여': 2}

    def sibling_key(pid):
        p = by_id[pid]
        born = p['birth_date'] if re.match(r'\d{4}', p['birth_date'] or '') else '9999'
        return (rank.get(p['gender'], 1), born, pid)

    rows, placed = [], set()

    def walk(pid):
        # Depth first, on a list rather than by recursion, so 200 世 cannot overflow.
        work = [(pid, 0, None, False)]
        while work:
            node, depth, other, is_ref = work.pop()
            if is_ref or node in placed:
                rows.append({'kind': 'child-ref', 'pid': node, 'depth': depth, 'other': other, 'gubun': clan_kind(node)})
                continue
            placed.add(node)
            rows.append({'kind': 'person', 'pid': node, 'depth': depth, 'other': other, 'gubun': clan_kind(node)})
            mates = [m for m in married.get(node, []) if m != node]
            for index, mate in enumerate(mates):
                gubun = guest_kind(mate, node, index)
                if mate in placed:
                    rows.append({'kind': 'spouse-ref', 'pid': mate, 'depth': depth, 'gubun': gubun})
                else:
                    placed.add(mate)
                    rows.append({'kind': 'spouse', 'pid': mate, 'depth': depth, 'gubun': gubun})
            pending = []
            for child in sorted(set(children_of[node]), key=sibling_key):
                # 다른 부모 is written only where it is needed: with two or more
                # spouses, which one; with one spouse who is not this child's
                # parent, (미상). With one spouse who is, the cell stays empty, so
                # a child row moved under a brother takes his wife as its mother.
                mate = next((m for m in parents_of[child] if m in mates), None)
                if mate is not None:
                    other_parent = mate if len(mates) > 1 else None
                else:
                    other_parent = '(미상)' if mates else None
                guest_elsewhere = child in host_of and host_of[child] != node
                pending.append((child, depth + 1, other_parent, guest_elsewhere))
            work.extend(reversed(pending))

    roots = [p['id'] for p in people if not parents_of[p['id']] and p['id'] not in host_of]
    roots.sort(key=lambda pid: (by_id[pid]['generation'], sibling_key(pid)))
    for pid in roots:
        if pid not in placed:
            walk(pid)
    # Whatever no root reached (a loop, or a child of a guest alone) still gets a row.
    for p in sorted(people, key=lambda p: (p['generation'], p['id'])):
        if p['id'] not in placed:
            target = host_of.get(p['id'])
            walk(target if target is not None and target not in placed else p['id'])
    return rows, by_id, parents_of, spouses_of


# ── xlsx 쓰기 ─────────────────────────────────────────────────────────

_BAD_XML = re.compile('[\x00-\x08\x0b\x0c\x0e-\x1f]')


def column_name(index):
    name = ''
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def column_index(name):
    index = 0
    for ch in name:
        index = index * 26 + ord(ch) - 64
    return index - 1


# 셀 모양. gfill·gref: 부인·사위 줄(옅은 회색 바탕), corner: 대각선을 그은 "세대/구분" 칸,
# warn: 붉은 굵은 경고 글씨, title: 큰 굵은 제목.
STYLE = {'plain': 0, 'head': 1, 'text': 2, 'guest': 3, 'ref': 4, 'gfill': 5, 'gref': 6, 'corner': 7,
         'warn': 8, 'title': 9, 'gnum': 10, 'colhead': 11, 'kind': 12, 'gkind': 13, 'num': 14,
         'b_text': 15, 'b_ref': 16, 'b_gfill': 17, 'b_gref': 18, 'b_gnum': 19, 'b_kind': 20, 'b_gkind': 21, 'b_num': 22}


def _sheet_xml(rows, widths, text_columns=(), heights=None, freeze=1):
    pane = (f'<pane ySplit="{freeze}" topLeftCell="A{freeze + 1}" activePane="bottomLeft" state="frozen"/>'
            if freeze else '')
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           f'<sheetViews><sheetView workbookViewId="0">{pane}</sheetView></sheetViews>'
           '<sheetFormatPr defaultRowHeight="18"/><cols>']
    for index, width in enumerate(widths):
        # Date columns stay text, so a date typed in later is not turned into a number.
        style = f' style="{STYLE["text"]}"' if index in text_columns else ''
        out.append(f'<col min="{index + 1}" max="{index + 1}" width="{width}" customWidth="1"{style}/>')
    out.append('</cols><sheetData>')
    for r, row in enumerate(rows, start=1):
        height = (heights or {}).get(r)
        out.append(f'<row r="{r}" ht="{height}" customHeight="1">' if height else f'<row r="{r}">')
        for c, cell in enumerate(row):
            if cell is None:
                continue
            value, style = cell if isinstance(cell, tuple) else (cell, 'plain')
            ref = f'{column_name(c)}{r}'
            if value is None or value == '':
                # 빈 칸도 모양(회색 바탕)은 남깁니다.
                if isinstance(cell, tuple) and style != 'plain':
                    out.append(f'<c r="{ref}" s="{STYLE[style]}"/>')
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out.append(f'<c r="{ref}" s="{STYLE[style]}"><v>{value}</v></c>')
            else:
                text = escape(_BAD_XML.sub('', str(value)))
                out.append(f'<c r="{ref}" s="{STYLE[style]}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>')
        out.append('</row>')
    # 1820처럼 연도만 적은 날짜에 "텍스트로 저장된 숫자" 초록 삼각형이 뜨지 않게 합니다.
    out.append('</sheetData><ignoredErrors><ignoredError sqref="A1:XFD1048576" numberStoredAsText="1"/></ignoredErrors></worksheet>')
    return ''.join(out)


_STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<fonts count="6"><font><sz val="11"/><name val="맑은 고딕"/><family val="3"/></font>'
           '<font><b/><sz val="11"/><name val="맑은 고딕"/><family val="3"/></font>'
           '<font><sz val="11"/><color rgb="FF6B5B45"/><name val="맑은 고딕"/><family val="3"/></font>'
           '<font><i/><sz val="11"/><color rgb="FF8A8A8A"/><name val="맑은 고딕"/><family val="3"/></font>'
           '<font><b/><sz val="12"/><color rgb="FFC00000"/><name val="맑은 고딕"/><family val="3"/></font>'
           '<font><b/><sz val="14"/><name val="맑은 고딕"/><family val="3"/></font></fonts>'
           '<fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
           '<fill><patternFill patternType="solid"><fgColor rgb="FFEFE6D4"/><bgColor indexed="64"/></patternFill></fill>'
           '<fill><patternFill patternType="solid"><fgColor rgb="FFF1F1F1"/><bgColor indexed="64"/></patternFill></fill></fills>'
           '<borders count="4"><border><left/><right/><top/><bottom/><diagonal/></border>'
           '<border><left/><right/><top/><bottom style="thin"><color rgb="FF9C8A6A"/></bottom><diagonal/></border>'
           # 2: 대각선 칸, 3: 칸 제목. 네 변 모두 선을 긋습니다.
           '<border diagonalDown="1"><left style="thin"><color rgb="FFD0C8B8"/></left><right style="thin"><color rgb="FFD0C8B8"/></right><top style="thin"><color rgb="FFD0C8B8"/></top>'
           '<bottom style="thin"><color rgb="FFD0C8B8"/></bottom><diagonal style="thin"><color rgb="FF9C8A6A"/></diagonal></border>'
           '<border><left style="thin"><color rgb="FFD0C8B8"/></left><right style="thin"><color rgb="FFD0C8B8"/></right><top style="thin"><color rgb="FFD0C8B8"/></top>'
           '<bottom style="thin"><color rgb="FFD0C8B8"/></bottom><diagonal/></border></borders>'
           '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
           '<cellXfs count="23"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
           '<xf numFmtId="49" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyNumberFormat="1"/>'
           '<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
           '<xf numFmtId="49" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyNumberFormat="1"/>'
           '<xf numFmtId="49" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1" applyNumberFormat="1"/>'
           '<xf numFmtId="49" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1" applyNumberFormat="1"/>'
           '<xf numFmtId="49" fontId="3" fillId="3" borderId="0" xfId="0" applyFont="1" applyFill="1" applyNumberFormat="1"/>'
           '<xf numFmtId="49" fontId="1" fillId="2" borderId="2" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1" applyNumberFormat="1">'
           '<alignment wrapText="1" vertical="center"/></xf>'
           '<xf numFmtId="49" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1" applyNumberFormat="1"/>'
           '<xf numFmtId="49" fontId="5" fillId="0" borderId="0" xfId="0" applyFont="1" applyNumberFormat="1"/>'
           '<xf numFmtId="0" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1" applyAlignment="1"><alignment horizontal="center"/></xf>'
           # colhead: 가계도 표의 칸 제목(가로·세로 가운데). kind·gkind: 구분 칸(가운데, gkind는 회색 바탕).
           '<xf numFmtId="49" fontId="1" fillId="2" borderId="3" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1" applyNumberFormat="1">'
           '<alignment horizontal="center" vertical="center" wrapText="1"/></xf>'
           '<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1" applyNumberFormat="1">'
           '<alignment horizontal="center" vertical="center"/></xf>'
           '<xf numFmtId="49" fontId="0" fillId="3" borderId="0" xfId="0" applyFill="1" applyAlignment="1" applyNumberFormat="1">'
           '<alignment horizontal="center" vertical="center"/></xf>'
           # num: 세(世) 같은 숫자 칸, 가운데 맞춤.
           '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center"/></xf>'
           # 15~22: 가계도 표 안의 칸. 위 모양에 칸 제목과 같은 네 변 테두리(borderId 3)를 더한 것입니다.
           + ''.join(f'<xf numFmtId="{fmt}" fontId="{font}" fillId="{fill}" borderId="3" xfId="0" applyFont="1" applyFill="1" '
                     f'applyBorder="1" applyAlignment="1" applyNumberFormat="1"><alignment{align} vertical="center"/></xf>'
                     for fmt, font, fill, align in ((49, 0, 0, ''), (49, 3, 0, ''), (49, 0, 3, ''), (49, 3, 3, ''),
                                                    (0, 0, 3, ' horizontal="center"'), (49, 0, 0, ' horizontal="center"'),
                                                    (49, 0, 3, ' horizontal="center"'), (0, 0, 0, ' horizontal="center"')))
           + '</cellXfs>'
           '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


def write_xlsx(sheets):
    """sheets: [(name, rows, widths, text_columns[, options])] → the bytes of an .xlsx file.

    options: {'hidden': True} 숨김 시트, {'heights': {행: 높이}} 행 높이, {'freeze': n} 위 n행 고정(0이면 없음).
    """
    sheets = [(name, rows, widths, text_columns, (rest[0] if rest else {}))
              for name, rows, widths, text_columns, *rest in sheets]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        overrides = ''.join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(sheets) + 1))
        z.writestr('[Content_Types].xml',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                   '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
                   + overrides + '</Types>')
        z.writestr('_rels/.rels',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
                   '</Relationships>')
        z.writestr('xl/workbook.xml',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + ''.join(f'<sheet name="{escape(name)}" sheetId="{i}"{" state=" + chr(34) + "hidden" + chr(34) if options.get("hidden") else ""} r:id="rId{i}"/>'
                             for i, (name, _, _, _, options) in enumerate(sheets, start=1))
                   + '</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + ''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                             for i in range(1, len(sheets) + 1))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   '</Relationships>')
        z.writestr('xl/styles.xml', _STYLES)
        for i, (_, rows, widths, text_columns, options) in enumerate(sheets, start=1):
            z.writestr(f'xl/worksheets/sheet{i}.xml',
                       _sheet_xml(rows, widths, text_columns, options.get('heights'), options.get('freeze', 1)))
    return buffer.getvalue()


# ── 엑셀 가계도 내보내기 ──────────────────────────────────────────────

TREE_SHEET = '가계도'
GUIDE_SHEET = '작성 안내'
PROGRAM_SHEET = '프로그램 정보'
# 2026.11.1~11.6 파일의 시트. 불러올 때만 읽습니다.
EXTRA_SHEET = '추가 관계'
INFO_SHEET = '족보 정보'
LISTING_SHEET = '인물 목록'

# 대각선을 그은 첫 칸: 오른쪽 위에 "세대", 왼쪽 아래에 "구분".
CORNER = '             세대\n구분'
# 이름 열 오른쪽의 칸. 번호는 사람을 구별하는 번호로, 새로 추가하는 사람은 비워 둡니다.
DETAIL_HEADS = ['세', '본관', '출생일', '사망일', '생모(生母)', '기록', '번호']
DETAIL_WIDTHS = [6, 14, 12, 12, 16, 70, 7]

# 구분: 칸에 적힌 말 → (집안 사람인가, 성별, 입양인가, 첫 배우자인가)
KINDS = {}
for words, meaning in (
        (('子', '아들'), ('clan', '남', False, None)),
        (('女', '딸'), ('clan', '여', False, None)),
        (('配', '본처', '부인', '처'), ('spouse', '여', False, True)),
        (('繼配', '계배', '후처', '後配', '후배'), ('spouse', '여', False, False)),
        (('壻', '婿', '사위', '남편', '夫'), ('spouse', '남', False, None)),
        (('系子', '양자', '養子', '繼子'), ('clan', '남', True, None)),
        (('養女', '양녀'), ('clan', '여', True, None))):
    for word in words:
        KINDS[word] = meaning
KIND_NAMES = '子(아들), 女(딸), 配(본처), 繼配(후처), 壻(사위), 系子(양자), 養女(양녀)'
# 구분 칸에 쓰는 말: 한자 뒤 괄호 안에 한글 뜻. 예: 子(아들)
KIND_LABEL = {word.split('(')[0]: word for word in KIND_NAMES.split(', ')}
_KIND_PAIR = re.compile(r'([^()（）]+)[(（]([^()（）]*)[)）]')


def kind_meaning(text):
    """구분 칸의 말 → KINDS의 뜻. 子, 아들, 子(아들) 모두 읽습니다. 모르는 말이거나 앞뒤가 다르면 None."""
    text = re.sub(r'\s+', '', text or '')
    if text in KINDS:
        return KINDS[text]
    pair = _KIND_PAIR.fullmatch(text)
    if not pair:
        return None
    outer, inner = KINDS.get(pair.group(1)), KINDS.get(pair.group(2))
    if outer and inner and outer != inner:
        return None
    return outer or inner


def _plain(rows):
    return [[cell[0] if isinstance(cell, tuple) else cell for cell in row] for row in rows]


def _tree_head(base, depth):
    return [(CORNER, 'corner')] + [(f'{base + d}세', 'colhead') for d in range(depth)] + [(h, 'colhead') for h in DETAIL_HEADS]


def _tree_row(depth, gubun, column, name, details, guest):
    """가계도 시트의 한 줄. 부인·사위 줄은 옅은 회색 바탕입니다."""
    # 표 안의 칸은 빈 칸까지 모두 칸 제목과 같은 테두리를 긋습니다(b_ 모양).
    fill, faint = ('b_gfill', 'b_gref') if guest else ('b_text', 'b_ref')
    cells = [(KIND_LABEL.get(gubun, gubun), 'b_gkind' if guest else 'b_kind')] + [('', fill) for _ in range(depth)] + [('', fill) for _ in DETAIL_HEADS]
    cells[1 + column] = (name, fill)
    for offset, value in enumerate(details):
        if value is None or value == '':
            continue
        style = faint if DETAIL_HEADS[offset] == '번호' else (('b_gfill' if isinstance(value, str) else 'b_gnum') if guest else ('b_text' if isinstance(value, str) else 'b_num'))
        cells[1 + depth + offset] = (value, style)
    return cells


def tree_xlsx(book):
    rows, by_id, parents_of, spouses_of = lay_out(book)
    depth = max((row['depth'] for row in rows), default=0) + 1
    tops = [by_id[row['pid']]['generation'] for row in rows if row['depth'] == 0 and row['kind'] == 'person']
    base = min(tops, default=1)
    sheet = [_tree_head(base, depth)]
    for row in rows:
        person = by_id[row['pid']]
        guest = row['kind'] in ('spouse', 'spouse-ref')
        name = label(person)
        details = [None] * len(DETAIL_HEADS)
        # 이미 다른 줄에 적힌 사람은 번호로 가리킵니다. 줄을 끼우거나 지워도 바뀌지 않습니다.
        if row['kind'] in ('spouse-ref', 'child-ref'):
            name = f'{name} → 번호 {row["pid"]}'
        if row['kind'] in ('person', 'spouse'):
            details = [person['generation'], bongwan_cell(person['bon_gwan']), sheet_date(person['birth_date']), sheet_date(person['death_date']),
                       None, person['note'], person['id']]
        if row['kind'] in ('person', 'child-ref'):
            other = row.get('other')
            details[DETAIL_HEADS.index('생모(生母)')] = (
                other if isinstance(other, str) else (label(by_id[other]) if other is not None else ''))
        sheet.append(_tree_row(depth, row['gubun'], row['depth'], name, details, guest))
    widths = [14] + [16] * depth + DETAIL_WIDTHS
    text_columns = {1 + depth + 2, 1 + depth + 3}

    # 트리로 그릴 수 없는 관계(배우자의 전혼 자녀, 집안끼리의 혼인 등)는 숨김 시트에 번호로 적습니다.
    # 어느 관계가 그런지는 가계도 시트를 불러올 때처럼 다시 읽어 족보와 비교해 찾습니다.
    drawn = tree_family(_plain(sheet))
    number_of = {p['key']: p['id'] for p in drawn['people']}
    implied = ({('parent', number_of[a], number_of[b]) for a, b, *_ in drawn['parents']}
               | {('spouse', *sorted((number_of[a], number_of[b]))) for a, b, *_ in drawn['spouses']})
    actual = {('parent', r['source_id'], r['target_id']) if r['kind'] == 'parent'
              else ('spouse', *sorted((r['source_id'], r['target_id'])))
              for r in book['relations'] if r['source_id'] in by_id and r['target_id'] in by_id}
    program = [['이 시트는 프로그램이 쓰는 정보입니다. 고치지 마십시오.'], [],
               ['항목', '내용']] + [[word, (book.get(field) or '', 'text')] for field, word in BOOK_WORDS]
    if book.get('book_key'):
        program.append([KEY_WORD, (book['book_key'], 'text')])
    program += [[], [EXTRA_HEAD, '번호', '이름', '번호', '이름']]
    adopted_links = {(r['source_id'], r['target_id']) for r in book['relations'] if r['kind'] == 'parent' and r.get('adopted')}
    for kind, a, b in sorted(actual - implied):
        word = '배우자' if kind == 'spouse' else ('양부모-자녀' if (a, b) in adopted_links else '부모-자녀')
        program.append([word, a, label(by_id[a]), b, label(by_id[b])])
    return write_xlsx([(TREE_SHEET, sheet, widths, text_columns, {'heights': {1: 40}}),
                       (GUIDE_SHEET, *guide_sheet()),
                       (PROGRAM_SHEET, program, [24, 40, 20, 8, 20], (), {'hidden': True, 'freeze': 0})])


# 프로그램 정보 시트에서 트리로 그릴 수 없는 관계 표가 시작되는 줄의 첫 칸.
EXTRA_HEAD = '추가 관계'

# 작성 안내 시트와 엑셀 양식에 쓰는 가상의 한 집안. 일곱 가지 구분이 모두 들어 있습니다.
# (구분, 세대 열, 이름, 세, 본관, 출생일, 사망일, 생모, 기록)
EXAMPLE = [
    ('子', 0, '金始祖(김시조)', 25, '金海', '1820', '1885-03-12', '',
     '字 景仁(경인) · 號 松溪(송계) · 通政大夫 · 墓 竹谷後山(죽곡후산) 酉坐(유좌) · 碑石 있음'),
    ('配', 0, '李貞淑(이정숙)', 25, '全州', '', '--09-19', '', '父 文煥(문환) · 忌 九月十九日 · 墓 合墳(합분)'),
    ('繼配', 0, '朴英順(박영순)', 25, '密陽', '', '1890-11-02', '', '父 泰俊(태준) · 墓 同原(동원) 子坐(자좌)'),
    ('子', 1, '金一男(김일남)', 26, '金海', '1845-05-02', '1910', '李貞淑(이정숙)',
     '初名 一坤(일곤) · 字 聲遠(성원) · 墓 竹谷後山(죽곡후산) 亥坐(해좌)'),
    ('配', 1, '崔氏(최씨)', 26, '慶州', '', '', '', '父 鎭國(진국) · 墓 雙墳(쌍분)'),
    ('子', 2, '金長孫(김장손)', 27, '金海', '1870', '', '', '字 致遠(치원) · 號 晩松(만송) · 通訓大夫 中樞院議官'),
    ('系子', 2, '金繼孫(김계손)', 27, '金海', '', '', '', '生父 金某 · 다른 집에서 양자로 들어옴'),
    ('女', 1, '金順(김순)', 26, '金海', '1852-02-11', '', '朴英順(박영순)',
     '出嫁 東萊 鄭在德(정재덕) · 孝行으로 鄕校에서 褒賞 · 忌 三月初八日 · 墓 鄭氏 先塋(정씨 선영)'),
    ('壻', 1, '鄭在德(정재덕)', 26, '東萊', '', '', '', '父 漢植(한식) · 子 東炫(동현) · 女 志娟(지연)'),
    ('子', 1, '金二男(김이남)', 26, '金海', '', '', '朴英順(박영순)', '字 聲和(성화) · 墓 竹谷(죽곡) 先塋下(선영하)'),
    ('養女', 1, '金貞(김정)', 26, '金海', '', '', '朴英順(박영순)', '生父 李某 · 다른 집에서 양녀로 들어옴'),
]
EXAMPLE_NAMES = {split_name(row[2])[1] for row in EXAMPLE} | {split_name(row[2])[0] for row in EXAMPLE}


def _example_rows(numbered=False):
    head = _tree_head(25, 3)
    if numbered:
        marks = '①②③④⑤⑥⑦⑧⑨⑩'
        head = [(CORNER.replace('구분', '① 구분'), 'corner'), ('② 25세', 'colhead'), ('26세', 'colhead'), ('27세', 'colhead')] + [
            (f'{marks[2 + i]} {h}', 'colhead') for i, h in enumerate(DETAIL_HEADS)]
    rows = [head]
    for gubun, column, name, gen, bon, born, died, other, note in EXAMPLE:
        guest = KINDS[gubun][0] == 'spouse'
        rows.append(_tree_row(3, gubun, column, name, [gen, bongwan_cell(bon), sheet_date(born), sheet_date(died), other, note, None], guest))
    return rows


# 작성 안내의 글. 한 줄이 엑셀 한 행입니다. ('warn', …)은 붉은 경고, ('title', …)은 제목입니다.
GUIDE_TEXT = [
    ('title', '엑셀 가계도 작성 안내'),
    ('', ''),
    ('warn', '⚠ 주의: 칸을 비우면 족보의 기존 내용이 지워집니다.'),
    ('warn', '프로그램에서 내보낸 파일을 고쳐서 원래 족보에 반영할 때, 내용이 있던 칸을 비워 두면 족보에 적혀 있던 그 내용도 지워집니다.'),
    ('warn', '지우려는 것이 아니라면 칸을 비우지 마십시오.'),
    ('', ''),
    ('', '족보는 "가계도" 시트에 작성합니다. 한 줄에는 한 사람만 적습니다.'),
    ('', '아래 예시 표의 칸 제목에 붙은 번호와, 그 아래 설명의 번호는 서로 같은 칸을 가리킵니다.'),
    ('', ''),
    ('example', ''),
    ('', ''),
    ('head', '① 구분'),
    ('', '그 사람이 이 집안과 어떤 관계인지 적습니다.'),
    ('', '이 집안에서 태어난 남자는 子(아들), 여자는 女(딸)라고 적습니다.'),
    ('', '이 집안 남자의 첫 부인은 配(본처), 둘째 이후의 부인은 繼配(후처)라고 적습니다.'),
    ('', '이 집안 여자의 남편은 壻(사위)라고 적습니다.'),
    ('', '다른 집에서 태어나 이 집안으로 입양된 아들은 系子(양자), 딸은 養女(양녀)라고 적습니다.'),
    ('', '구분 칸에는 예시처럼 子(아들)과 같이 한자를 적고 그 뒤 괄호 안에 한글 뜻을 적습니다. 한자만 적거나 한글만 적어도 프로그램이 읽습니다.'),
    ('', '구분 칸을 비우면 이 집안에서 태어났고 성별을 모르는 사람으로 봅니다.'),
    ('', ''),
    ('head', '② 세대 열(25세, 26세, 27세 …)'),
    ('', '이름은 그 사람의 세대에 해당하는 열에 적습니다. 예를 들어 25세인 사람은 "25세" 열에 적고, 그 사람의 자녀는 바로 오른쪽 "26세" 열에 적습니다.'),
    ('', '자녀는 부모가 적힌 줄보다 아래에 적고, 형제자매는 같은 열에 나이 순서대로 이어서 적습니다.'),
    ('', '부인과 사위는 남편 또는 아내의 바로 아래 줄, 같은 열에 적습니다. 부인이 둘 이상이면 본처를 먼저 적고 후처를 그 아래에 적습니다.'),
    ('', '이름은 金一男(김일남)처럼 한자와 한글을 함께 적어도 되고, 둘 가운데 하나만 적어도 됩니다.'),
    ('', '부인의 이름을 알면 李貞淑(이정숙)처럼 이름을 적고, 이름을 모르면 예시의 崔氏(최씨)처럼 성 뒤에 氏를 붙여 적습니다.'),
    ('', '세대 열이 모자라면 오른쪽에 "28세"처럼 열을 더 만들어 적습니다.'),
    ('', ''),
    ('head', '③ 세'),
    ('', '그 사람의 실제 세(世)를 숫자로 적습니다. 비워 두면 이름을 적은 열의 세대를 따릅니다.'),
    ('', ''),
    ('head', '④ 본관'),
    ('', '그 사람의 본관을 적습니다. 부인과 사위는 친정 또는 본가의 본관을 적습니다.'),
    ('', '본관도 이름처럼 金海(김해)와 같이 한자 옆 괄호 안에 한글을 적습니다. 한자만 적거나 한글만 적어도 됩니다.'),
    ('', '프로그램이 파일을 만들 때는 한자로 저장된 본관은 金海(김해)로, 한글로 저장된 본관은 김해(金海)로 적습니다. 다시 불러올 때는 괄호 앞의 말을 본관으로 저장합니다.'),
    ('', ''),
    ('head', '⑤ 출생일, ⑥ 사망일'),
    ('', '날짜는 아는 만큼만 적습니다. 연도만 알면 1956, 연도와 달을 알면 1956-03, 날짜까지 알면 1956-03-02처럼 적습니다.'),
    ('', '1956.3.2나 1956년 3월 2일처럼 적어도 읽습니다. 연도를 모르고 달과 날만 알면 미상-03-02처럼 연도 자리에 미상이라고 적습니다. 3월 2일처럼 적어도 읽습니다.'),
    ('', '출생일을 모르면 비워 두고 사망일만 적어도 됩니다. 예시의 朴英順은 출생일을 몰라 사망일만 적었고, 李貞淑은 돌아가신 해도 몰라 제삿날만 알아 사망일에 미상-09-19라고 적었습니다.'),
    ('', ''),
    ('head', '⑦ 생모(生母)'),
    ('', '생모는 그 자녀를 낳은 어머니를 말합니다.'),
    ('', '아버지에게 부인이 두 명 이상일 때에만, 자녀의 줄에 그 자녀를 낳은 어머니의 이름을 적습니다.'),
    ('', '예시에서 金始祖에게는 본처 李貞淑과 후처 朴英順이 있습니다. 金一男은 李貞淑이 낳았으므로 李貞淑(이정숙)이라고 적었고, 金順과 金二男은 朴英順이 낳았으므로 朴英順(박영순)이라고 적었습니다. 부인 줄에 적은 이름과 똑같이 적어야 프로그램이 찾을 수 있습니다.'),
    ('', '아버지의 부인이 한 명뿐이면 이 칸은 비워 둡니다. 비워 두면 그 부인이 낳은 자녀로 봅니다.'),
    ('', '부인의 줄과 사위의 줄에는 이 칸을 적지 않습니다. 어머니가 누구인지 모르면 (미상)이라고 적습니다.'),
    ('', ''),
    ('head', '⑧ 기록'),
    ('', '그 사람에 대해 남길 내용을 적습니다. 여러 가지를 적을 때는 예시처럼 가운뎃점(·)으로 나누어 한 칸에 적습니다.'),
    ('', '字(자), 號(호), 初名(초명), 관직, 학력, 상훈처럼 그 사람의 이력을 적습니다.'),
    ('', '돌아가신 분은 忌(제삿날)와 墓(묘소의 위치와 방향)를 적습니다. 예: 墓 竹谷後山 酉坐(유좌), 墓 合墳(합분), 墓 雙墳(쌍분), 碑石 있음.'),
    ('', '딸의 줄에도 이력과 墓를 적고, 어느 집안의 누구에게 시집갔는지를 出嫁 다음에 적습니다. 예: 出嫁 東萊 鄭在德(정재덕).'),
    ('', '부인과 사위의 줄에는 그 사람의 친정 또는 본가 아버지의 이름을 父 다음에 적습니다. 예: 父 泰俊(태준).'),
    ('', '사위의 줄에는 딸이 낳은 자녀(외손)의 이름을 子, 女 다음에 적습니다. 예: 子 東炫(동현) · 女 志娟(지연). 외손은 이 집안의 대를 잇지 않으므로 따로 줄을 만들지 않고 사위의 기록에만 적습니다.'),
    ('', '양자와 양녀는 친부모의 이름을 적습니다. 예: 生父 金某.'),
    ('', '다른 집으로 양자를 간 아들은 이 집안에서 태어났으므로 구분에 子(아들)라고 적고, 기록에 出系라고 적습니다.'),
    ('', ''),
    ('head', '⑨ 번호'),
    ('', '프로그램이 사람을 구별하려고 붙인 번호입니다. 이 번호는 고치거나 지우지 마십시오.'),
    ('', '새로 추가하는 사람의 번호 칸은 비워 둡니다.'),
    ('', '이름 뒤에 "→ 번호 12"처럼 적힌 줄은, 이미 다른 줄에 적힌 번호 12인 사람을 다시 가리키는 줄입니다. 이 줄은 고치지 말고 그대로 두십시오.'),
    ('', ''),
    ('head', '이미 있는 족보를 고칠 때 알아 둘 점'),
    ('', '프로그램에서 내보낸 엑셀 파일을 고쳐서 불러오면, 원래 족보에 고친 내용을 반영할 수 있습니다. 반영은 다음 규칙을 따릅니다.'),
    ('', '· 칸의 내용을 고치면 족보의 내용도 고친 대로 바뀝니다.'),
    ('warn', '· 칸을 비우면 족보에 적혀 있던 그 내용도 지워집니다. 예를 들어 사망일 칸을 비우고 불러오면 족보의 사망일도 지워집니다.'),
    ('', '· 새 줄을 끼워 사람을 적으면 족보에 새 사람으로 추가됩니다.'),
    ('', '· 줄을 지워도 족보의 사람은 지워지지 않습니다. 사람을 지우려면 프로그램의 인물 화면에서 지우십시오.'),
    ('', '· 반영하기 전에 바뀌는 내용을 화면에 보여 드리고, 반영 직전의 족보는 백업해 둡니다.'),
    ('', ''),
    ('', '양식으로 받은 파일의 예시 줄(金始祖 등 가상 인물)은 지운 뒤에 작성하십시오.'),
]


def guide_sheet():
    """작성 안내 시트: (rows, widths, text_columns, options)."""
    rows, heights = [], {}
    for kind, text in GUIDE_TEXT:
        if kind == 'example':
            start = len(rows) + 1
            rows += _example_rows(numbered=True)
            heights[start] = 40
            continue
        style = {'warn': 'warn', 'title': 'title', 'head': 'head'}.get(kind, 'plain')
        rows.append([(text, style)] if text else [])
    return rows, [14, 16, 16, 16] + DETAIL_WIDTHS, (), {'heights': heights, 'freeze': 0}


def template_gedcom():
    """엑셀 양식과 같은 가상의 한 집안을 GEDCOM으로."""
    family = tree_family(_plain(_example_rows()))
    keys = ['korean_name', 'hanja_name', 'generation', 'gender', 'bon_gwan', 'birth_date', 'death_date', 'note']
    number = {p['key']: index for index, p in enumerate(family['people'], start=1)}
    book = {'title': 'GEDCOM 양식', 'clan_name': '金氏', 'bon_gwan': '金海', 'volume': '1',
            'description': '불러오기 예시입니다. 모든 인물은 가상 인물입니다.',
            'persons': [{'id': number[p['key']], **{k: p[k] for k in keys}} for p in family['people']],
            'relations': [{'id': i, 'source_id': number[a], 'target_id': number[b], 'kind': 'parent', 'adopted': adopted}
                          for i, (a, b, adopted) in enumerate(family['parents'], start=1)]
                         + [{'id': 100 + i, 'source_id': number[a], 'target_id': number[b], 'kind': 'spouse', 'marriage_order': order}
                            for i, (a, b, order) in enumerate(family['spouses'], start=1)]}
    return gedcom(book)


def template_xlsx():
    """엑셀 양식: 작성 예시가 채워진 가계도 시트와 작성 안내 시트."""
    return write_xlsx([(TREE_SHEET, _example_rows(), [14, 16, 16, 16] + DETAIL_WIDTHS, {7, 8}, {'heights': {1: 40}}),
                       (GUIDE_SHEET, *guide_sheet())])

# The book's own fields on a sheet of their own, so a sheet sent out comes back
# as the same book, as a GEDCOM file does.
INFO_SHEET = '족보 정보'
BOOK_WORDS = [('title', '족보명'), ('clan_name', '성씨/가문'), ('bon_gwan', '본관'), ('branch_name', '파명'),
              ('volume', '권'), ('page', '페이지'), ('page_breaks', '쪽 이어짐'), ('founder', '시조'),
              ('lineage', '계통'), ('description', '설명')]


# The key that ties a file to the book it came from (see main.export_book).
KEY_WORD = '족보 번호 (고치지 마십시오)'


def book_info(rows):
    """The book's fields from the 족보 정보 sheet, and the book's key if the sheet has one."""
    words = {word: field for field, word in BOOK_WORDS}
    book, key = {}, ''
    for row in rows[1:]:
        if len(row) < 2:
            continue
        word, value = _cell_text(row[0]), row[1]
        value = value.strip() if isinstance(value, str) else _cell_text(value)
        if word in words:
            book[words[word]] = value
        elif word == KEY_WORD:
            key = value
    return book, key


# ── xlsx · csv 읽기 ───────────────────────────────────────────────────

MAX_PART = 60 * 1024 * 1024


def _xml(z, name):
    info = z.getinfo(name)
    if info.file_size > MAX_PART:
        raise ExchangeError('엑셀 파일이 너무 큽니다.')
    return ET.fromstring(z.read(name))


def read_xlsx(data, sheet_name=TREE_SHEET, fallback=True):
    """The rows of one sheet as lists of str / float / None.

    The 가계도 sheet is read, or the first sheet when there is none of that name;
    with fallback off, a missing sheet gives no rows.
    """
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        names = set(z.namelist())
        workbook = _xml(z, 'xl/workbook.xml')
        rels = _xml(z, 'xl/_rels/workbook.xml.rels')
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ExchangeError('엑셀(.xlsx) 파일을 읽지 못했습니다. 엑셀에서 "Excel 통합 문서(.xlsx)"로 다시 저장해 주십시오.')
    targets = {rel.get('Id'): rel.get('Target') for rel in rels}
    sheets = [(sheet.get('name'), sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'))
              for sheet in workbook.iterfind('.//{*}sheet')]
    if not sheets:
        raise ExchangeError('엑셀 파일에 시트가 없습니다.')
    rid = next((rid for name, rid in sheets if name == sheet_name), sheets[0][1] if fallback else None)
    if rid is None:
        return []
    target = (targets.get(rid) or '').lstrip('/')
    path = target if target.startswith('xl/') else 'xl/' + target
    if path not in names:
        raise ExchangeError('엑셀 시트를 찾지 못했습니다.')
    shared = []
    if 'xl/sharedStrings.xml' in names:
        for item in _xml(z, 'xl/sharedStrings.xml').iterfind('.//{*}si'):
            shared.append(''.join(t.text or '' for t in item.iterfind('.//{*}t')))
    grid = {}
    for cell in _xml(z, path).iterfind('.//{*}c'):
        ref = cell.get('r') or ''
        found = re.fullmatch(r'([A-Z]+)(\d+)', ref)
        if not found:
            continue
        kind = cell.get('t')
        value_node = cell.find('{*}v')
        raw = value_node.text if value_node is not None else None
        if kind == 's':
            value = shared[int(raw)] if raw is not None and raw.isdigit() and int(raw) < len(shared) else ''
        elif kind == 'inlineStr':
            value = ''.join(t.text or '' for t in cell.iterfind('.//{*}t'))
        elif kind in ('str', 'e'):
            value = raw or ''
        elif kind == 'b':
            value = raw or ''
        else:
            try:
                value = float(raw) if raw not in (None, '') else None
            except ValueError:
                value = raw
        grid[(int(found[2]) - 1, column_index(found[1]))] = value
    if not grid:
        return []
    height = max(r for r, _ in grid) + 1
    width = max(c for _, c in grid) + 1
    if height * width > 4_000_000:
        raise ExchangeError('엑셀 시트가 너무 큽니다.')
    rows = [[None] * width for _ in range(height)]
    for (r, c), value in grid.items():
        rows[r][c] = value
    return rows


def read_csv(data):
    for encoding in ('utf-8-sig', 'cp949'):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ExchangeError('CSV 파일의 글자를 읽지 못했습니다. UTF-8로 저장해 주십시오.')
    return [row for row in csv.reader(io.StringIO(text))]


# ── 엑셀 가계도 불러오기 ──────────────────────────────────────────────

HEAD_FIELDS = {'세': 'generation', '세대': 'generation', '世': 'generation', '성별': 'gender', '본관': 'bon_gwan',
               '출생일': 'birth_date', '출생': 'birth_date', '생년월일': 'birth_date', '생일': 'birth_date',
               '사망일': 'death_date', '사망': 'death_date', '졸': 'death_date',
               '생모(生母)': 'other', '생모': 'other', '生母': 'other', '어머니(아버지)': 'other', '어머니': 'other', '아버지': 'other', '다른부모': 'other', '배우자부모': 'other',
               '기록': 'note', '메모': 'note', '비고': 'note', '한자명': 'hanja_name', '한자': 'hanja_name',
               '번호': 'id', '번호(고치지않음)': 'id'}
# 2026.11.1~11.6 양식은 구분 열 없이 배우자 이름 앞에 "配 "를 붙였습니다. 그 모양도 읽습니다.
SPOUSE_MARK = re.compile(r'^\s*(?:配|배\s*[):.]|배\s+)\s*')
# → 번호 12 (번호 12인 사람), 또는 2026.11.1~11.5 양식의 → 12행.
REFERENCE = re.compile(r'\s*(?:→|->)\s*(?:번호\s*)?(\d+)\s*(행)?\s*$')
# 양식의 예시 인물. 지우지 않고 불러오면 알립니다.
EXAMPLE_MARKS = {'金始祖', '金繼孫', '金長孫'}


def _cell_text(value):
    if value is None:
        return ''
    if isinstance(value, float):
        return str(int(value)) if value == int(value) else str(value)
    return str(value).strip()


def _head_name(value):
    return re.sub(r'\s+', '', _cell_text(value))


def program_info(rows):
    """숨김 "프로그램 정보" 시트: 족보 정보, 족보 번호, 트리로 그릴 수 없는 관계."""
    cut = next((i for i, row in enumerate(rows) if row and _cell_text(row[0]) == EXTRA_HEAD), len(rows))
    book, key = book_info(rows[:cut])
    return book, key, rows[cut:]


def tree_family(rows, extra=()):
    """가계도 시트를 읽습니다. 알림의 행 번호는 엑셀의 행 번호와 같습니다.

    extra: 트리로 그릴 수 없는 관계 표(첫 줄은 제목).
    """
    family = {'book': {}, 'book_key': '', 'people': [], 'parents': [], 'spouses': [], 'warnings': [], 'errors': []}
    rows = [list(row) for row in rows]
    if not rows:
        family['errors'].append('엑셀 시트가 비어 있습니다.')
        return finish(family)
    width = max(len(row) for row in rows)
    for row in rows:
        row.extend([None] * (width - len(row)))
    first = [_head_name(v) for v in rows[0]]
    kind_col = next((i for i, name in enumerate(first) if '구분' in name), None)
    detail = {index: HEAD_FIELDS[name] for index, name in enumerate(first) if name in HEAD_FIELDS}
    has_head = bool(detail) or kind_col is not None or any(re.fullmatch(r'\d+[세世]', name) for name in first)
    tree_start = kind_col + 1 if kind_col is not None else 0
    tree_end = min(detail) if detail else width
    if tree_end <= tree_start:
        family['errors'].append('1행: 이름을 적을 세대 열(예: 25세, 26세)이 없습니다. 세대 열은 구분 열 오른쪽, 세·본관 같은 칸의 왼쪽에 둡니다.')
        return finish(family)
    base_match = re.match(r'(\d+)', first[tree_start]) if has_head else None
    base = int(base_match[1]) if base_match else 1
    start = 1 if has_head else 0
    # 파일에 실제로 있는 칸. 반영할 때 이 칸이 비어 있으면 족보의 내용도 지웁니다.
    present = ['korean_name', 'hanja_name', 'generation']
    present += sorted({field for field in detail.values() if field in ('bon_gwan', 'birth_date', 'death_date', 'note')})
    if kind_col is not None or 'gender' in detail.values():
        present.append('gender')

    last = {}               # 세대 열 → 그 열에 마지막으로 적힌 집안 사람의 key
    mates = defaultdict(list)
    wives = defaultdict(int)  # 배우자 줄을 만날 때마다 1씩: 혼인 순서
    row_person, numbered = {}, {}
    pending = []
    people = family['people']
    errors, warnings = family['errors'], family['warnings']

    def attach(kind, anchor, target, other, number, adopted, order):
        if kind == 'spouse':
            family['spouses'].append([anchor, target, order])
            mates[anchor].append(target)
        elif anchor is not None:
            _link_child(family, anchor, target, other, mates, number, people, adopted)

    for index in range(start, len(rows)):
        row, number = rows[index], index + 1
        names = [(c, _cell_text(row[c])) for c in range(tree_start, tree_end) if _cell_text(row[c])]
        kind_text = _head_name(row[kind_col]) if kind_col is not None else ''
        if not names:
            if any(_cell_text(v) for v in row[tree_end:]) or kind_text:
                warnings.append(f'{number}행: 이름이 적혀 있지 않아 이 줄을 건너뛰었습니다.')
            continue
        if len(names) > 1:
            errors.append(f'{number}행: 이름이 두 칸 이상에 적혀 있습니다. 한 줄에는 한 사람만 적습니다.')
            continue
        column, text = names[0][0] - tree_start, names[0][1]
        marked = bool(SPOUSE_MARK.match(text))
        if marked:
            text = SPOUSE_MARK.sub('', text, count=1)
        if kind_text:
            meaning = kind_meaning(kind_text)
            if meaning is None:
                errors.append(f'{number}행: 구분 "{kind_text}"은(는) 쓸 수 없는 말입니다. {KIND_NAMES} 가운데 하나를 적어 주십시오.')
                continue
            role, gender, adopted, _ = meaning
        else:
            role, gender, adopted = ('spouse' if marked else 'clan'), None, False
        spouse = role == 'spouse'
        reference = REFERENCE.search(text)
        if reference:
            text = text[:reference.start()].strip()
        if spouse:
            anchor = last.get(column)
            if anchor is None:
                errors.append(f'{number}행: 이 배우자의 남편이나 아내가 바로 위 줄, 같은 열에 없습니다. 배우자는 그 사람 바로 아래 줄, 같은 열에 적습니다.')
                continue
            wives[anchor] += 1
        else:
            anchor = None
            if column > 0:
                anchor = last.get(column - 1)
                if anchor is None:
                    errors.append(f'{number}행: 이 사람의 부모가 바로 왼쪽 세대 열에 없습니다. 자녀는 부모보다 한 칸만 오른쪽 열에 적습니다.')
                    continue
        cells = {field: row[i] for i, field in detail.items()}
        other = _cell_text(cells.get('other'))
        order = wives[anchor] if spouse else 0
        if reference:
            value, by_row = int(reference[1]), bool(reference[2])
            target = row_person.get(value) if by_row else numbered.get(value)
            if target is not None:
                attach('spouse' if spouse else 'child', anchor, target, other, number, adopted, order)
            else:
                pending.append((number, 'spouse' if spouse else 'child', anchor, value, by_row, other, adopted, order))
            if not spouse:
                last[column] = None
                for c in [c for c in last if c > column]:
                    del last[c]
            continue
        key = f'r{number}'
        person = blank_person(key)
        person['present'] = list(present)
        person['korean_name'], person['hanja_name'] = split_name(text)
        if 'hanja_name' in detail.values() and _cell_text(cells.get('hanja_name')):
            person['hanja_name'] = _cell_text(cells['hanja_name'])
        gen_number = re.match(r'(\d+)', _cell_text(cells.get('generation')))
        person['generation'] = int(gen_number[1]) if gen_number else base + column
        person['gender'] = gender or GENDER.get(_cell_text(cells.get('gender')).upper(), '미상')
        person['bon_gwan'] = bongwan_value(_cell_text(cells.get('bon_gwan')))
        person['id'] = person_number(cells.get('id'))
        note = cells.get('note')
        person['note'] = str(note).strip() if isinstance(note, str) else _cell_text(note)
        for field, word in (('birth_date', '출생'), ('death_date', '사망')):
            value = cells.get(field)
            parsed = text_date(value)
            if parsed is None:
                add_note(person, f'{word} {_cell_text(value)}')
                warnings.append(f'{number}행: {word}일 "{_cell_text(value)}"을(를) 날짜로 읽지 못해 기록 칸에 옮겨 적었습니다.')
            else:
                person[field] = parsed
        where = f'{number}행'
        settle_dates(person, where, warnings)
        fit(person, where, warnings)
        people.append(person)
        row_person[number] = key
        if person['id'] is not None:
            numbered.setdefault(person['id'], key)
        if spouse:
            attach('spouse', anchor, key, other, number, False, order)
        else:
            if anchor is not None:
                attach('child', anchor, key, other, number, adopted, 0)
            last[column] = key
            for c in [c for c in last if c > column]:
                del last[c]

    for number, kind, anchor, value, by_row, other, adopted, order in pending:
        target = row_person.get(value) if by_row else numbered.get(value)
        if target is None:
            errors.append(f'{number}행: "→ {value}행"이 가리키는 줄에 사람이 없습니다.' if by_row
                          else f'{number}행: "→ 번호 {value}"인 사람이 이 시트에 없습니다.')
            continue
        attach(kind, anchor, target, other, number, adopted, order)

    for index, row in enumerate(list(extra)[1:], start=2):
        cells = list(row) + [None] * 5
        word = _head_name(cells[0])
        if not word and not _cell_text(cells[1]) and not _cell_text(cells[3]):
            continue
        a, b = numbered.get(person_number(cells[1])), numbered.get(person_number(cells[3]))
        if word not in ('부모-자녀', '부모', '양부모-자녀', '배우자'):
            errors.append(f'추가 관계 {index}행: 관계는 "부모-자녀" 또는 "배우자"로 적습니다.')
        elif a is None or b is None:
            errors.append(f'추가 관계 {index}행: 번호 {_cell_text(cells[1] if a is None else cells[3])}인 사람이 가계도 시트에 없습니다.')
        elif word == '배우자':
            family['spouses'].append([a, b, 0])
        else:
            family['parents'].append([a, b, int(word == '양부모-자녀')])

    found = sorted({p['hanja_name'] for p in people} & EXAMPLE_MARKS)
    if found:
        warnings.insert(0, f'양식의 예시 인물({", ".join(found)} 등)이 그대로 남아 있습니다. 예시 줄을 지운 뒤 다시 불러오십시오.')
    if len(people) > MAX_PEOPLE:
        errors.append(f'한 번에 {MAX_PEOPLE}명까지 불러올 수 있습니다.')
    return finish(family)


def _link_child(family, parent, child, other, mates, number, people, adopted=False):
    """parent의 자녀로 잇고, 어머니(아버지) 칸이나 배우자 수로 다른 부모도 잇습니다."""
    adopted = int(bool(adopted))
    family['parents'].append([parent, child, adopted])
    spouses = mates.get(parent, [])
    if other in ('(미상)', '미상', '-'):
        return
    if other:
        by_key = {p['key']: p for p in people}
        korean, hanja = split_name(other)
        found = [m for m in spouses if other in (label(by_key[m]), by_key[m]['korean_name'], by_key[m]['hanja_name'])
                 or (korean and korean == by_key[m]['korean_name']) or (hanja and hanja == by_key[m]['hanja_name'])]
        if found:
            family['parents'].append([found[0], child, adopted])
        else:
            family['warnings'].append(f'{number}행: 생모 칸에 적힌 "{other}"을(를) 아버지의 부인 가운데서 찾지 못했습니다. 그래서 이 자녀는 아버지와만 이었습니다.')
        return
    if len(spouses) == 1:
        family['parents'].append([spouses[0], child, adopted])
    elif len(spouses) > 1:
        family['warnings'].append(f'{number}행: 아버지의 부인이 둘 이상인데 생모 칸이 비어 있습니다. 그래서 이 자녀는 아버지와만 이었습니다. 이 자녀를 낳은 어머니의 이름을 생모 칸에 적어 주십시오.')


# ── GEDCOM 내보내기 ───────────────────────────────────────────────────

BOOK_TAGS = [('clan_name', '_CLAN'), ('bon_gwan', '_BONGWAN'), ('branch_name', '_BRANCH'), ('volume', '_VOLUME'),
             ('founder', '_FOUNDER'), ('page', '_PAGE'), ('lineage', '_LINEAGE'), ('page_breaks', '_PAGEBREAKS')]
SURNAMES_TWO = {'남궁', '제갈', '선우', '황보', '독고', '사공', '서문', '동방', '어금', '망절', '장곡',
                '南宮', '諸葛', '鮮于', '皇甫', '獨孤', '司空', '西門', '東方'}


BOOK_NOTE_FIRST = '우리의 족보에서 내보낸 족보입니다.'
# 메모장으로 파일을 연 사람을 위한 안내. 다른 족보 프로그램은 이 글을 읽지 않고 넘어갑니다.
GEDCOM_GUIDE = [
    '이 파일은 GEDCOM 파일입니다. GEDCOM은 족보 프로그램끼리 족보를 주고받으려고 만든 국제 표준 형식입니다.',
    'Gramps, MyHeritage, Ancestry 같은 다른 족보 프로그램에서 이 파일을 불러오면 족보를 그대로 옮길 수 있습니다.',
    '이 파일은 메모장으로 직접 작성하거나 고치는 파일이 아닙니다. 줄의 순서나 기호가 하나라도 틀리면 프로그램이 읽지 못합니다.',
    '족보를 직접 작성하거나 고치려면, 우리의 족보 프로그램의 [불러오기] 창에서 엑셀 양식을 받아 작성하십시오.',
    '아래는 이 족보의 정보입니다.',
]
KEY_LINE = '족보 번호'


def book_note(book):
    """족보명: …, 성씨/가문: …, …, 족보 번호: …, and the description last, since it may run to many lines."""
    lines = [BOOK_NOTE_FIRST] + GEDCOM_GUIDE
    for field, word in BOOK_WORDS:
        if field != 'description' and book.get(field):
            lines.append(f'{word}: {book[field]}')
    if book.get('book_key'):
        lines.append(f'{KEY_LINE}: {book["book_key"]}')
    if book.get('description'):
        lines.append(f'설명: {book["description"]}')
    return '\n'.join(lines)


def read_book_note(text):
    words = {word: field for field, word in BOOK_WORDS}
    book, key = {}, ''
    lines = text.split('\n')[1:]
    for index, line in enumerate(lines):
        word, _, value = line.partition(': ')
        if word == '설명':
            book['description'] = '\n'.join([value] + lines[index + 1:])
            break
        if word == KEY_LINE:
            key = value.strip()
        elif word in words:
            book[words[word]] = value.strip()
    return book, key


def gedcom_name(name):
    """사람 이름 → GEDCOM NAME 줄의 값과 GIVN·SURN.

    김영조 → '영조 /김/'. 이름 없이 성에 씨를 붙인 부인은 다른 족보 프로그램에서 성으로 묶이도록
    崔氏 → '氏 /崔/'(성 崔), 본관이 앞에 붙은 全州崔氏는 이름 그대로 두고 SURN에 崔만 적습니다.
    다시 읽을 때는 어느 쪽이든 원래 이름(崔氏, 全州崔氏)으로 돌아옵니다.
    """
    name = name.strip()
    if len(name) >= 2 and name.endswith(('씨', '氏')) and ' ' not in name:
        rest, suffix = name[:-1], name[-1]
        if len(rest) == 1 or rest in SURNAMES_TWO:
            return f'{suffix} /{rest}/', suffix, rest
        surname = rest[-2:] if rest[-2:] in SURNAMES_TWO else rest[-1]
        return name, '', surname
    surname, given = name_parts(name)
    return (f'{given} /{surname}/'.strip(), given, surname) if surname else (name, '', '')


def name_parts(name):
    """김영조 → ('김', '영조'): a GEDCOM name has its surname between slashes."""
    name = name.strip()
    if not name or ' ' in name or name.endswith(('씨', '氏')) or len(name) < 2:
        return '', name
    size = 2 if name[:2] in SURNAMES_TWO and len(name) >= 3 else 1
    return name[:size], name[size:]


def _ged_value(lines, level, tag, value, xref=None):
    """One GEDCOM line, with long or many-lined values carried on CONT/CONC."""
    head = f'{level} ' + (f'{xref} ' if xref else '') + tag
    text = str(value or '')
    if not text:
        lines.append(head)
        return
    for index, part in enumerate(text.replace('\r', '').split('\n')):
        chunks = [part[i:i + 200] for i in range(0, len(part), 200)] or ['']
        for n, chunk in enumerate(chunks):
            if index == 0 and n == 0:
                lines.append(f'{head} {chunk}' if chunk else head)
            else:
                sub = 'CONT' if n == 0 else 'CONC'
                lines.append(f'{level + 1} {sub} {chunk}' if chunk else f'{level + 1} {sub}')


def gedcom(book, version='2026'):
    people = book['persons']
    by_id = {p['id']: p for p in people}
    xref = {p['id']: f'@I{n}@' for n, p in enumerate(people, start=1)}
    parents_of, spouse_pairs = defaultdict(list), []
    # 사람마다의 혼인(순서는 in_marriage_order)과 입양된 부모-자녀.
    marriages, adopted = defaultdict(list), set()
    for r in book['relations']:
        if r['source_id'] not in by_id or r['target_id'] not in by_id:
            continue
        if r['kind'] == 'parent':
            parents_of[r['target_id']].append(r['source_id'])
            if r.get('adopted'):
                adopted.add((r['source_id'], r['target_id']))
        else:
            pair = tuple(sorted((r['source_id'], r['target_id'])))
            spouse_pairs.append(pair)
            for member in pair:
                marriages[member].append((r, pair))
    spouse_set = set(spouse_pairs)
    families = {}

    def family_of(members):
        key = tuple(sorted(members))
        if key not in families:
            families[key] = {'members': key, 'children': []}
        return families[key]

    for pair in spouse_pairs:
        family_of(pair)
    for child in sorted(parents_of):
        parents = sorted(set(parents_of[child]))
        groups = []
        if len(parents) <= 2:
            groups = [parents]
        else:
            left = list(parents)
            while left:
                one = left.pop(0)
                mate = next((x for x in left if tuple(sorted((one, x))) in spouse_set), None)
                if mate is not None:
                    left.remove(mate)
                    groups.append([one, mate])
                else:
                    groups.append([one])
        for group in groups:
            family_of(group)['children'].append(child)
    fam_xref = {key: f'@F{n}@' for n, key in enumerate(families, start=1)}
    fams, famc = defaultdict(list), defaultdict(list)
    for key, fam in families.items():
        for member in fam['members']:
            fams[member].append(key)
        for child in fam['children']:
            # 입양이면 PEDI adopted(표준 항목)를 붙입니다.
            famc[child].append((fam_xref[key], any((parent, child) in adopted for parent in fam['members'])))
    # 한 사람의 가족(FAMS)은 혼인 순서대로 적습니다. 본처와의 가족이 먼저, 후처가 다음입니다.
    # 배우자 없이 자녀만 있는 가족은 맨 뒤에 둡니다.
    for member, keys in fams.items():
        ordered = [pair for _, pair in in_marriage_order(marriages.get(member, []))]
        keys.sort(key=lambda k: ordered.index(k) if k in ordered else len(ordered))
        fams[member] = [fam_xref[k] for k in keys]

    lines = []
    add = lambda level, tag, value='', ref=None: _ged_value(lines, level, tag, value, ref)
    today = date.today()
    add(0, 'HEAD')
    add(1, 'SOUR', 'JOCBO')
    add(2, 'NAME', '우리의 족보')
    add(2, 'VERS', version)
    add(1, 'DATE', f'{today.day} {MONTHS[today.month - 1]} {today.year}')
    add(1, 'SUBM', '@U1@')
    add(1, 'GEDC')
    add(2, 'VERS', '5.5.1')
    add(2, 'FORM', 'LINEAGE-LINKED')
    add(1, 'CHAR', 'UTF-8')
    add(1, 'LANG', 'Korean')
    # The book's own fields, so that a file sent between two copies of this app
    # comes back as the same book. Other programs pass over tags that begin with _.
    # The book's own fields go in the header's note, the place the standard keeps
    # for describing the file, as plain lines (족보명: …). Other programs show or
    # keep it quietly; a header tag of our own made Gramps report "lines ignored".
    add(1, 'NOTE', book_note(book))
    add(0, 'SUBM', '', '@U1@')
    add(1, 'NAME', '우리의 족보')
    for p in people:
        add(0, 'INDI', '', xref[p['id']])
        value, given, surname = gedcom_name(p['korean_name'])
        add(1, 'NAME', value)
        if given:
            add(2, 'GIVN', given)
        if surname:
            add(2, 'SURN', surname)
        if p['hanja_name'] and p['hanja_name'] != p['korean_name']:
            value, given, surname = gedcom_name(p['hanja_name'])
            add(1, 'NAME', value)
            add(2, 'TYPE', 'aka')
            add(2, 'NOTE', '漢字')
        add(1, 'SEX', {'남': 'M', '여': 'F'}.get(p['gender'], 'U'))
        if p['birth_date']:
            add(1, 'BIRT')
            add(2, 'DATE', to_gedcom_date(p['birth_date']))
        if p['death_date']:
            add(1, 'DEAT')
            add(2, 'DATE', to_gedcom_date(p['death_date']))
        if p['note']:
            add(1, 'NOTE', p['note'])
        # The person's number in this book, so the file can come back into it (REFN is standard).
        add(1, 'REFN', str(p['id']))
        add(2, 'TYPE', 'jocbo')
        add(1, '_GEN', str(p['generation']))
        if p['bon_gwan']:
            add(1, '_BONGWAN', p['bon_gwan'])
        for ref, is_adopted in famc[p['id']]:
            add(1, 'FAMC', ref)
            if is_adopted:
                add(2, 'PEDI', 'adopted')
        for ref in fams[p['id']]:
            add(1, 'FAMS', ref)
    for key, fam in families.items():
        add(0, 'FAM', '', fam_xref[key])
        members = [by_id[m] for m in fam['members']]
        if len(members) == 2:
            a, b = members
            husband, wife = (b, a) if (a['gender'] == '여' and b['gender'] != '여') or (b['gender'] == '남' and a['gender'] != '남') else (a, b)
            add(1, 'HUSB', xref[husband['id']])
            add(1, 'WIFE', xref[wife['id']])
        elif members:
            add(1, 'WIFE' if members[0]['gender'] == '여' else 'HUSB', xref[members[0]['id']])
        for child in fam['children']:
            add(1, 'CHIL', xref[child])
    add(0, 'TRLR')
    return '\r\n'.join(lines) + '\r\n'


# ── GEDCOM 불러오기 ───────────────────────────────────────────────────

LINE = re.compile(r'^\s*(\d{1,2})\s+(?:(@[^@\s]+@)\s+)?([A-Za-z0-9_]+)(?: (.*))?$')


def decode_gedcom(data):
    if data.startswith(b'\xef\xbb\xbf'):
        return data[3:].decode('utf-8', errors='replace')
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16')
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        pass
    try:
        return data.decode('cp949')
    except UnicodeDecodeError:
        return data.decode('latin-1')


def parse_gedcom_lines(text):
    """GEDCOM lines into nested nodes: {'tag', 'xref', 'value', 'children'}."""
    roots, stack, bad = [], [], 0
    for raw in text.splitlines():
        if not raw.strip():
            continue
        found = LINE.match(raw.lstrip('\ufeff'))
        if not found:
            bad += 1
            continue
        level, ref, tag, value = int(found[1]), found[2], found[3].upper(), found[4] or ''
        if tag in ('CONT', 'CONC') and stack and level >= 1:
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                owner = stack[-1][1]
                owner['value'] += ('\n' if tag == 'CONT' else '') + value
                continue
        node = {'tag': tag, 'xref': ref, 'value': value, 'children': []}
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            stack[-1][1]['children'].append(node)
        else:
            roots.append(node)
        stack.append((level, node))
    return roots, bad


RECORDS = {'INDI', 'FAM', 'NOTE', 'SNOTE', 'SOUR', 'OBJE', 'REPO', 'SUBM'}
POINTERS = {'HUSB', 'WIFE', 'CHIL', 'FAMS', 'FAMC'}


def mend_records(roots):
    """Straighten what hand- and AI-written files get wrong before the records are read.

    "0 I1 INDI" (no @) is read as "0 @I1@ INDI", and "1 CHIL I2" as "1 CHIL @I2@".
    A number used for two people (a file put together page by page, each page
    counting from 1) gives the second one its own number, and every pointer goes
    to the record of that number written nearest to it. Returns the numbers used twice.
    """
    for node in roots:
        if not node['xref'] and node['tag'] not in ('HEAD', 'TRLR') and node['value'].strip().upper() in RECORDS:
            node['xref'], node['tag'], node['value'] = f'@{node["tag"]}@', node['value'].strip().upper(), ''
    defs = defaultdict(list)
    for index, node in enumerate(roots):
        if node['xref'] and node['tag'] in ('INDI', 'FAM'):
            defs[(node['tag'], node['xref'])].append(index)
    twice = sorted(xref.strip('@') for (tag, xref), at in defs.items() if len(at) > 1)
    names = {}
    for (tag, xref), at in defs.items():
        for n, index in enumerate(at[1:], start=2):
            fresh = f'@{xref.strip("@")}-{n}@'
            while (tag, fresh) in defs:
                fresh = f'@{fresh.strip("@")}-{n}@'
            names[index] = fresh
    for index, node in enumerate(roots):
        for child in node['children']:
            if child['tag'] not in POINTERS:
                continue
            value = child['value'].strip()
            if value and not value.startswith('@'):
                value = f'@{value}@'
            target = ('FAM' if child['tag'] in ('FAMS', 'FAMC') else 'INDI', value)
            at = defs.get(target, [])
            if len(at) > 1:
                # 쪽마다 사람을 먼저, 가족을 뒤에 적습니다. 가족이 가리키는 사람은 바로 앞에 적힌 그 번호,
                # 사람이 가리키는 가족은 바로 뒤에 적힌 그 번호입니다.
                before, after = [p for p in at if p < index], [p for p in at if p > index]
                if target[0] == 'INDI':
                    chosen = max(before) if before else min(after)
                else:
                    chosen = min(after) if after else max(before)
                value = names.get(chosen, value)
            child['value'] = value
    for index, fresh in names.items():
        roots[index]['xref'] = fresh
    return twice


def generation_of(node):
    """世 as written: 25, 25세, 25世, or an event of type 세/世/세대 (Gramps, other programs)."""
    found = [_custom(node, '_GEN')]
    for event in _subs(node, 'EVEN') + _subs(node, 'FACT'):
        kind = (_sub(event, 'TYPE') or {}).get('value', '').strip().upper()
        if kind in ('세', '世', '세대', '世代', 'GENERATION'):
            found.append(event['value'].strip())
    for value in found:
        match = re.fullmatch(r'\s*(\d{1,3})\s*(?:세|世|대|代)?\s*', value or '')
        if match and 1 <= int(match[1]) <= 200:
            return int(match[1])
    return None


def _sub(node, tag):
    return next((child for child in node['children'] if child['tag'] == tag), None)


def _subs(node, tag):
    return [child for child in node['children'] if child['tag'] == tag]


def _name_text(node):
    value = node['value'].strip()
    surname = (_sub(node, 'SURN') or {}).get('value', '').strip()
    given = (_sub(node, 'GIVN') or {}).get('value', '').strip()
    if '/' in value:
        before, _, rest = value.partition('/')
        inner, _, after = rest.partition('/')
        before, inner, after = before.strip(), inner.strip(), after.strip()
        if HANGUL.search(value) or HANJA.search(value):
            # 전주최씨 /최/ 처럼 이름 칸에 성까지 다 적힌 부인은 이름 칸만 씁니다.
            if inner and before.endswith(('씨', '氏')) and inner in before:
                return re.sub(r'\s+', '', before + after)
            return re.sub(r'\s+', '', inner + before + after)
        return ' '.join(part for part in (before, inner, after) if part)
    if value:
        return re.sub(r'\s+', '', value) if (HANGUL.search(value) or HANJA.search(value)) else value
    if HANGUL.search(surname + given) or HANJA.search(surname + given):
        return surname + given
    return ' '.join(part for part in (given, surname) if part)


def _custom(node, tag):
    """A tag of this app's own, as written (1 _GEN 25) or as Gramps passes it on
    (1 EVEN 25 / 2 TYPE _GEN): it keeps tags it does not know as typed events."""
    direct = _sub(node, tag)
    if direct and direct['value'].strip():
        return direct['value'].strip()
    for event in _subs(node, 'EVEN') + _subs(node, 'FACT'):
        kind = _sub(event, 'TYPE')
        if kind and kind['value'].strip().upper() == tag and event['value'].strip():
            return event['value'].strip()
    return ''


EVENT_NOTES = {'OCCU': '직업', 'EDUC': '학력', 'TITL': '관직·칭호', 'RELI': '종교', 'GRAD': '졸업'}


def gedcom_family(data):
    family = {'book': {}, 'book_key': '', 'people': [], 'parents': [], 'spouses': [], 'warnings': [], 'errors': []}
    text = decode_gedcom(data)
    roots, bad = parse_gedcom_lines(text)
    if not roots or roots[0]['tag'] != 'HEAD':
        family['errors'].append('GEDCOM 파일이 아닙니다. 첫 줄이 "0 HEAD"로 시작해야 합니다.')
        return finish(family)
    if bad:
        family['warnings'].append(f'읽을 수 없는 줄 {bad}개를 건너뛰었습니다.')
    twice = mend_records(roots)
    if twice:
        shown = ', '.join(twice[:10]) + (f' 외 {len(twice) - 10}개' if len(twice) > 10 else '')
        family['warnings'].append(f'같은 번호가 두 번 이상 쓰였습니다({shown}). 쪽마다 번호를 새로 매긴 파일로 보고 '
                                  '서로 다른 사람으로 불러왔으며, 관계는 파일에서 가장 가까이 적힌 사람과 이었습니다. '
                                  '불러온 뒤 이 번호의 사람들이 바르게 이어졌는지 확인해 주십시오.')
    notes ={node['xref']: node['value'] for node in roots if node['tag'] in ('NOTE', 'SNOTE') and node['xref']}

    def note_text(node):
        value = node['value'].strip()
        if re.fullmatch(r'@[^@]+@', value):
            return notes.get(value, '')
        return node['value']

    head = roots[0]
    book_node = _sub(head, '_BOOK')
    head_note = _sub(head, 'NOTE')
    if head_note and head_note['value'].startswith(BOOK_NOTE_FIRST):
        family['book'], family['book_key'] = read_book_note(head_note['value'])
    elif book_node:  # files of 2026.11.1–11.5
        family['book']['title'] = (_sub(book_node, 'TITL') or {}).get('value', '')
        family['book_key'] = (_sub(book_node, '_KEY') or {}).get('value', '').strip()
        for field, tag in BOOK_TAGS:
            family['book'][field] = (_sub(book_node, tag) or {}).get('value', '')
        description = _sub(book_node, 'NOTE')
        family['book']['description'] = description['value'] if description else ''
    else:
        file_node = _sub(head, 'FILE')
        if file_node and file_node['value']:
            family['book']['title'] = re.sub(r'\.ged$', '', Path(file_node['value'].replace('\\', '/')).name, flags=re.I)
    char = (_sub(head, 'CHAR') or {}).get('value', '').upper()
    if char == 'ANSEL' and re.search(r'[\x80-\xff]', text):
        family['warnings'].append('ANSEL 문자 집합 파일이라 일부 특수 문자가 다르게 보일 수 있습니다.')

    # 이 프로그램에서 내보낸 파일이면 모든 항목이 적혀 있으므로, 없는 항목은 비운 것입니다.
    # 다른 프로그램의 파일이면 사람마다 실제로 들어 있는 항목만 "있는 칸"으로 봅니다.
    own_file = bool(family['book_key']) or bool(head_note and head_note['value'].startswith(BOOK_NOTE_FIRST)) or bool(book_node)
    people, keys = family['people'], {}
    fams_order, pedigree = {}, {}
    undated = 0
    for node in roots:
        if node['tag'] != 'INDI' or not node['xref']:
            continue
        key = node['xref'].strip('@')
        person = blank_person(key)
        fams_order[key] = [ref['value'].strip() for ref in _subs(node, 'FAMS')]
        for ref in _subs(node, 'FAMC'):
            pedi = (_sub(ref, 'PEDI') or {}).get('value', '').strip().lower()
            pedigree[(key, ref['value'].strip())] = pedi == 'adopted'
        where = f'{key} 인물'
        texts = []
        for name in _subs(node, 'NAME'):
            texts.append(_name_text(name))
            for variant in name['children']:
                if variant['tag'] in ('FONE', 'ROMN', 'TRAN'):
                    texts.append(_name_text(variant))
        texts = [t for t in texts if t]
        korean = next((t for t in texts if HANGUL.search(t)), '')
        hanja = next((t for t in texts if HANJA.search(t) and not HANGUL.search(t)), '')
        other = next((t for t in texts if not HANGUL.search(t) and not HANJA.search(t)), '')
        person['korean_name'] = korean or (hangul_of(hanja) if hanja else other)
        person['hanja_name'] = hanja
        if other and person['korean_name'] != other:
            add_note(person, f'영문 이름 {other}')
        sex = (_sub(node, 'SEX') or {}).get('value', '').strip().upper()
        person['gender'] = GENDER.get(sex, '미상')
        for tag, field, word in (('BIRT', 'birth_date', '출생'), ('DEAT', 'death_date', '사망')):
            event = _sub(node, tag)
            if not event:
                continue
            when = (_sub(event, 'DATE') or {}).get('value', '').strip()
            if when:
                parsed = from_gedcom_date(when)
                if parsed:
                    person[field] = parsed
                else:
                    add_note(person, f'{word} {when}')
                    undated += 1
            place = (_sub(event, 'PLAC') or {}).get('value', '').strip()
            if place:
                add_note(person, f'{word}지 {place}')
        burial = _sub(node, 'BURI')
        if burial:
            place = (_sub(burial, 'PLAC') or {}).get('value', '').strip()
            if place:
                add_note(person, f'墓 {place}')
        for tag, word in EVENT_NOTES.items():
            for event in _subs(node, tag):
                if event['value'].strip():
                    add_note(person, f'{word} {event["value"].strip()}')
        for note in _subs(node, 'NOTE') + _subs(node, 'SNOTE'):
            add_note(person, note_text(note).strip())
        generation = generation_of(node)
        if generation:
            person['generation'] = generation
        person['bon_gwan'] = _custom(node, '_BONGWAN')
        for ref in _subs(node, 'REFN'):
            kind = _sub(ref, 'TYPE')
            if kind and kind['value'].strip().lower() == 'jocbo':
                person['id'] = person_number(ref['value'])
        settle_dates(person, f'{person["korean_name"] or key}', family['warnings'])
        fit(person, f'{person["korean_name"] or key}', family['warnings'])
        if not own_file:
            person['present'] = ['korean_name'] + [field for field, has in (
                ('hanja_name', person['hanja_name']), ('gender', person['gender'] != '미상'),
                ('birth_date', person['birth_date']), ('death_date', person['death_date']), ('note', person['note']),
                ('bon_gwan', person['bon_gwan']), ('generation', bool(generation))) if has]
        keys[node['xref']] = key
        people.append(person)
    if undated:
        family['warnings'].append(f'정확하지 않은 날짜(ABT, BEF, BET 등) {undated}개는 날짜 칸 대신 기록 칸에 옮겨 적었습니다.')
    # 관계는 가족(FAM)의 HUSB·WIFE·CHIL과 사람(INDI)의 FAMS·FAMC 두 곳에 적힙니다. 한쪽에만 적은
    # 파일(다른 프로그램, AI가 만든 파일)도 있으므로 둘을 합쳐 읽습니다.
    member_of, child_of = defaultdict(list), defaultdict(list)
    for node in roots:
        if node['tag'] == 'INDI' and node['xref']:
            key = node['xref'].strip('@')
            for ref in _subs(node, 'FAMS'):
                member_of[ref['value'].strip()].append(key)
            for ref in _subs(node, 'FAMC'):
                child_of[ref['value'].strip()].append(key)
    missing = 0
    fams = []
    written = {node['xref'] for node in roots if node['tag'] == 'FAM'}
    # 가족 기록 없이 사람 쪽(FAMS·FAMC)에만 적힌 가족도 가족으로 봅니다.
    unwritten = [{'tag': 'FAM', 'xref': ref, 'value': '', 'children': []}
                 for ref in dict.fromkeys(list(member_of) + list(child_of)) if ref not in written]
    for node in roots + unwritten:
        if node['tag'] != 'FAM':
            continue
        couple = [keys.get(child['value'].strip()) for child in node['children'] if child['tag'] in ('HUSB', 'WIFE')]
        kids = [keys.get(child['value'].strip()) for child in node['children'] if child['tag'] == 'CHIL']
        missing += sum(1 for k in couple + kids if k is None)
        couple = [k for k in couple if k]
        couple += [k for k in dict.fromkeys(member_of.get(node['xref'], [])) if k not in couple][:max(0, 2 - len(couple))]
        kids = [k for k in kids if k]
        kids += [k for k in dict.fromkeys(child_of.get(node['xref'], [])) if k not in kids and k not in couple]
        fams.append((node, couple, kids))
    # 부부가 함께 적힌 가족만 혼인으로 셉니다(한쪽 부모만 있는 가족은 혼인 순서에 넣지 않음).
    spouse_fams = {node['xref'] for node, couple, _ in fams if len(couple) == 2}
    for node, couple, kids in fams:
        if len(couple) == 2:
            # 혼인 순서: 그 사람의 가족(FAMS) 가운데 몇 번째인가. 혼인이 여러 번인 쪽을 따릅니다.
            order = 0
            for one in couple:
                married = [ref for ref in fams_order.get(one, []) if ref in spouse_fams]
                if len(married) > 1 and node['xref'] in married:
                    order = married.index(node['xref']) + 1
                    break
            family['spouses'].append([couple[0], couple[1], order or 1])
        for kid in kids:
            if kid:
                adopted = int(pedigree.get((kid, node['xref']), False))
                for parent in couple:
                    family['parents'].append([parent, kid, adopted])
    if missing:
        family['warnings'].append(f'가족(FAM) 기록이 가리키는 사람 {missing}명을 파일에서 찾지 못해 그 관계는 건너뛰었습니다.')
    if not own_file:
        join_page_copies(family)
        unwind_wife_as_child(family)
    return finish(family)


def _surname(person):
    for name in (person.get('hanja_name'), person.get('korean_name')):
        if name:
            return name[0]
    return ''


def join_page_copies(family):
    """옛 족보는 쪽이 바뀌면 그 쪽의 첫 사람을 다시 적습니다. 파일로 옮기면 같은 사람이 둘이 되어,
    앞쪽의 그 사람에게는 자녀가 없고 뒤쪽의 그 사람에게는 부모가 없어 자손이 통째로 끊깁니다.

    이름(한자가 있으면 한자도)과 성별이 같은 남자, 적힌 세가 있으면 세도 같고, 한쪽은 자녀가 없고
    다른 쪽은 부모가 없으며, 그런 짝이 하나뿐일 때만 한 사람으로 합칩니다. 합친 것은 알림에 적습니다.
    """
    people = family['people']
    has_parent = {child for _, child, *_ in family['parents']}
    has_child = {parent for parent, *_ in family['parents']}

    def fits(a, b):
        same_name = a['korean_name'] == b['korean_name'] and (not a['hanja_name'] or not b['hanja_name'] or a['hanja_name'] == b['hanja_name'])
        same_gen = not a.get('generation') or not b.get('generation') or a['generation'] == b['generation']
        # 부인(○씨)과 딸은 합치지 않습니다. 성별을 적지 않은 파일은 이름만으로 봅니다.
        return (same_name and same_gen and a['gender'] == b['gender'] and a['gender'] != '여'
                and len(a['korean_name']) >= 2 and not a['korean_name'].endswith(('씨', '氏')))

    leaves = defaultdict(list)
    for p in people:
        if p['key'] in has_parent and p['key'] not in has_child:
            leaves[p['korean_name']].append(p)
    heads = defaultdict(list)
    for p in people:
        if p['key'] not in has_parent and p['key'] in has_child:
            heads[p['korean_name']].append(p)
    into = {}
    for name, copies in heads.items():
        originals = [o for o in leaves.get(name, []) if any(fits(o, c) for c in copies)]
        copies = [c for c in copies if any(fits(o, c) for o in originals)]
        if len(originals) == 1 and len(copies) == 1:
            into[copies[0]['key']] = originals[0]['key']
    if not into:
        return
    by_key = {p['key']: p for p in people}
    lines = []
    for copy, original in into.items():
        a, b = by_key[original], by_key[copy]
        for field in ('hanja_name', 'birth_date', 'death_date', 'bon_gwan'):
            if not a.get(field) and b.get(field):
                a[field] = b[field]
        if b.get('note') and b['note'] not in (a.get('note') or ''):
            add_note(a, b['note'])
        if not a.get('generation') and b.get('generation'):
            a['generation'] = b['generation']
        if a.get('present') is not None and b.get('present') is not None:
            a['present'] = sorted(set(a['present']) | set(b['present']))
        lines.append(f'{who(a, original)} = {who(b, copy)}')
    family['people'] = [p for p in people if p['key'] not in into]
    family['parents'] = [[into.get(a, a), into.get(b, b), *rest] for a, b, *rest in family['parents']]
    family['spouses'] = [[into.get(a, a), into.get(b, b), *rest] for a, b, *rest in family['spouses']]
    family['warnings'].insert(0, f'쪽이 바뀌며 다시 적힌 것으로 보이는 같은 사람 {len(lines)}쌍을 한 사람으로 합쳤습니다'
                                 f'(앞쪽에는 자녀가 없고 뒤쪽에는 부모가 없는 같은 이름): {", ".join(lines[:20])}'
                                 + (f' 외 {len(lines) - 20}쌍' if len(lines) > 20 else '') + '. 다른 사람이면 불러온 뒤 나눠 주십시오.')


def unwind_wife_as_child(family):
    """配(부인)를 자녀 줄로 잘못 옮기면 며느리가 시아버지의 자녀이면서 그 아들의 아내가 됩니다.

    부부가 같은 부모를 두고 있으면, 성이 그 부모(아버지)와 다른 쪽의 부모 관계를 뺍니다.
    누구인지 가릴 수 없으면 알림만 남깁니다.
    """
    by_key = {p['key']: p for p in family['people']}
    parents_of = defaultdict(set)
    for parent, child, *_ in family['parents']:
        parents_of[child].add(parent)
    drop, unsure = set(), []
    for one, other, *_ in family['spouses']:
        shared = parents_of[one] & parents_of[other]
        if not shared:
            continue
        clan = {_surname(by_key[p]) for p in shared if by_key[p]['gender'] == '남'} or {_surname(by_key[p]) for p in shared}
        outsiders = [k for k in (one, other) if _surname(by_key[k]) not in clan]
        if len(outsiders) == 1:
            drop.update((p, outsiders[0]) for p in parents_of[outsiders[0]])
        else:
            unsure.append(f'{who(by_key[one], one)} ↔ {who(by_key[other], other)}')
    if drop:
        family['parents'] = [l for l in family['parents'] if (l[0], l[1]) not in drop]
        wives = sorted({c for _, c in drop})
        family['warnings'].insert(0, f'부부가 같은 부모의 자녀로도 적혀 있어, 성이 다른 배우자 {len(wives)}명의 부모 관계를 뺐습니다'
                                     f'(配를 자녀 줄로 옮긴 것으로 보임): {", ".join(who(by_key[k], k) for k in wives[:20])}.')
    if unsure:
        family['warnings'].insert(0, f'부부가 같은 부모의 자녀로도 적혀 있습니다. 족보 원본과 맞춰 확인해 주십시오: {", ".join(unsure[:20])}.')


# ── 파일 종류 가리기 ──────────────────────────────────────────────────

def read_family(name, data):
    lower = (name or '').lower()
    if data[:4] == b'\xd0\xcf\x11\xe0':
        raise ExchangeError('옛 엑셀 형식(.xls)은 읽지 못합니다. 엑셀에서 "Excel 통합 문서(.xlsx)"로 다시 저장해 주십시오.')
    if lower.endswith(('.ged', '.gedcom')) or re.match(rb'^(\xef\xbb\xbf)?\s*0\s+HEAD', data[:64]):
        family = gedcom_family(data)
        family['format'] = 'gedcom'
    elif data[:2] == b'PK':
        program = read_xlsx(data, PROGRAM_SHEET, fallback=False)
        if program:
            info, key, extra = program_info(program)
        else:  # 2026.11.1~11.6 파일: 족보 정보·추가 관계 시트
            info, key = book_info(read_xlsx(data, INFO_SHEET, fallback=False))
            extra = read_xlsx(data, EXTRA_SHEET, fallback=False)
        family = tree_family(read_xlsx(data), extra)
        family['format'] = 'xlsx'
        if info:
            family['book'] = tidy_book(info)
        family['book_key'] = key
    elif lower.endswith('.csv'):
        family = tree_family(read_csv(data))
        family['format'] = 'csv'
    else:
        raise ExchangeError('GEDCOM(.ged), 엑셀(.xlsx), CSV(.csv) 파일만 불러올 수 있습니다.')
    if not family['book'].get('title') or family['book']['title'] == '불러온 족보':
        stem = re.sub(r'\.[^.]+$', '', Path((name or '').replace('\\', '/')).name)
        # A sheet sent out by this app is named '<족보명> 가계도.xlsx'.
        stem = re.sub(r'\s*가계도(\s*\(\d+\))?$', '', stem)
        family['book']['title'] = stem[:200] or '불러온 족보'
    return family
