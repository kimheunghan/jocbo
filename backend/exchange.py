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
    found = re.fullmatch(r'(\d{1,2})\s*월\s*(\d{1,2})\s*일?', text)
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
    return {'key': key, 'korean_name': '', 'hanja_name': '', 'bon_gwan': '', 'generation': None,
            'gender': '미상', 'birth_date': '', 'death_date': '', 'note': ''}


GENDER = {'남': '남', '男': '남', 'M': '남', 'MALE': '남', '여': '여', '女': '여', 'F': '여', 'FEMALE': '여'}


# ── 세대 ──────────────────────────────────────────────────────────────

def settle_generations(people, parents, spouses, base=1):
    """Give everyone a 世: the one written down where there is one, else from the family.

    A child stands at least one below each parent and husband and wife stand
    together, as the page itself draws them. A parent line that loops back on
    itself, or one that cannot be laid out, is an error.
    """
    keys = [p['key'] for p in people]
    gen = {p['key']: p.get('generation') for p in people}
    children = defaultdict(list)
    has_parent = set()
    for parent, child in parents:
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
                raise ExchangeError('부모-자녀 관계가 순환합니다. 어떤 사람이 자기 조상으로 이어져 있습니다.')
            elif nxt not in state:
                state[nxt] = 1
                stack.append((nxt, iter(children[nxt])))
    while any(value is None for value in gen.values()):
        changed = True
        while changed:
            changed = False
            for parent, child in parents:
                if gen[parent] is not None and gen[child] is None:
                    gen[child], changed = gen[parent] + 1, True
                elif gen[child] is not None and gen[parent] is None:
                    gen[parent], changed = gen[child] - 1, True
            for one, other in spouses:
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
        for parent, child in parents:
            if gen[child] < gen[parent] + 1:
                gen[child], changed = gen[parent] + 1, True
        for one, other in spouses:
            if gen[one] != gen[other]:
                gen[one] = gen[other] = max(gen[one], gen[other])
                changed = True
        if not changed:
            break
    else:
        raise ExchangeError('세대를 맞출 수 없습니다. 부부 관계와 부모 관계가 서로 맞지 않는 사람이 있습니다.')
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
    seen = set()
    parents = []
    for parent, child in family['parents']:
        if parent in keys and child in keys and parent != child and (parent, child) not in seen:
            seen.add((parent, child))
            parents.append([parent, child])
    pairs = set()
    spouses = []
    for one, other in family['spouses']:
        pair = tuple(sorted((one, other)))
        if one in keys and other in keys and one != other and pair not in pairs:
            pairs.add(pair)
            spouses.append(list(pair))
    family['parents'], family['spouses'] = parents, spouses
    if not family['people'] and not family['errors']:
        family['errors'].append('불러올 사람이 없습니다.')
    if len(family['people']) > MAX_PEOPLE:
        family['errors'].append(f'한 번에 {MAX_PEOPLE}명까지 불러올 수 있습니다.')
    if not family['errors']:
        try:
            settle_generations(family['people'], parents, spouses)
        except ExchangeError as error:
            family['errors'].append(str(error))
    family['book'] = tidy_book(family['book'])
    return family


def tidy_book(book):
    """Every field of a book, each within its length, with a title and a volume."""
    book = {field: str(book.get(field, '') or '').strip()[:limit] for field, limit in BOOK_LIMITS.items()}
    book['title'] = book['title'] or '불러온 족보'
    book['volume'] = book['volume'] or '1'
    return book


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
    for r in book['relations']:
        if r['kind'] != 'spouse' or r['source_id'] not in by_id or r['target_id'] not in by_id:
            continue
        a, b = by_id[r['source_id']], by_id[r['target_id']]
        sa, sb = score(a), score(b)
        host, guest = (a, b) if (sa > sb or (sa == sb and a['id'] < b['id'])) else (b, a)
        married[host['id']].append(guest['id'])
        host_of[guest['id']] = host['id']

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
                rows.append({'kind': 'child-ref', 'pid': node, 'depth': depth, 'other': other})
                continue
            placed.add(node)
            rows.append({'kind': 'person', 'pid': node, 'depth': depth, 'other': other})
            mates = [m for m in married.get(node, []) if m != node]
            for mate in mates:
                if mate in placed:
                    rows.append({'kind': 'spouse-ref', 'pid': mate, 'depth': depth})
                else:
                    placed.add(mate)
                    rows.append({'kind': 'spouse', 'pid': mate, 'depth': depth})
            pending = []
            for child in sorted(set(children_of[node]), key=sibling_key):
                mate = next((m for m in parents_of[child] if m in mates), None)
                others = [m for m in parents_of[child] if m != node]
                other_parent = mate if mate is not None else ('(미상)' if mates and not others else None)
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


