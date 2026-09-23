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
# The reader mistakes these for the stem or branch they look like: 己亥 comes
# back as 已亥, 戊申 as 戊中. Which one is meant depends on the place it stands.
STEM_LOOKALIKE = {'已': '己', '巳': '己', '戌': '戊', '戍': '戊'}
BRANCH_LOOKALIKE = {'中': '申', '已': '巳', '己': '巳', '戍': '戌', '成': '戌', '戊': '戌', '干': '午'}
# Months the page names rather than numbers.
NAMED_MONTHS = {'正': 1, '至': 11, '臘': 12}


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
    if text in NAMED_MONTHS:
        return NAMED_MONTHS[text]
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


def _cycle(text):
    """A 간지 as it was meant, with the lookalikes put back."""
    if len(text) != 2:
        return text
    return STEM_LOOKALIKE.get(text[0], text[0]) + BRANCH_LOOKALIKE.get(text[1], text[1])


NUMBER = '〇零○Oo0-9一二三四五六七八九十廿卅'
CYCLE = STEMS + BRANCHES + ''.join(STEM_LOOKALIKE) + ''.join(BRANCH_LOOKALIKE)
MONTH = r'(?:[%s]{1,3}|[%s])' % (NUMBER, ''.join(NAMED_MONTHS))
# 日 is sometimes left out before 卒 (三月五卒), so a day stands either on 日 or
# on the 生 or 卒 that follows it directly.
DAY = r'([%s]{1,3})\s*(?:日\s*(生|卒)?|(生|卒))' % NUMBER
DATE = re.compile(r'([%s]{4})\s*年\s*([%s]{2})?\s*(%s)\s*月\s*%s' % (NUMBER, CYCLE, MONTH, DAY))
# A date without a year: the day a spouse is remembered on (忌 九月十九日), or a
# birth given by month and day alone.
# 忌는 comes back as 忌二 or 忌一, since the reader has no hangul.
YEARLESS = re.compile(r'(忌|生)?\s*(?:[는二一])?\s*(%s)\s*月\s*%s' % (MONTH, DAY))


def _dates(text):
    """Every date in an entry, each with whether its 간지 backs the year up."""
    found = []
    for match in DATE.finditer(text):
        year = _year(match.group(1))
        month, day = _small(match.group(3)), _small(match.group(4))
        if not year or not month or not day or not (1 <= month <= 12) or not (1 <= day <= 31):
            continue
        cycle = _cycle(match.group(2) or '')
        found.append({
            'kind': match.group(5) or match.group(6) or '',
            'date': '%04d-%02d-%02d' % (year, month, day),
            # A year and its 간지 disagreeing means one of the two was misread.
            'ganji': cycle,
            'agrees': (not cycle) or cycle == ganji(year),
            'at': match.start(),
            'end': match.end(),
        })
    # The page gives the birth first and the death after it. Where the reader
    # lost the 生 or the 卒 itself, the order says which one it was.
    for one in found:
        if not one['kind']:
            one['kind'] = '卒' if any(other['kind'] == '生' for other in found) else '生'
    return found


def _yearless(text, dated):
    """Dates written as a month and a day alone, outside every dated one."""
    spans = [(one['at'], one['end']) for one in dated]
    found = []
    for match in YEARLESS.finditer(text):
        if any(start <= match.start() < end or start < match.end() <= end for start, end in spans):
            continue
        month, day = _small(match.group(2)), _small(match.group(3))
        if not month or not day or not (1 <= month <= 12) or not (1 <= day <= 31):
            continue
        kind = match.group(4) or match.group(5) or ''
        label = '기일' if match.group(1) == '忌' or kind == '卒' else '생일'
        found.append('%s %d월 %d일' % (label, month, day))
    return found


