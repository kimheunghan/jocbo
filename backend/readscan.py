# -*- coding: utf-8 -*-
"""Read a photographed 족보 page into proposed people.

The page is set in columns read right to left, divided into horizontal bands
with one generation to a band. An entry opens with 子 or 女 for a child of the
line, or 配 for someone who married into it, and carries a birth date written
with its sexagenary year beside it — which is used here as a check on the
reading rather than as decoration, since a year and its 간지 have to agree.

Nothing here writes to the record. It proposes lines for a person to correct.
"""
import re

_engine = None
_convert = None


def available():
    """Whether a reading engine is installed at all."""
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def _reader():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR
        _engine = RapidOCR()
    return _engine


def _traditional(text):
    """The model is trained on simplified characters; a 족보 is not written in them."""
    global _convert
    if _convert is None:
        try:
            from opencc import OpenCC
            _convert = OpenCC('s2t').convert
        except Exception:
            _convert = lambda value: value
    return _convert(text)


DIGITS = {'〇': 0, '零': 0, 'O': 0, 'o': 0, '○': 0, '一': 1, '二': 2, '三': 3, '四': 4,
          '五': 5, '六': 6, '七': 7, '八': 8, '九': 9}
for _n in range(10):
    DIGITS[str(_n)] = _n
STEMS = '甲乙丙丁戊己庚辛壬癸'
BRANCHES = '子丑寅卯辰巳午未申酉戌亥'


def _year(text):
    value = 0
    for char in text:
        if char not in DIGITS:
            return None
        value = value * 10 + DIGITS[char]
    return value if 1000 <= value <= 2999 else None


def _small(text):
    """十一 → 11, 二十九 → 29, 三 → 3. The page writes months and days this way."""
    if not text:
        return None
    if all(char in '0123456789' for char in text):
        return int(text)
    if '十' in text:
        tens, _, units = text.partition('十')
        high = DIGITS.get(tens, 1) if tens else 1
        low = DIGITS.get(units, 0) if units else 0
        return high * 10 + low
    if text in ('廿',):
        return 20
    if text.startswith('廿'):
        return 20 + (DIGITS.get(text[1:], 0) if len(text) > 1 else 0)
    if text.startswith('卅'):
        return 30 + (DIGITS.get(text[1:], 0) if len(text) > 1 else 0)
    return DIGITS.get(text)


def ganji(year):
    return STEMS[(year - 4) % 10] + BRANCHES[(year - 4) % 12]


NUMBER = '〇零○Oo0-9一二三四五六七八九十廿卅'
DATE = re.compile(
    r'([%s]{4})\s*年\s*([%s]{2})?\s*([%s]{1,3})\s*月\s*([%s]{1,3})\s*日\s*(生|卒)'
    % (NUMBER, STEMS + BRANCHES, NUMBER, NUMBER))


def _dates(text):
    """Every date in an entry, each with whether its 간지 backs the year up."""
    found = []
    for match in DATE.finditer(text):
        year = _year(match.group(1))
        month, day = _small(match.group(3)), _small(match.group(4))
        if not year or not month or not day or not (1 <= month <= 12) or not (1 <= day <= 31):
            continue
        cycle = match.group(2)
        found.append({
            'kind': match.group(5),
            'date': '%04d-%02d-%02d' % (year, month, day),
            # A year and its 간지 disagreeing means one of the two was misread.
            'ganji': cycle or '',
            'agrees': (not cycle) or cycle == ganji(year),
            'at': match.start(),
        })
    return found


def bands(boxes, gap=0.18):
    """Split the page into its horizontal bands, one generation to a band.

    The 권 and 쪽 marks along the head of the sheet are set in a few characters
    where an entry runs the depth of the band, so they are told apart by height
    and dropped rather than mixed into the first generation.
    """
    if not boxes:
        return []
    tallest = max(box['h'] for box in boxes)
    boxes = [box for box in boxes if box['h'] >= tallest * 0.2]
    if not boxes:
        return []
    height = max(box['y'] + box['h'] for box in boxes)
    tops = sorted(boxes, key=lambda box: box['y'])
    groups, current = [], [tops[0]]
    for box in tops[1:]:
        if box['y'] - current[-1]['y'] > height * gap:
            groups.append(current)
            current = [box]
        else:
            current.append(box)
    groups.append(current)
    # The page is read right to left inside each band.
    return [sorted(group, key=lambda box: -box['x']) for group in groups]