STYLE = {'plain': 0, 'head': 1, 'text': 2, 'guest': 3, 'ref': 4}


def _sheet_xml(rows, widths, text_columns=()):
    out = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
           '</sheetView></sheetViews><sheetFormatPr defaultRowHeight="18"/><cols>']
    for index, width in enumerate(widths):
        # Date columns stay text, so a date typed in later is not turned into a number.
        style = f' style="{STYLE["text"]}"' if index in text_columns else ''
        out.append(f'<col min="{index + 1}" max="{index + 1}" width="{width}" customWidth="1"{style}/>')
    out.append('</cols><sheetData>')
    for r, row in enumerate(rows, start=1):
        out.append(f'<row r="{r}">')
        for c, cell in enumerate(row):
            if cell is None:
                continue
            value, style = cell if isinstance(cell, tuple) else (cell, 'plain')
            if value is None or value == '':
                continue
            ref = f'{column_name(c)}{r}'
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out.append(f'<c r="{ref}" s="{STYLE[style]}"><v>{value}</v></c>')
            else:
                text = escape(_BAD_XML.sub('', str(value)))
                out.append(f'<c r="{ref}" s="{STYLE[style]}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>')
        out.append('</row>')
    out.append('</sheetData></worksheet>')
    return ''.join(out)


_STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<fonts count="4"><font><sz val="11"/><name val="맑은 고딕"/><family val="3"/></font>'
           '<font><b/><sz val="11"/><name val="맑은 고딕"/><family val="3"/></font>'
           '<font><sz val="11"/><color rgb="FF6B5B45"/><name val="맑은 고딕"/><family val="3"/></font>'
           '<font><i/><sz val="11"/><color rgb="FF8A8A8A"/><name val="맑은 고딕"/><family val="3"/></font></fonts>'
           '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
           '<fill><patternFill patternType="solid"><fgColor rgb="FFEFE6D4"/><bgColor indexed="64"/></patternFill></fill></fills>'
           '<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
           '<border><left/><right/><top/><bottom style="thin"><color rgb="FF9C8A6A"/></bottom><diagonal/></border></borders>'
           '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
           '<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
           '<xf numFmtId="49" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyNumberFormat="1"/>'
           '<xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
           '<xf numFmtId="49" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyNumberFormat="1"/>'
           '<xf numFmtId="49" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1" applyNumberFormat="1"/></cellXfs>'
           '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')


def write_xlsx(sheets):
    """sheets: [(name, rows, widths, text_columns)] → the bytes of an .xlsx file."""
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
                   + ''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i, (name, *_) in enumerate(sheets, start=1))
                   + '</sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels',
                   '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + ''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                             for i in range(1, len(sheets) + 1))
                   + f'<Relationship Id="rId{len(sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
                   '</Relationships>')
        z.writestr('xl/styles.xml', _STYLES)
        for i, (_, rows, widths, text_columns) in enumerate(sheets, start=1):
            z.writestr(f'xl/worksheets/sheet{i}.xml', _sheet_xml(rows, widths, text_columns))
    return buffer.getvalue()


# ── 엑셀 가계도 내보내기 ──────────────────────────────────────────────

DETAIL_HEADS = ['세', '성별', '본관', '출생일', '사망일', '다른 부모', '기록']
TREE_SHEET = '가계도'


