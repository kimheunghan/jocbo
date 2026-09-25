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
        # 忌七六月: a stray character run into the month; the month is its end.
        if (not month or not 1 <= month <= 12) and len(match.group(2)) > 1:
            month = _small(match.group(2)[-1])
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


def _horizontal(ink, x0, x1, keep):
    """Long runs of ink across [x0, x1): each as its slope, height, and extent."""
    import cv2
    import numpy
    part = ink[:, x0:x1]
    width = x1 - x0
    opened = cv2.morphologyEx(part, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, width // 25), 1)))
    joined = cv2.dilate(opened, cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, width // 20), 7)))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(joined)
    found = []
    for label in range(1, count):
        x, y, w, h = stats[label][:4]
        if w < width * keep or h > width * 0.12:
            continue
        ys, xs = numpy.nonzero(opened[y:y + h, x:x + w] & (labels[y:y + h, x:x + w] == label))
        if len(xs) < 2:
            continue
        slope, base = numpy.polyfit(xs + x + x0, ys + y, 1)
        found.append({'slope': float(slope), 'base': float(base), 'x0': int(x + x0), 'x1': int(x + w + x0)})
    return found


def pages(image):
    """The page or pages in the photo, each with the rules that cross it.

    A book photographed open shows two pages whose rules stand at different
    heights, since the paper curls toward the spine. Taken together their bands
    run into one another, so the spread is cut at the gutter, where no rule
    crosses, and each page keeps its own. A rule printed thin and tilted by the
    curl breaks into short runs of ink, so strokes are thickened a little
    upward first.
    """
    try:
        import cv2
        import numpy
    except Exception:
        return []
    gray = cv2.cvtColor(numpy.asarray(image), cv2.COLOR_RGB2GRAY)
    width = gray.shape[1]
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 10)
    ink = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 5)))
    spans = [(line['x0'], line['x1']) for line in _horizontal(ink, 0, width, 0.15)]
    covered = numpy.zeros(width, int)
    for start, end in spans:
        covered[start:end] += 1
    # The gutter: the widest stretch near the middle that far fewer rules cross
    # than cross the pages. The edge of the cover or the table can still run
    # the whole width under the book, so it is not asked to be crossed by none.
    middle = covered[int(width * 0.3):int(width * 0.7)]
    cuts = [0, width]
    if len(middle) and covered.max() >= 3:
        low = middle.min()
        split, run, best = None, 0, 0
        for x in range(int(width * 0.3), int(width * 0.7)):
            run = run + 1 if covered[x] == low else 0
            if run > best:
                best, split = run, x - run // 2
        if split and low <= covered.max() * 0.34 and best >= width * 0.004:
            cuts = [0, split, width]
    found = []
    for x0, x1 in zip(cuts, cuts[1:]):
        lines = sorted(_horizontal(ink, x0, x1, 0.4), key=lambda line: line['base'] + line['slope'] * (x0 + x1) / 2)
        if lines:
            found.append({'x0': x0, 'x1': x1, 'lines': lines})
    return found


def _above(lines, x, y):
    """How many of a page's rules pass above the point (x, y)."""
    return sum(1 for line in lines if line['base'] + line['slope'] * x < y)