MARKERS = {'子': '남', '女': '여', '配': '여'}
NAME_CHAR = re.compile(r'[㐀-鿿]')
# 朴 is its own character in a Korean name; the simplified-to-traditional table
# turns it into 樸, which is a different surname altogether.
MISCONVERTED = {'樸': '朴', '硃': '朱'}
# A 족보 gives two characters for a given name almost without exception, and the
# small 字 note that follows is read as more characters, so the name stops there.
GIVEN_NAME = 2


def _name(text):
    """The characters that follow a marker, before anything else starts."""
    out = []
    for char in text:
        if len(out) >= GIVEN_NAME:
            break
        if char in MARKERS or char in '（）()[]，,。.':
            break
        if char in '年月日生卒墓配系':
            break
        # A name is not made of numbers or of the sexagenary cycle.
        if char in DIGITS or char in STEMS or char in BRANCHES:
            break
        if not NAME_CHAR.match(char):
            break
        out.append(MISCONVERTED.get(char, char))
    return ''.join(out)


def _marks(stream):
    """Where the entries begin.

    子 and 女 also turn up inside the small notes the page sets in brackets, and
    子 is one of the twelve branches, so it stands in every 甲子 and 庚子 on the
    page. Neither starts a person.
    """
    inside, found = False, []
    for index, char in enumerate(stream):
        if char in '（(':
            inside = True
            continue
        if char in '）)':
            inside = False
            continue
        if char not in MARKERS:
            continue
        if char in BRANCHES and index and stream[index - 1] in STEMS:
            continue
        # Inside a note, a marker counts only when a whole name follows it. That
        # is what keeps （子） out while still finding the entry that comes after
        # a bracket the reader never closed.
        if inside and len(_name(stream[index + 1:])) < GIVEN_NAME:
            continue
        found.append(index)
    return found


# 配 <본관 two characters> <family name> 氏 <given name>. The given name is left
# to _name, so the first digit of the date that follows is not read into it.
BON_GWAN = re.compile(r'配\s*([㐀-鿿]{2})\s*([㐀-鿿])\s*氏\s*(.*)', re.S)


def _entries(stream, surname):
    """Cut a band's text into one entry per person."""
    marks = _marks(stream)
    people = []
    for order, start in enumerate(marks):
        end = marks[order + 1] if order + 1 < len(marks) else len(stream)
        chunk = stream[start:end]
        marker = chunk[0]
        if marker == '配':
            match = BON_GWAN.match(chunk)
            if not match:
                continue
            bon_gwan, family, given = match.groups()
            given = _name(given)
            if not given:
                continue
            family = MISCONVERTED.get(family, family)
            bon_gwan = ''.join(MISCONVERTED.get(char, char) for char in bon_gwan)
            hanja = family + given
        else:
            given = _name(chunk[1:])
            # A bare marker, or one that is really part of a 간지, is not a person.
            if not 1 <= len(given) <= 3:
                continue
            bon_gwan = ''
            hanja = (surname + given) if surname else given
        found = _dates(chunk)
        birth = next((one for one in found if one['kind'] == '生'), None)
        death = next((one for one in found if one['kind'] == '卒'), None)
        people.append({
            'hanja_name': hanja,
            'gender': MARKERS[marker],
            'bon_gwan': bon_gwan,
            'birth_date': birth['date'] if birth else '',
            'death_date': death['date'] if death else '',
            'married_in': marker == '配',
            'ganji_agrees': all(one['agrees'] for one in found) if found else None,
            'raw': chunk[:80],
        })
    return people


def read(path, surname=''):
    """Read a page image and propose the people written on it."""
    if not available():
        raise RuntimeError('판독기가 설치되어 있지 않습니다.')
    from PIL import Image
    with Image.open(path) as page:
        result, _ = _reader()(page.convert('RGB'))
    boxes = []
    for corners, text, score in result or []:
        xs = [point[0] for point in corners]
        ys = [point[1] for point in corners]
        boxes.append({'x': min(xs), 'y': min(ys), 'w': max(xs) - min(xs), 'h': max(ys) - min(ys),
                      'text': _traditional(text), 'score': float(score)})
    people, lowest = [], {}
    for index, band in enumerate(bands(boxes)):
        stream = ''.join(box['text'] for box in band)
        worst = min((box['score'] for box in band), default=0.0)
        for person in _entries(stream, surname):
            person['band'] = index
            person['score'] = round(worst, 2)
            people.append(person)
        lowest[index] = worst
    return {'people': people, 'bands': len(lowest), 'boxes': len(boxes)}