def tree_xlsx(book):
    rows, by_id, parents_of, spouses_of = lay_out(book)
    depth = max((row['depth'] for row in rows), default=0) + 1
    tops = [by_id[row['pid']]['generation'] for row in rows if row['depth'] == 0 and row['kind'] == 'person']
    base = min(tops, default=1)
    row_of = {}
    for number, row in enumerate(rows, start=2):
        if row['kind'] in ('person', 'spouse'):
            row_of[row['pid']] = number
    head = [(f'{base + d}세', 'head') for d in range(depth)] + [(h, 'head') for h in DETAIL_HEADS]
    sheet = [head]
    for row in rows:
        person = by_id[row['pid']]
        cells = [None] * (depth + len(DETAIL_HEADS))
        name = label(person)
        if row['kind'] == 'person':
            cells[row['depth']] = name
        elif row['kind'] == 'spouse':
            cells[row['depth']] = ('配 ' + name, 'guest')
        elif row['kind'] == 'spouse-ref':
            cells[row['depth']] = (f'配 {name} → {row_of[row["pid"]]}행', 'ref')
        else:
            cells[row['depth']] = (f'{name} → {row_of[row["pid"]]}행', 'ref')
        if row['kind'] in ('person', 'spouse'):
            other = row.get('other')
            other_text = other if isinstance(other, str) else (label(by_id[other]) if other is not None else '')
            details = [person['generation'], person['gender'] if person['gender'] != '미상' else '',
                       person['bon_gwan'], person['birth_date'], person['death_date'], other_text, person['note']]
            for offset, value in enumerate(details):
                cells[depth + offset] = (value, 'text') if isinstance(value, str) else value
        sheet.append(cells)
    widths = [16] * depth + [6, 6, 10, 12, 12, 16, 50]
    text_columns = {depth + 3, depth + 4}

    # A plain list beside it, for sorting and filtering; it is not read back.
    listing = [[(h, 'head') for h in ['행', '세', '한글명', '한자명', '성별', '본관', '아버지', '어머니', '배우자', '출생일', '사망일', '기록']]]
    for number, row in enumerate(rows, start=2):
        if row['kind'] not in ('person', 'spouse'):
            continue
        p = by_id[row['pid']]
        mothers = [by_id[x] for x in parents_of[p['id']] if by_id[x]['gender'] == '여']
        fathers = [by_id[x] for x in parents_of[p['id']] if by_id[x]['gender'] != '여']
        listing.append([number, p['generation'], p['korean_name'], p['hanja_name'], p['gender'], p['bon_gwan'],
                        ', '.join(label(x) for x in fathers), ', '.join(label(x) for x in mothers),
                        ', '.join(label(by_id[x]) for x in spouses_of[p['id']]),
                        (p['birth_date'], 'text'), (p['death_date'], 'text'), p['note']])
    info = [[('항목', 'head'), ('내용', 'head')]] + [[word, (book.get(field) or '', 'text')] for field, word in BOOK_WORDS]
    return write_xlsx([(TREE_SHEET, sheet, widths, text_columns),
                       ('인물 목록', listing, [6, 6, 10, 12, 6, 10, 16, 16, 20, 12, 12, 50], {9, 10}),
                       (INFO_SHEET, info, [14, 60], {1})])


# The book's own fields on a sheet of their own, so a sheet sent out comes back
# as the same book, as a GEDCOM file does.
INFO_SHEET = '족보 정보'
BOOK_WORDS = [('title', '족보명'), ('clan_name', '성씨/가문'), ('bon_gwan', '본관'), ('branch_name', '파명'),
              ('volume', '권'), ('page', '페이지'), ('page_breaks', '쪽 이어짐'), ('founder', '시조'),
              ('lineage', '계통'), ('description', '설명')]


def book_info(rows):
    words = {word: field for field, word in BOOK_WORDS}
    book = {}
    for row in rows[1:]:
        if len(row) >= 2 and _cell_text(row[0]) in words:
            value = row[1]
            book[words[_cell_text(row[0])]] = value.strip() if isinstance(value, str) else _cell_text(value)
    return book