def _aligned(spread):
    """For each page, what to add to its band number to reach the right page's.

    A 족보 is read from the right-hand page, and both pages of a spread carry the
    same generation rows. Where the two pages meet, a row's rule on one side
    meets the same row's rule on the other, so the rules are paired there.
    """
    if not spread:
        return []
    right = spread[-1]
    shifts = []
    for page in spread:
        if page is right:
            shifts.append(0)
            continue
        at = page['x1']
        here = [line['base'] + line['slope'] * at for line in page['lines']]
        there = [line['base'] + line['slope'] * at for line in right['lines']]
        gaps = [b - a for a, b in zip(there, there[1:])] or [0]
        tolerance = sorted(gaps)[len(gaps) // 2] * 0.4
        pairs = []
        for index, y in enumerate(here):
            nearest = min(range(len(there)), key=lambda other: abs(there[other] - y))
            if abs(there[nearest] - y) <= tolerance:
                pairs.append(nearest - index)
        shifts.append(sorted(pairs)[len(pairs) // 2] if pairs else 0)
    return shifts


# The generation printed down the margin beside each band: 二十六世. The reader
# sometimes returns 世 as 川 and drops a character or adds a stray one.
GENERATION_LABEL = re.compile(r'^[一二三四五六七八九十百廿卅川庫\s]*[世川]$')


def _generation(text):
    """二十六世 → 26, or None where the label was misread."""
    match = re.fullmatch(r'([一二三四五六七八九]?)(十?)([一二三四五六七八九]?)世', re.sub(r'\s', '', text))
    if not match:
        return None
    high, ten, low = match.groups()
    if ten:
        return (DIGITS[high] if high else 1) * 10 + (DIGITS[low] if low else 0)
    if high and not low:
        return DIGITS[high]
    return None


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
MISCONVERTED = {'樸': '朴', '硃': '朱', '曹': '曺'}
# A Korean book prints some names in the short form (点 for 點), and the table
# lengthens them. In a name the book's own form is kept.
SHORT_FORMS = {'點': '点'}
# Characters the reader returns for a name character it mistook, that are
# themselves all but never given in a Korean name: 踢 for 錫 shares its 易.
NAME_MISREAD = {'踢': '錫', '惕': '錫', '賜': '錫',
                # The table gives 鐘 (a bell) for 钟; a Korean name writes 鍾.
                '鐘': '鍾',
                # 鎭 loses its 眞 to 貨 and 磬 its 石 to 石 under 广.
                '鎖': '鎭', '磨': '磬', '填': '埴',
                # The table lengthens 斗 into 鬥, which no one is named.
                '鬥': '斗'}
# 본관 characters the reader mistakes for one of like shape: 摩州 is 慶州, both
# under 广. A 본관 is a place, so these stand only where a place name does.
BON_GWAN_MISREAD = {'摩': '慶', '麐': '慶', '晨': '晉', '青': '淸', '清': '淸', '倘': '尙', '尚': '尙', '寕': '寧'}


def _fixed(name):
    """A name as it was printed, with the table's and the reader's slips put back."""
    return ''.join(NAME_MISREAD.get(char, MISCONVERTED.get(char, char)) for char in name)


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
        # 英子 and 春子 end in 子, which does not open the next entry when no
        # name follows it.
        if (char == '子' and len(out) == 1
                and not NAME_CHAR.match(text[index + 1:index + 2] or ' ')):
            out.append(char)
            continue
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


def _marks(stream, starts=None):
    """Where the entries begin.

    子 and 女 also turn up inside the small notes the page sets in brackets, and
    子 is one of the twelve branches, so it stands in every 甲子 and 庚子 on the
    page. Neither starts a person.

    Where it is known where each of the reader's boxes began (starts), an entry
    is also known to open a column: 東國(동국)女, a spouse's father named with
    her, sits in the middle of one, and so do the children a daughter's entry
    lists after her husband.
    """
    inside, found, wed = False, [], False
    for index, char in enumerate(stream):
        # A daughter's entry names her husband (夫) and then her son, who is of
        # his father's line and not of this book's.
        if char == '夫' and found and stream[found[-1]] == '女':
            wed = True
            continue
        if starts is not None and char in '子女':
            head = max((start for start in starts if start <= index), default=0)
            # Only marks of punctuation or noise may stand before it in its box,
            # and a 子 alone in a box of its own is a stray, not a person.
            if NAME_CHAR.search(stream[head:index]):
                continue
            following = min((start for start in starts if start > index), default=len(stream))
            if not NAME_CHAR.search(stream[index + 1:following]):
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
        # 英子（영자）: a 子 that ends a name has no name after it to open.
        if char == '子' and index and NAME_CHAR.match(stream[index - 1]) \
                and not NAME_CHAR.match(stream[index + 1:index + 2] or ' '):
            continue
        # Inside a note, a marker counts only when a whole name follows it. That
        # is what keeps （子） out while still finding the entry that comes after
        # a bracket the reader never closed.
        if inside and len(_name(stream[index + 1:])) < GIVEN_NAME:
            continue
        if wed and char == '子' and starts is None:
            wed = False
            continue
        wed = False
        found.append(index)
    return found


# 配 <본관 two characters> <family name> 氏 <given name>. The given name is left
# to _name, so the first digit of the date that follows is not read into it.
BON_GWAN = re.compile(r'配\s*([㐀-鿿]{1,2})\s*([㐀-鿿])\s*氏\s*(.*)', re.S)


# Other names the page gives a person, each followed by the name itself.
OTHER_NAMES = re.compile(r'(字|初名|號|諱)\s*([㐀-鿿]{2})')
# Where a person lies: 墓 up to the way the grave faces. 墓는 comes back as 墓二,
# since the reader has no hangul.
HUSBAND = re.compile(r'夫\s*([㐀-鿿]{2,4}?)(?=[（(子]|$)')
FATHER = re.compile(r'([㐀-鿿]{2})\s*(?:[（(][^（(）)]*[）)]?)?\s*女')
GRAVE = re.compile(r'墓\s*[는二]?\s*([^墓配忌生卒]{2,24}?[坐向])')


def _notes(chunk, dated):
    """What else the entry says, in the characters the reader can be trusted with.

    A bracket holds the hangul reading of what stands before it, which the
    reader turns into nonsense characters, so brackets are left out.
    """
    plain = re.sub(r'[（(][^）)]*[）)]?', '', chunk)
    notes = ['%s %s' % (match.group(1), _fixed(match.group(2))) for match in OTHER_NAMES.finditer(plain)
             if not DATE_START.match(plain, match.start(2) + 1)]
    notes += ['墓 ' + re.sub(r'[\s，,。.]', '', match.group(1)) for match in GRAVE.finditer(plain)]
    # 配 … 鍾萬(종만)女: someone who married in is named as her father's daughter.
    if chunk.startswith('配'):
        # The father stands beside the hangul reading of the spouse's name,
        # which the reader turns into characters of its own, so a name read
        # there is as often the noise beside it: it is marked to be checked.
        notes += ['父 %s(확인 필요)' % _fixed(name) for name in FATHER.findall(chunk)]
    # 女 … 夫 諸葛芝奉 子 柄律: a daughter's husband, and her son of his line.
    if chunk.startswith('女'):
        notes += ['夫 ' + _fixed(name) for name in HUSBAND.findall(chunk)]
        notes += ['子 ' + name for name in re.findall(r'夫[^子]*子\s*([㐀-鿿]{2})', chunk)]
    notes += _yearless(chunk, dated)
    return ' · '.join(notes)


# 女 嚴柱華 寧越人: an older book names a daughter by her husband, his 본관
# after him and 人, and does not give her own name at all.
SON_IN_LAW = re.compile(r'\s*([㐀-鿿]{3})\s*([㐀-鿿]{2})\s*[（(]?[^人子女配）)]{0,6}[）)]?\s*人')


def _entries(stream, surname, starts=None):
    """Cut a band's text into one entry per person."""
    marks = _marks(stream, starts)
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
            # 金寧金氏 read as 金金氏 has lost a character of the 본관; the person
            # still stands, with the 본관 left for a hand to fill.
            bon_gwan = _bon_gwan(''.join(MISCONVERTED.get(char, char) for char in bon_gwan)) if len(bon_gwan) == 2 else ''
            hanja = family + given
        elif marker == '女' and SON_IN_LAW.match(chunk, 1):
            husband, home = SON_IN_LAW.match(chunk, 1).groups()
            husband = _fixed(husband)
            bon_gwan = ''
            hanja = (surname + '氏') if surname else ''
            found = _dates(chunk)
            people.append({
                'hanja_name': hanja, 'gender': '여', 'bon_gwan': '',
                'birth_date': '', 'death_date': '', 'married_in': False, 'ganji_agrees': None,
                'note': '사위 %s(%s人) · 딸 이름 미기재' % (husband, _bon_gwan(home)),
                'raw': chunk[:80], 'at': start,
            })
            # A date after the husband's 본관 is no part of her entry: it is what
            # is left of the next one, whose name the reader missed. It is
            # offered with the name blank rather than lost.
            rest = chunk[SON_IN_LAW.match(chunk, 1).end():]
            left = _dates(rest)
            if left:
                birth = next((one for one in left if one['kind'] == '生'), None)
                death = next((one for one in left if one['kind'] == '卒'), None)
                notes = _notes(rest, left)
                people.append({
                    'hanja_name': '', 'gender': '미상', 'bon_gwan': '',
                    'birth_date': birth['date'] if birth else '', 'death_date': death['date'] if death else '',
                    'married_in': False, 'ganji_agrees': all(one['agrees'] for one in left),
                    'note': '이름 판독 안 됨' + (' · ' + notes if notes else ''),
                    'raw': rest[:80], 'at': start + SON_IN_LAW.match(chunk, 1).end(),
                })
            continue
        else:
            given = _name(chunk[1:])
            # A bare marker, or one that is really part of a 간지, is not a person;
            # nor is (지한)女 一九二四年, a date the reader took for a name.
            if not 1 <= len(given) <= 3 or all(char in DIGITS for char in given):
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
            'at': start,
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
    spread = pages(page)
    if spread:
        people, count = _read_ruled(boxes, spread, surname)
        if people:
            return {'people': people, 'bands': count, 'boxes': len(boxes)}
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


def _read_ruled(boxes, spread, surname):
    """Read the page or spread band by band, each band across both pages.

    A box belongs to the page it stands on and to the band between that page's
    rules; the left page's bands are then numbered as the right page's are, so a
    generation reads on from one page to the other as the book does. Where the
    margin names the generations (二十六世) each band is given its own; a label
    the reader garbled is made up from its neighbours.
    """
    shifts = _aligned(spread)

    def where(box):
        middle_x, middle_y = box['x'] + box['w'] / 2, box['y'] + box['h'] / 2
        for index, one in enumerate(spread):
            if one['x0'] <= middle_x < one['x1']:
                return index, _above(one['lines'], middle_x, middle_y) + shifts[index]
        return None, None

    labels, grouped = [], {}
    for box in boxes:
        text = re.sub(r'\s', '', box['text'])
        side, band = where(box)
        if side is None:
            continue
        # The margin: generation labels, page numbers, the book's own title.
        if GENERATION_LABEL.match(text):
            generation = _generation(text)
            if generation:
                labels.append((band, generation))
            continue
        if re.fullmatch(r'[0-9]+', text) or _margin(box):
            continue
        grouped.setdefault(band, []).append(box)
    offsets = sorted(generation - band for band, generation in labels)
    offset = offsets[len(offsets) // 2] if offsets else None

    people, count = [], 0
    for band in sorted(grouped):
        ordered = columns(grouped[band])
        stream, starts, heads = '', set(), []
        for box in ordered:
            starts.add(len(stream))
            heads.append((len(stream), box))
            stream += box['text']
        found = _entries(stream, surname, starts)
        if not found:
            continue
        worst = min(box['score'] for box in ordered)
        for person in found:
            at = person.pop('at', 0)
            box = max((one for one in heads if one[0] <= at), key=lambda one: one[0])[1]
            person['_box'] = box
            person['_side'] = where(box)[0]
            person['band'] = count
            person['score'] = round(worst, 2)
            if offset is not None:
                person['generation'] = band + offset
            people.append(person)
        count += 1
    _families(people, len(spread) - 1)
    for person in people:
        del person['_box'], person['_side']
    return people, count


def _families(people, right):
    """Tell the family carried over from the right-hand page from one that starts.

    A spread goes on with the family the right page began and, somewhere on the
    left page, starts another. A person on the left page of an older generation
    than any on the right cannot be a descendant of the family being carried
    on, so it opens the next one; the columns of that family reach no further
    right than its right-most such person. Everyone to the left of that edge is
    of the new family, 30世 or not, and everyone to the right of it goes on with
    the old — as does the entry that runs over the gutter.
    """
    for person in people:
        person['family'] = 0
    named = [person for person in people if person.get('generation') and person['hanja_name']]
    carried = [person['generation'] for person in named if person['_side'] == right]
    if not carried:
        return
    top = min(carried)
    older = [person for person in named if person['_side'] != right and person['generation'] < top]
    if not older:
        return
    edge = max(person['_box']['x'] + person['_box']['w'] for person in older)
    for person in people:
        box = person['_box']
        if person['_side'] != right and box['x'] + box['w'] / 2 < edge:
            person['family'] = 1
    # The page is read family by family: the one carried on, then the new one.
    people.sort(key=lambda person: person['family'])