def rules(image):
    """The ruled lines that cross the page between its bands, top to bottom.

    Each comes back as a slope and a height, since a photo is seldom square to
    the sheet and a line runs a little uphill or down.
    """
    try:
        import cv2
        import numpy
    except Exception:
        return []
    gray = cv2.cvtColor(numpy.asarray(image), cv2.COLOR_RGB2GRAY)
    width = gray.shape[1]
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    # Only a long run of ink survives a wide flat opening: a rule does, a
    # character does not.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, width // 12), 1))
    lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel)
    lines = cv2.dilate(lines, cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, width // 30), 5)))
    count, _, stats, _ = cv2.connectedComponentsWithStats(lines)
    found = []
    for label in range(1, count):
        x, y, w, h = stats[label][:4]
        if w < width * 0.35 or h > w * 0.2:
            continue
        ys, xs = numpy.nonzero(lines[y:y + h, x:x + w])
        slope, base = numpy.polyfit(xs + x, ys + y, 1)
        found.append((float(slope), float(base)))
    return sorted(found, key=lambda line: line[1] + line[0] * width / 2)


def _margin(box):
    """The book's own title, set down the outer margin across every band."""
    return '譜' in box['text'] and '卷' in box['text']


def columns(boxes):
    """Order a band as the page is read: columns right to left, each top down.

    The reader sometimes breaks one column into two boxes, so boxes that share
    most of their width are kept together and read downward.
    """
    ordered = []
    for box in sorted(boxes, key=lambda box: -(box['x'] + box['w'] / 2)):
        column = ordered[-1] if ordered else None
        if column:
            left = max(box['x'], min(one['x'] for one in column))
            right = min(box['x'] + box['w'], max(one['x'] + one['w'] for one in column))
            # Two pieces of one column sit one above the other; two columns side
            # by side run down the same stretch of the band.
            beside = max(min(box['y'] + box['h'], one['y'] + one['h']) - max(box['y'], one['y'])
                         for one in column)
            if (right - left > min(box['w'], max(one['w'] for one in column)) * 0.5
                    and beside < min(box['h'], min(one['h'] for one in column)) * 0.2):
                column.append(box)
                continue
        ordered.append([box])
    return [box for column in ordered for box in sorted(column, key=lambda box: box['y'])]


def bands(boxes, gap=0.18, lines=()):
    """Split the page into its horizontal bands, one generation to a band.

    Where the page's ruled lines were found, a box belongs to the band its middle
    falls in. Otherwise the bands are told apart by the gap between their tops.
    The 권 and 쪽 marks along the head of the sheet are set in a few characters
    where an entry runs the depth of the band, so they are told apart by height
    and dropped rather than mixed into the first generation.
    """
    boxes = [box for box in boxes if not _margin(box)]
    if not boxes:
        return []
    tallest = max(box['h'] for box in boxes)
    boxes = [box for box in boxes if box['h'] >= tallest * 0.2]
    if not boxes:
        return []
    if lines:
        groups = {}
        for box in boxes:
            middle_x, middle_y = box['x'] + box['w'] / 2, box['y'] + box['h'] / 2
            above = sum(1 for slope, base in lines if base + slope * middle_x < middle_y)
            groups.setdefault(above, []).append(box)
        return [columns(groups[key]) for key in sorted(groups)]
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
    return [columns(group) for group in groups]


MARKERS = {'子': '남', '女': '여', '配': '여'}
NAME_CHAR = re.compile(r'[㐀-鿿]')
# 朴 is its own character in a Korean name; the simplified-to-traditional table
# turns it into 樸, which is a different surname altogether.
MISCONVERTED = {'樸': '朴', '硃': '朱'}
# A Korean book prints some names in the short form (点 for 點), and the table
# lengthens them. In a name the book's own form is kept.
SHORT_FORMS = {'點': '点'}
# Characters the reader returns for a name character it mistook, that are
# themselves all but never given in a Korean name: 踢 for 錫 shares its 易.
NAME_MISREAD = {'踢': '錫', '惕': '錫', '賜': '錫'}
# 본관 characters the reader mistakes for one of like shape: 摩州 is 慶州, both
# under 广. A 본관 is a place, so these stand only where a place name does.
BON_GWAN_MISREAD = {'摩': '慶', '麐': '慶', '晨': '晉', '青': '淸', '清': '淸', '倘': '尙'}


def _bon_gwan(text):
    return ''.join(BON_GWAN_MISREAD.get(char, char) for char in text)
# A 족보 gives two characters for a given name almost without exception, and the
# small 字 note that follows is read as more characters, so the name stops there.
GIVEN_NAME = 2
DATE_START = re.compile(r'[%s]{2,4}\s*年|[%s]{1,3}\s*[月日生卒]|[0-9]' % (NUMBER, NUMBER))


def _name(text):
    """The characters that follow a marker, before anything else starts."""
    out = []
    for index, char in enumerate(text):
        if len(out) >= GIVEN_NAME:
            break
        if char in MARKERS or char in '（）()[]，,。.':
            break
        if char in '年月日生卒墓配系':
            break
        # 三順 and 一男 are names, so a numeral ends one only where a date starts.
        if char in DIGITS and DATE_START.match(text, index):
            break
        if char in STEMS or char in BRANCHES:
            break
        if not NAME_CHAR.match(char):
            break
        char = MISCONVERTED.get(char, char)
        char = NAME_MISREAD.get(char, char)
        out.append(SHORT_FORMS.get(char, char))
    return ''.join(out)


def _marks(stream):
    """Where the entries begin.

    子 and 女 also turn up inside the small notes the page sets in brackets, and
    子 is one of the twelve branches, so it stands in every 甲子 and 庚子 on the
    page. Neither starts a person.
    """
    inside, found, wed = False, [], False
    for index, char in enumerate(stream):
        # A daughter's entry names her husband (夫) and then her son, who is of
        # his father's line and not of this book's.
        if char == '夫' and found and stream[found[-1]] == '女':
            wed = True
            continue
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
        if wed and char == '子':
            wed = False
            continue
        wed = False
        found.append(index)
    return found


# 配 <본관 two characters> <family name> 氏 <given name>. The given name is left
# to _name, so the first digit of the date that follows is not read into it.
BON_GWAN = re.compile(r'配\s*([㐀-鿿]{2})\s*([㐀-鿿])\s*氏\s*(.*)', re.S)


# Other names the page gives a person, each followed by the name itself.
OTHER_NAMES = re.compile(r'(字|初名|號|諱)\s*([㐀-鿿]{2})')
# Where a person lies: 墓 up to the way the grave faces. 墓는 comes back as 墓二,
# since the reader has no hangul.
HUSBAND = re.compile(r'夫\s*([㐀-鿿]{2,4}?)(?=[（(子]|$)')
FATHER = re.compile(r'([㐀-鿿]{2})\s*(?:[（(][^）)]*[）)]?)?\s*女')
GRAVE = re.compile(r'墓\s*[는二]?\s*([^墓配忌生卒]{2,24}?[坐向])')


def _notes(chunk, dated):
    """What else the entry says, in the characters the reader can be trusted with.

    A bracket holds the hangul reading of what stands before it, which the
    reader turns into nonsense characters, so brackets are left out.
    """
    plain = re.sub(r'[（(][^）)]*[）)]?', '', chunk)
    notes = ['%s %s' % match.groups() for match in OTHER_NAMES.finditer(plain)]
    notes += ['墓 ' + re.sub(r'[\s，,。.]', '', match.group(1)) for match in GRAVE.finditer(plain)]
    # 配 … 鍾萬(종만)女: someone who married in is named as her father's daughter.
    if chunk.startswith('配'):
        notes += ['父 ' + name for name in FATHER.findall(chunk)]
    # 女 … 夫 諸葛芝奉 子 柄律: a daughter's husband, and her son of his line.
    if chunk.startswith('女'):
        notes += ['夫 ' + name for name in HUSBAND.findall(plain)]
        notes += ['子 ' + name for name in re.findall(r'夫[^子]*子\s*([㐀-鿿]{2})', chunk)]
    notes += _yearless(chunk, dated)
    return ' · '.join(notes)


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
            # The page may give the hangul of 본관 and 성씨 in a bracket before
            # the name. That bracket is read as nonsense, and the name after it
            # sometimes not at all — the person is still there, with the 본관 and
            # family name to go on.
            given = _name(re.sub(r'^\s*[（(][^）)]*[）)]?', '', given))
            family = MISCONVERTED.get(family, family)
            bon_gwan = _bon_gwan(''.join(MISCONVERTED.get(char, char) for char in bon_gwan))
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
            'note': _notes(chunk, found),
            'raw': chunk[:80],
        })
    return people