def template_gedcom():
    """The same made-up family as the Excel template, as a GEDCOM file."""
    rows = [  # id, 한글명, 한자명, 世, 성별, 본관, 출생, 사망, 기록
        (1, '김시조', '金始祖', 1, '남', '金海', '1820', '1885-03', '字 ○○ · 예시 인물입니다'),
        (2, '이씨', '李氏', 1, '여', '全州', '', '', ''),
        (3, '김일남', '金一男', 2, '남', '', '1845-05-02', '', ''),
        (4, '박씨', '朴氏', 2, '여', '密陽', '', '', ''),
        (5, '김장손', '', 3, '남', '', '', '', ''),
        (6, '김차손', '', 3, '남', '', '', '', ''),
        (7, '김이남', '金二男', 2, '남', '', '', '', ''),
    ]
    keys = ['id', 'korean_name', 'hanja_name', 'generation', 'gender', 'bon_gwan', 'birth_date', 'death_date', 'note']
    links = [(1, 2, 'spouse'), (3, 4, 'spouse'), (1, 3, 'parent'), (2, 3, 'parent'), (1, 7, 'parent'), (2, 7, 'parent'),
             (3, 5, 'parent'), (4, 5, 'parent'), (3, 6, 'parent'), (4, 6, 'parent')]
    book = {'title': 'GEDCOM 양식', 'clan_name': '金氏', 'bon_gwan': '金海', 'volume': '1',
            'description': '불러오기 예시입니다. 모든 인물은 가상 인물입니다.',
            'persons': [dict(zip(keys, row)) for row in rows],
            'relations': [{'source_id': a, 'target_id': b, 'kind': kind} for a, b, kind in links]}
    return gedcom(book)


def template_xlsx():
    """An empty tree with a made-up family, to show how the sheet is filled in."""
    head = [(h, 'head') for h in ['1세', '2세', '3세', *DETAIL_HEADS]]
    rows = [head,
            ['金始祖(김시조)', None, None, 1, '남', '金海', '1820', '1885-03', None, '字 ○○ · 예시 인물입니다'],
            [('配 李氏(이씨)', 'guest'), None, None, 1, '여', '全州', None, None, None, None],
            [None, '金一男(김일남)', None, 2, '남', None, '1845-05-02', None, None, None],
            [None, ('配 朴氏(박씨)', 'guest'), None, 2, '여', '密陽', None, None, None, None],
            [None, None, '김장손', 3, '남', None, None, None, None, '이름만 적어도 됩니다'],
            [None, None, '김차손', 3, '남', None, None, None, None, None],
            [None, '金二男(김이남)', None, 2, '남', None, None, None, None, '형제는 같은 열에 이어 적습니다'],
            ]
    guide = [[('불러오기 규칙', 'head')],
             ['한 행에 한 사람을 적습니다.'],
             ['이름을 적은 열이 세대입니다. 오른쪽으로 한 칸 들어가면 바로 위 사람의 자녀입니다.'],
             ['배우자는 그 사람 바로 아래 행, 같은 열에 "配 " 또는 "배 "를 앞에 붙여 적습니다.'],
             ['이름은 金一男(김일남), 김일남(金一男), 김일남, 金一男 어느 것이든 됩니다.'],
             ['배우자가 둘 이상이면 자녀 행의 "다른 부모" 칸에 그 배우자 이름을 적습니다. 모르면 (미상)이라고 적습니다.'],
             ['날짜는 1956, 1956-03, 1956-03-02, 1956.3.2, 3월 2일처럼 아는 만큼 적습니다.'],
             ['"세" 칸을 비우면 첫 행 머리글(1세, 2세 …)을 따릅니다.'],
             ['"→ 12행"은 이미 다른 행에 적힌 사람을 가리킵니다.'],
             ['불러오기는 "가계도" 시트만 읽습니다.']]
    return write_xlsx([(TREE_SHEET, rows, [16, 16, 16, 6, 6, 10, 12, 12, 16, 50], {6, 7}),
                       ('작성 안내', guide, [110], ())])


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
               '다른부모': 'other', '어머니': 'other', '배우자부모': 'other',
               '기록': 'note', '메모': 'note', '비고': 'note', '한자명': 'hanja_name', '한자': 'hanja_name'}
SPOUSE_MARK = re.compile(r'^\s*(?:配|배\s*[):.]|배\s+)\s*')
REFERENCE = re.compile(r'\s*(?:→|->)\s*(\d+)\s*행\s*$')


def _cell_text(value):
    if value is None:
        return ''
    if isinstance(value, float):
        return str(int(value)) if value == int(value) else str(value)
    return str(value).strip()


def _head_name(value):
    return re.sub(r'\s+', '', _cell_text(value))


def tree_family(rows):
    """Read the tree sheet into a family; row numbers in messages are the sheet's own."""
    family = {'book': {}, 'people': [], 'parents': [], 'spouses': [], 'warnings': [], 'errors': []}
    rows = [list(row) for row in rows]
    if not rows:
        family['errors'].append('엑셀 시트가 비어 있습니다.')
        return finish(family)
    width = max(len(row) for row in rows)
    for row in rows:
        row.extend([None] * (width - len(row)))
    first = [_head_name(v) for v in rows[0]]
    detail = {index: HEAD_FIELDS[name] for index, name in enumerate(first) if name in HEAD_FIELDS}
    has_head = bool(detail) or any(re.fullmatch(r'\d+[세世]', name) for name in first)
    tree_end = min(detail) if detail else width
    if tree_end == 0:
        family['errors'].append('1행: 첫 열에 이름을 적을 세대 열이 없습니다. 세(世)·성별 같은 칸은 이름 열들 오른쪽에 둡니다.')
        return finish(family)
    base_match = re.match(r'(\d+)', first[0]) if has_head else None
    base = int(base_match[1]) if base_match else 1
    start = 1 if has_head else 0

    last = {}            # column → key of the latest person written there
    mates = defaultdict(list)
    row_person = {}      # sheet row → key
    pending_refs = []    # (sheet row, kind, anchor key, target row, other)
    people = family['people']
    errors, warnings = family['errors'], family['warnings']

    for index in range(start, len(rows)):
        row, number = rows[index], index + 1
        names = [(c, _cell_text(rows[index][c])) for c in range(tree_end) if _cell_text(rows[index][c])]
        if not names:
            if any(_cell_text(v) for v in row[tree_end:]):
                warnings.append(f'{number}행: 이름 칸이 비어 있어 이 행을 건너뛰었습니다.')
            continue
        if len(names) > 1:
            errors.append(f'{number}행: 이름이 두 칸 이상에 적혀 있습니다. 한 행에는 한 사람만 적습니다.')
            continue
        column, text = names[0]
        spouse = bool(SPOUSE_MARK.match(text))
        if spouse:
            text = SPOUSE_MARK.sub('', text, count=1)
        reference = REFERENCE.search(text)
        if reference:
            text = text[:reference.start()].strip()
        if spouse:
            anchor = last.get(column)
            if anchor is None:
                errors.append(f'{number}행: 배우자(配) 위에 같은 열의 사람이 없습니다. 배우자는 그 사람 바로 아래, 같은 열에 적습니다.')
                continue
        else:
            anchor = None
            if column > 0:
                anchor = last.get(column - 1)
                if anchor is None:
                    errors.append(f'{number}행: 바로 왼쪽 열에 부모가 없습니다. 자녀는 부모보다 한 칸만 오른쪽에 적습니다.')
                    continue
        cells = {field: row[i] for i, field in detail.items()}
        other = _cell_text(cells.get('other'))
        if reference:
            pending_refs.append((number, 'spouse' if spouse else 'child', anchor, int(reference[1]), other))
            if not spouse:
                last[column] = None
                for c in [c for c in last if c > column]:
                    del last[c]
            continue
        key = f'r{number}'
        person = blank_person(key)
        person['korean_name'], person['hanja_name'] = split_name(text)
        if 'hanja_name' in detail and _cell_text(cells.get('hanja_name')):
            person['hanja_name'] = _cell_text(cells['hanja_name'])
        gen_text = _cell_text(cells.get('generation'))
        gen_number = re.match(r'(\d+)', gen_text)
        person['generation'] = int(gen_number[1]) if gen_number else base + column
        person['gender'] = GENDER.get(_cell_text(cells.get('gender')).upper(), '미상')
        person['bon_gwan'] = _cell_text(cells.get('bon_gwan'))
        note = cells.get('note')
        person['note'] = str(note).strip() if isinstance(note, str) else _cell_text(note)
        for field, word in (('birth_date', '출생'), ('death_date', '사망')):
            value = cells.get(field)
            parsed = text_date(value)
            if parsed is None:
                add_note(person, f'{word} {_cell_text(value)}')
                warnings.append(f'{number}행: {word}일 "{_cell_text(value)}"을(를) 날짜로 읽지 못해 기록(메모)에 옮겼습니다.')
            else:
                person[field] = parsed
        where = f'{number}행'
        settle_dates(person, where, warnings)
        fit(person, where, warnings)
        people.append(person)
        row_person[number] = key
        if spouse:
            family['spouses'].append([anchor, key])
            mates[anchor].append(key)
        else:
            if anchor is not None:
                _link_child(family, anchor, key, other, mates, number, people)
            last[column] = key
            for c in [c for c in last if c > column]:
                del last[c]

    for number, kind, anchor, target_row, other in pending_refs:
        target = row_person.get(target_row)
        if target is None:
            errors.append(f'{number}행: "→ {target_row}행"이 가리키는 행에 사람이 없습니다.')
            continue
        if kind == 'spouse':
            family['spouses'].append([anchor, target])
            mates[anchor].append(target)
        elif anchor is not None:
            _link_child(family, anchor, target, other, mates, number, people)
    if len(people) > MAX_PEOPLE:
        errors.append(f'한 번에 {MAX_PEOPLE}명까지 불러올 수 있습니다.')
    return finish(family)