def read(path, surname=''):
    """Read a page image and propose the people written on it."""
    if not available():
        raise RuntimeError('판독기가 설치되어 있지 않습니다.')
    from PIL import Image, ImageOps
    with Image.open(path) as page:
        # A phone stores the picture as the sensor took it and says in its EXIF
        # which way is up. Left alone, the page is read lying on its side and
        # its bands run into one another.
        page = ImageOps.exif_transpose(page).convert('RGB')
    width = page.width
    # The reader works in lines across, so the page is turned a quarter left
    # and every column becomes a line read left to right. It misses fewer
    # columns that way than reading them standing.
    result, _ = _reader()(page.rotate(90, expand=True))
    boxes = []
    for corners, text, score in result or []:
        xs = [point[0] for point in corners]
        ys = [point[1] for point in corners]
        # Back to the page as it stands: across the turned image is down the page.
        boxes.append({'x': width - max(ys), 'y': min(xs), 'w': max(ys) - min(ys), 'h': max(xs) - min(xs),
                      'text': _traditional(text), 'score': float(score)})
    people, lowest = [], {}
    for band in bands(boxes, lines=rules(page)):
        stream = ''.join(box['text'] for box in band)
        worst = min((box['score'] for box in band), default=0.0)
        found = _entries(stream, surname)
        # A strip above the first rule or below the last holds no one.
        if not found:
            continue
        index = len(lowest)
        for person in found:
            person['band'] = index
            person['score'] = round(worst, 2)
            people.append(person)
        lowest[index] = worst
    return {'people': people, 'bands': len(lowest), 'boxes': len(boxes)}