def _link_child(family, parent, child, other, mates, number, people):
    family['parents'].append([parent, child])
    spouses = mates.get(parent, [])
    if other in ('(미상)', '미상', '-'):
        return
    if other:
        by_key = {p['key']: p for p in people}
        korean, hanja = split_name(other)
        found = [m for m in spouses if other in (label(by_key[m]), by_key[m]['korean_name'], by_key[m]['hanja_name'])
                 or (korean and korean == by_key[m]['korean_name']) or (hanja and hanja == by_key[m]['hanja_name'])]
        if found:
            family['parents'].append([found[0], child])
        else:
            family['warnings'].append(f'{number}행: 다른 부모 "{other}"를 배우자 가운데서 찾지 못해 한쪽 부모만 이었습니다.')
        return
    if len(spouses) == 1:
        family['parents'].append([spouses[0], child])
    elif len(spouses) > 1:
        family['warnings'].append(f'{number}행: 배우자가 둘 이상이라 어느 쪽 자녀인지 알 수 없어 한쪽 부모만 이었습니다. "다른 부모" 칸에 이름을 적어 주십시오.')


# ── GEDCOM 내보내기 ───────────────────────────────────────────────────

BOOK_TAGS = [('clan_name', '_CLAN'), ('bon_gwan', '_BONGWAN'), ('branch_name', '_BRANCH'), ('volume', '_VOLUME'),
             ('founder', '_FOUNDER'), ('page', '_PAGE'), ('lineage', '_LINEAGE'), ('page_breaks', '_PAGEBREAKS')]
SURNAMES_TWO = {'남궁', '제갈', '선우', '황보', '독고', '사공', '서문', '동방', '어금', '망절', '장곡',
                '南宮', '諸葛', '鮮于', '皇甫', '獨孤', '司空', '西門', '東方'}


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
    for r in book['relations']:
        if r['source_id'] not in by_id or r['target_id'] not in by_id:
            continue
        if r['kind'] == 'parent':
            parents_of[r['target_id']].append(r['source_id'])
        else:
            spouse_pairs.append(tuple(sorted((r['source_id'], r['target_id']))))
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
            fams[member].append(fam_xref[key])
        for child in fam['children']:
            famc[child].append(fam_xref[key])

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
    add(1, '_BOOK')
    add(2, 'TITL', book.get('title', ''))
    for field, tag in BOOK_TAGS:
        if book.get(field):
            add(2, tag, book[field])
    if book.get('description'):
        add(2, 'NOTE', book['description'])
    add(0, 'SUBM', '', '@U1@')
    add(1, 'NAME', '우리의 족보')
    for p in people:
        add(0, 'INDI', '', xref[p['id']])
        surname, given = name_parts(p['korean_name'])
        add(1, 'NAME', f'{given} /{surname}/'.strip() if surname else p['korean_name'])
        if surname:
            add(2, 'GIVN', given)
            add(2, 'SURN', surname)
        if p['hanja_name'] and p['hanja_name'] != p['korean_name']:
            surname, given = name_parts(p['hanja_name'])
            add(1, 'NAME', f'{given} /{surname}/'.strip() if surname else p['hanja_name'])
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
        add(1, '_GEN', str(p['generation']))
        if p['bon_gwan']:
            add(1, '_BONGWAN', p['bon_gwan'])
        for ref in famc[p['id']]:
            add(1, 'FAMC', ref)
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
            return re.sub(r'\s+', '', inner + before + after)
        return ' '.join(part for part in (before, inner, after) if part)
    if value:
        return re.sub(r'\s+', '', value) if (HANGUL.search(value) or HANJA.search(value)) else value
    if HANGUL.search(surname + given) or HANJA.search(surname + given):
        return surname + given
    return ' '.join(part for part in (given, surname) if part)


EVENT_NOTES = {'OCCU': '직업', 'EDUC': '학력', 'TITL': '관직·칭호', 'RELI': '종교', 'GRAD': '졸업'}


def gedcom_family(data):
    family = {'book': {}, 'people': [], 'parents': [], 'spouses': [], 'warnings': [], 'errors': []}
    text = decode_gedcom(data)
    roots, bad = parse_gedcom_lines(text)
    if not roots or roots[0]['tag'] != 'HEAD':
        family['errors'].append('GEDCOM 파일이 아닙니다. 첫 줄이 "0 HEAD"로 시작해야 합니다.')
        return finish(family)
    if bad:
        family['warnings'].append(f'읽을 수 없는 줄 {bad}개를 건너뛰었습니다.')
    notes = {node['xref']: node['value'] for node in roots if node['tag'] in ('NOTE', 'SNOTE') and node['xref']}

    def note_text(node):
        value = node['value'].strip()
        if re.fullmatch(r'@[^@]+@', value):
            return notes.get(value, '')
        return node['value']

    head = roots[0]
    book_node = _sub(head, '_BOOK')
    if book_node:
        family['book']['title'] = (_sub(book_node, 'TITL') or {}).get('value', '')
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

    people, keys = family['people'], {}
    undated = 0
    for node in roots:
        if node['tag'] != 'INDI' or not node['xref']:
            continue
        key = node['xref'].strip('@')
        person = blank_person(key)
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
        generation = (_sub(node, '_GEN') or {}).get('value', '').strip()
        if generation.isdigit() and 1 <= int(generation) <= 200:
            person['generation'] = int(generation)
        person['bon_gwan'] = (_sub(node, '_BONGWAN') or {}).get('value', '').strip()
        settle_dates(person, f'{person["korean_name"] or key}', family['warnings'])
        fit(person, f'{person["korean_name"] or key}', family['warnings'])
        keys[node['xref']] = key
        people.append(person)
    if undated:
        family['warnings'].append(f'정확하지 않은 날짜(ABT, BEF, BET 등) {undated}개는 날짜 칸 대신 기록(메모)에 옮겼습니다.')
    missing = 0
    for node in roots:
        if node['tag'] != 'FAM':
            continue
        couple = [keys.get(child['value'].strip()) for child in node['children'] if child['tag'] in ('HUSB', 'WIFE')]
        kids = [keys.get(child['value'].strip()) for child in node['children'] if child['tag'] == 'CHIL']
        missing += sum(1 for k in couple + kids if k is None)
        couple = [k for k in couple if k]
        if len(couple) == 2:
            family['spouses'].append(couple)
        for kid in kids:
            if kid:
                for parent in couple:
                    family['parents'].append([parent, kid])
    if missing:
        family['warnings'].append(f'가족(FAM) 기록이 가리키는 사람 {missing}명을 파일에서 찾지 못해 그 관계는 건너뛰었습니다.')
    return finish(family)


# ── 파일 종류 가리기 ──────────────────────────────────────────────────

def read_family(name, data):
    lower = (name or '').lower()
    if data[:4] == b'\xd0\xcf\x11\xe0':
        raise ExchangeError('옛 엑셀 형식(.xls)은 읽지 못합니다. 엑셀에서 "Excel 통합 문서(.xlsx)"로 다시 저장해 주십시오.')
    if lower.endswith(('.ged', '.gedcom')) or re.match(rb'^(\xef\xbb\xbf)?\s*0\s+HEAD', data[:64]):
        family = gedcom_family(data)
        family['format'] = 'gedcom'
    elif data[:2] == b'PK':
        family = tree_family(read_xlsx(data))
        family['format'] = 'xlsx'
        info = book_info(read_xlsx(data, INFO_SHEET, fallback=False))
        if info:
            family['book'] = tidy_book(info)
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
