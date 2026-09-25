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
    for package in ('rapidocr', 'rapidocr_onnxruntime'):
        try:
            __import__(package)
            return True
        except Exception:
            continue
    return False


def _reader():
    """The reading engine, called on a picture and giving (boxes, _) back, each box
    (corners, text, score).

    PP-OCRv6 is taught traditional characters as well as simplified ones, so it
    reads a 족보 as printed — 魯佶, 魯錫, 勝世 — where the older model, taught
    simplified only, read their look-alikes (結上, 魯, 滕世). The older one is kept
    for an install that has not taken the new package yet.
    """
    global _engine
    if _engine is None:
        try:
            from rapidocr import RapidOCR, OCRVersion, ModelType
            engine = RapidOCR(params={
                'Global.log_level': 'error', 'Global.max_side_len': 3000,
                'Det.ocr_version': OCRVersion.PPOCRV5, 'Det.model_type': ModelType.MOBILE,
                'Rec.ocr_version': OCRVersion.PPOCRV6})

            def read(picture):
                out = engine(picture)
                found = [(box.tolist(), text, float(score))
                         for box, text, score in zip(out.boxes if out.boxes is not None else [],
                                                     out.txts or [], out.scores or [])]
                return found, None
            _engine = read
        except ImportError:
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
# 忌는 comes back as 忌二, 忌一, 忌雲 or 忌亡, since the reader has no hangul.
YEARLESS = re.compile(r'(忌|生)?\s*(?:[는二一雲亡])?\s*(%s)\s*月\s*%s' % (MONTH, DAY))


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


def _curves(ink, x0, x1, span, scale):
    """The rules across [x0, x1), each followed as far as it runs unbroken.

    A photo of an open book bends every rule, and more toward the spine; a thin
    rule printed pale breaks into short runs wherever it tilts. Each run is taken
    on its own and joined to the next where it carries on almost without a gap,
    as a rule does and the strokes of a line of characters, broken by the blank
    between columns, do not. Characters sitting on a rule join it, so a run is
    allowed some height. What is found is a curve: a gentle bow, not a line.
    """
    import cv2
    import numpy
    part = ink[:, x0:x1]
    length = max(20, scale // 60)
    opened = cv2.morphologyEx(part, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (length, 1)))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(opened)
    runs = []
    for label in range(1, count):
        x, y, w, h = stats[label][:4]
        if w < length * 1.2 or h > w:
            continue
        ys, xs = numpy.nonzero(labels[y:y + h, x:x + w] == label)
        # A rule that the last characters of many columns stand on runs into
        # them, and the whole is too tall to be a rule. The rule is the one
        # stroke found at every x, so the middle height at each x follows it
        # and the characters, found at some x only, fall away.
        if h > scale * 0.04:
            order = numpy.argsort(xs, kind='stable')
            xs, ys = xs[order], ys[order]
            cuts = numpy.flatnonzero(numpy.diff(xs)) + 1
            columns = numpy.split(ys, cuts)
            xs = numpy.array([xs[0]] + [xs[cut] for cut in cuts])
            ys = numpy.array([numpy.median(column) for column in columns])
            # Where characters hold most of a column the middle is theirs, not
            # the rule's: keep the stretch that lies along one line.
            base = numpy.median(ys)
            keep = numpy.abs(ys - base) < scale * 0.01
            if keep.sum() < length:
                continue
            xs, ys = xs[keep], ys[keep]
        xs, ys = xs + x + x0, ys + y
        left, right = xs < xs.min() + 20, xs > xs.max() - 20
        runs.append({'x0': int(xs.min()), 'x1': int(xs.max()), 'xs': xs, 'ys': ys,
                     'left': float(numpy.median(ys[left])), 'right': float(numpy.median(ys[right]))})
    runs.sort(key=lambda run: run['x0'])
    gap, rise = scale / 120, scale / 257
    chains = []
    for run in runs:
        best = None
        for chain in chains:
            last = chain[-1]
            apart = run['x0'] - last['x1']
            if not -40 < apart < gap:
                continue
            slope = (last['right'] - last['left']) / max(1, last['x1'] - last['x0'])
            miss = abs(last['right'] + slope * apart - run['left'])
            if miss < rise and (best is None or miss < best[0]):
                best = (miss, chain)
        if best:
            best[1].append(run)
        else:
            chains.append([run])
    found = []
    for chain in chains:
        start, stop = chain[0]['x0'], max(run['x1'] for run in chain)
        if stop - start < (x1 - x0) * span:
            continue
        xs = numpy.concatenate([run['xs'] for run in chain])
        ys = numpy.concatenate([run['ys'] for run in chain])
        fit = numpy.polyfit(xs, ys, 2 if stop - start > scale * 0.1 else 1)
        found.append({'fit': [float(value) for value in fit], 'x0': int(start), 'x1': int(stop)})
    return found


def _y(line, x):
    """The height of a rule at x."""
    if 'fit' in line:
        value = 0.0
        for coefficient in line['fit']:
            value = value * x + coefficient
        return value
    return line['base'] + line['slope'] * x


def pages(image):
    """The page or pages in the photo, each with the rules that cross it.

    A book photographed open shows two pages whose rules stand at different
    heights, since the paper curls toward the spine. Taken together their bands
    run into one another, so the spread is cut at the gutter, where no rule
    crosses, and each page keeps its own. A page too little of which is in the
    photo to show a rule of its own is read by its neighbour's.
    """
    try:
        import cv2
        import numpy
    except Exception:
        return []
    gray = cv2.cvtColor(numpy.asarray(image), cv2.COLOR_RGB2GRAY)
    width = gray.shape[1]
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 10)
    # Thickened upward, so a rule tilted by the curl stays one run of ink.
    ink = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 11)))
    covered = numpy.zeros(width, int)
    for line in _curves(ink, 0, width, 0.15, width):
        covered[line['x0']:line['x1']] += 1
    # The gutter: the widest stretch that far fewer rules cross than cross the
    # pages. The edge of the cover or the table can still run the whole width
    # under the book, so it is not asked to be crossed by none; and a photo may
    # show one page whole and only a strip of the other, so it is looked for
    # well off the middle.
    low_end, high_end = int(width * 0.15), int(width * 0.85)
    cuts = [0, width]
    if covered.max() >= 3:
        low = covered[low_end:high_end].min()
        split, run, best = None, 0, 0
        for x in range(low_end, high_end):
            run = run + 1 if covered[x] == low else 0
            if run > best:
                best, split = run, x - run // 2
        if split and low <= covered.max() * 0.34 and best >= width * 0.004:
            cuts = [0, split, width]
    found = []
    for x0, x1 in zip(cuts, cuts[1:]):
        lines = _curves(ink, x0, x1, 0.4, width)
        lines.sort(key=lambda line: _y(line, (x0 + x1) / 2))
        if lines:
            found.append({'x0': x0, 'x1': x1, 'lines': lines})
        elif found:
            found[-1]['x1'] = x1
    # A strip of a page with no rule of its own goes with the page beside it.
    if found:
        found[0]['x0'] = 0
        found[-1]['x1'] = width
        for left, right in zip(found, found[1:]):
            left['x1'] = right['x0']
    return found


def _above(lines, x, y):
    """How many of a page's rules pass above the point (x, y)."""
    return sum(1 for line in lines if _y(line, x) < y)


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
        here = [_y(line, at) for line in page['lines']]
        there = [_y(line, at) for line in right['lines']]
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
            # by side run down the same stretch of the band. A tilted photo lets
            # the pieces of one column overlap a little (敬鎭 over 女智).
            beside = max(min(box['y'] + box['h'], one['y'] + one['h']) - max(box['y'], one['y'])
                         for one in column)
            if (right - left > min(box['w'], max(one['w'] for one in column)) * 0.5
                    and beside < min(box['h'], min(one['h'] for one in column)) * 0.3):
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
# Where a line picks up again after pages of other families, the book heads the
# son with his forebears in small type — 芝淑 相錫 正煥 over 澈純 — and prints
# no 子 before him. Such a heading is set in the stream between these two marks,
# and opens an entry as 子 does.
LINEAGE, LINEAGE_END = '\ue000', '\ue001'
MARKERS[LINEAGE] = '남'
# What a heading of forebears' names never holds: marks, dates, and the words of
# places and notes (陽洞後山, 議公誠后, 寒暄堂) that also come in runs of hanja.
NOT_LINEAGE = set('年月日生卒配子女夫人氏字名墓忌坐向山洞里面郡市道原公后後堂號諱初系') | set(DIGITS)


def _lineage(text):
    """芝淑相錫正煥 → ['芝淑', '相錫', '正煥'] where a box is a heading of
    forebears: two, three or four given names and nothing else."""
    text = re.sub(r'\s', '', text)
    if not re.fullmatch(r'[㐀-鿿]{4,8}', text) or len(text) % 2 or NOT_LINEAGE & set(text):
        return []
    return [_fixed(text[at:at + 2]) for at in range(0, len(text), 2)]
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
                '鬥': '斗',
                # 鎮 is 鎭 as China prints it; the book writes 鎭.
                '鎮': '鎭'}
# 본관 characters the reader mistakes for one of like shape: 摩州 is 慶州, both
# under 广. A 본관 is a place, so these stand only where a place name does.
BON_GWAN_MISREAD = {'摩': '慶', '麐': '慶', '晨': '晉', '青': '淸', '清': '淸', '倘': '尙', '尚': '尙', '寕': '寧', '寫': '寧'}


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
        # 初名 充一, 字 玉汝: a note begins, and the name, if the reader missed
        # it, is not to be made of the note.
        if char in '字號諱' or text.startswith(('初名', '一名'), index):
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
        if char == LINEAGE:
            found.append(index)
            inside = wed = False
            continue
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
            # (동국)女 at the head of a box is still a spouse's father named
            # with her: the bracket before it says so.
            if stream[head:index].rstrip().endswith(('）', ')')):
                continue
        # 女 一九五六年: a year where the name would be opens nothing, and
        # cutting there would take the date from the entry it belongs to.
        if char in '子女':
            ahead = re.sub(r'\s', '', stream[index + 1:index + 3])
            if ahead and all(one in DIGITS for one in ahead):
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
# 父: 世東(세동)女 — the father's name with its hangul in a bracket, then 女.
# The spouse's own name comes just before with its hangul too, which the reader
# turns into characters of its own that run into the father's; the bracket that
# closes right after him is what marks where his name ends.
FATHER = re.compile(r'([㐀-鿿]{2})\s*[（(][^（(）)]{0,6}[）)]\s*女')
# 墓는 comes back as 墓二, 墓雲, 墓亡 or 墓乞.
# 墓는 合墳(합분): a grave shared with the spouse names no place at all.
GRAVE = re.compile(r'墓\s*[는二雲亡乞]?\s*([^墓配忌生卒]{0,4}?墳|[^墓配忌生卒]{2,24}?[坐向])')


def _notes(chunk, dated):
    """What else the entry says, in the characters the reader can be trusted with.

    A bracket holds the hangul reading of what stands before it, which the
    reader turns into nonsense characters, so brackets are left out.
    """
    # A bracket the reader left open takes only the few characters of hangul
    # it held, never a 忌 or 墓 after them: (補從忌六七月… keeps the 忌.
    plain = re.sub(r'[（(][^（(）)]*[）)]', '', chunk)
    plain = re.sub(r'[（(][^（(）)忌墓生卒配]{0,4}|[）)]', '', plain)
    notes = ['%s %s' % (match.group(1), _fixed(match.group(2))) for match in OTHER_NAMES.finditer(plain)
             if not DATE_START.match(plain, match.start(2) + 1)]
    notes += ['墓 ' + re.sub(r'[\s，,。.]', '', match.group(1)) for match in GRAVE.finditer(plain)]
    # 配 … 鍾萬(종만)女: someone who married in is named as her father's daughter.
    if chunk.startswith('配'):
        notes += ['父 ' + _fixed(name) for name in FATHER.findall(chunk)]
    notes += _yearless(chunk, dated)
    return ' · '.join(notes)


def _children(text):
    """子 東炫 女 志娟, as a husband's entry lists them: each 子 or 女 with the
    two-character names after it (女 智恩 睿恩 is two daughters). A date ends
    the list, and the 子 of 庚子 is no son."""
    plain = re.sub(r'[（(][^）)]*[）)]?', '', text)
    cut = DATE_START.search(plain)
    plain = plain[:cut.start()] if cut else plain
    marks = [index for index, char in enumerate(plain) if char in '子女'
             and not (char == '子' and index and plain[index - 1] in STEMS)]
    out = []
    for order, index in enumerate(marks):
        end = marks[order + 1] if order + 1 < len(marks) else len(plain)
        run = re.match(r'[㐀-鿿]+', plain[index + 1:end])
        names = [run.group(0)[at:at + 2] for at in range(0, len(run.group(0)) - 1, 2)] if run else []
        # The names end where a numeral or a date's word turns up: what
        # follows is another column's text run on (一大大四手甲寅).
        kept = []
        for name in names:
            if any(char in DIGITS or char in '年月日生卒' for char in name):
                break
            kept.append(_fixed(name))
        names = kept
        if names:
            out.append('%s %s' % (plain[index], ' · '.join(names)))
    return out


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
            # 配 延安車氏 with no name after it is named as the page names
            # her, 본관 and clan together: 延安車氏. A name that is there is
            # hers (配 昌寧成氏 元永 is 成元永).
            if not given:
                hanja = bon_gwan + family + '氏'
            else:
                hanja = family + given
        elif marker == LINEAGE:
            heading, _, rest = chunk[1:].partition(LINEAGE_END)
            given = _name(rest)
            if all(char in DIGITS for char in given):
                given = ''
            bon_gwan = ''
            hanja = ((surname + given) if surname else given) if given else ''
            chunk = LINEAGE + rest
        elif marker == '女' and SON_IN_LAW.match(chunk, 1):
            husband, home = SON_IN_LAW.match(chunk, 1).groups()
            husband = _fixed(husband)
            bon_gwan = ''
            hanja = (surname + '氏') if surname else ''
            found = _dates(chunk)
            daughter = {
                'hanja_name': hanja, 'gender': '여', 'bon_gwan': '',
                'birth_date': '', 'death_date': '', 'married_in': False, 'ganji_agrees': None,
                'note': '딸 이름 미기재',
                'raw': chunk[:80], 'at': start,
            }
            people.append(daughter)
            # Her husband, named in her place, is proposed as her spouse, with
            # his 본관 where it goes and their children in his note.
            people.append({
                '_partner': daughter,
                'hanja_name': husband, 'gender': '남', 'bon_gwan': _bon_gwan(home),
                'birth_date': '', 'death_date': '', 'married_in': True, 'ganji_agrees': None,
                'note': ' · '.join(_children(chunk[SON_IN_LAW.match(chunk, 1).end():])),
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
        found = every = _dates(chunk)
        # A second birth in one entry is the next person's, whose name the
        # reader missed (子亨純 lost, 一九九二年…生 left under the entry before).
        # It is offered with the name blank rather than given to the wrong one.
        births = [one for one in found if one['kind'] == '生']
        stray = births[1:]
        if stray:
            found = [one for one in found if one['at'] < stray[0]['at']]
        birth = next((one for one in found if one['kind'] == '生'), None)
        death = next((one for one in found if one['kind'] == '卒'), None)
        for one in stray:
            people.append({
                'hanja_name': '', 'gender': '미상', 'bon_gwan': '',
                'birth_date': one['date'], 'death_date': '', 'married_in': False,
                'ganji_agrees': one['agrees'], 'note': '이름 판독 안 됨',
                'raw': chunk[one['at']:one['at'] + 80], 'at': start + one['at'],
            })
        entry = len(people)
        # 配 is the spouse of the son just before: 子鍾煥 … 配 全京愛. A daughter
        # has her 夫 instead, and a son whose name the reader missed is still
        # the one she married.
        partner = None
        if marker == '配':
            partner = next((one for one in reversed(people)
                            if not one['married_in'] and one['gender'] != '여'), None)
        people.append({
            '_partner': partner,
            # The forebears a heading names (芝淑 相錫 正煥): the last is the
            # father, whose generation in the book gives this band its own.
            'forebears': _lineage(heading) if marker == LINEAGE else [],
            'hanja_name': hanja,
            'gender': MARKERS[marker],
            'bon_gwan': bon_gwan,
            'birth_date': birth['date'] if birth else '',
            'death_date': death['date'] if death else '',
            'married_in': marker == '配',
            'ganji_agrees': all(one['agrees'] for one in found) if found else None,
            # Every dated span is known to the notes, the stray birth too, so
            # it is not read a second time as a month and day alone. A
            # daughter's note is her own: her husband and their children go
            # with him.
            # A heading of forebears opens the entry and is not kept in it.
            'note': ' · '.join(filter(None, [
                '이름 판독 안 됨' if marker == LINEAGE and not hanja else '',
                _notes(chunk[:chunk.index('夫')] if marker == '女' and '夫' in chunk else chunk, every)])),
            'raw': chunk[:80],
            'at': start,
        })
        # A daughter's husband has no line of his own in the book; he is named in
        # hers — 夫 金熙旋 瑞興人 父 學龍 — and is proposed after her, so he can
        # be filed and joined to her as her spouse.
        if marker == '女':
            for match in HUSBAND.finditer(chunk):
                husband = _fixed(match.group(1))
                after = chunk[match.end():match.end() + 24]
                home = re.match(r'\s*(?:[（(][^）)]*[）)]?)?\s*([㐀-鿿]{2})\s*(?:[（(][^）)人]*[）)]?)?\s*人', after)
                father = re.search(r'人\s*父\s*([㐀-鿿]{2})', after)
                # His name and 본관 have fields of their own and the marriage is
                # the spouse link; his note is what is left: his father and
                # their children.
                rest = chunk[match.end() + (father.end() if father else 0):]
                note = (['父 ' + _fixed(father.group(1))] if father else []) + _children(rest)
                people.insert(entry + 1, {
                    '_partner': people[entry],
                    'hanja_name': husband, 'gender': '남',
                    'bon_gwan': _bon_gwan(home.group(1)) if home else '',
                    'birth_date': '', 'death_date': '', 'married_in': True, 'ganji_agrees': None,
                    'note': ' · '.join(note),
                    'raw': chunk[match.start():match.start() + 80], 'at': start,
                })
    for person in people:
        _days_into_dates(person)
    return people


DAY = re.compile(r'(기일|생일) (\d{1,2})월 (\d{1,2})일')


def _days_into_dates(person):
    """忌七月二十八日 is the day she died, though the year is not given: it
    goes in the 사망일 as --07-28, and a 생일 likewise in the 출생일, where a
    dated one has not already taken the place."""
    kept = []
    for item in filter(None, person['note'].split(' · ')):
        day = DAY.fullmatch(item)
        field = {'기일': 'death_date', '생일': 'birth_date'}.get(day.group(1)) if day else None
        if field and not person[field]:
            person[field] = '--%02d-%02d' % (int(day.group(2)), int(day.group(3)))
            continue
        kept.append(item)
    person['note'] = ' · '.join(kept)


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
    _reread_names(page, boxes)
    number = page_number(page)
    spread = pages(page)
    if spread:
        people, count = _read_ruled(boxes, spread, surname, page)
        if people:
            return {'people': _paired(people), 'bands': count, 'boxes': len(boxes), 'page': number}
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
    return {'people': _paired(people), 'bands': len(lowest), 'boxes': len(boxes), 'page': number}


PAGE_NUMBER = re.compile(r'\d{1,4}')


def page_number(page):
    """The page number printed across the head or foot of the page, or at its side.

    It is set in Arabic figures, lying across the page where every other line
    stands, so the page is read upright once more, over its margins alone. What
    is not read clearly is left for the reader to fill in, never guessed.
    """
    width, height = page.size
    margins = [(0, 0, width, int(height * 0.15)), (0, int(height * 0.85), width, height),
               (0, 0, int(width * 0.12), height), (int(width * 0.88), 0, width, height)]
    for box in margins:
        result, _ = _reader()(page.crop(box))
        found = [(len(text.strip()), score, text.strip()) for _, text, score in result or []
                 if PAGE_NUMBER.fullmatch(text.strip()) and score >= 0.9 and len(text.strip()) >= 2]
        if found:
            return str(int(max(found)[2]))
    return ''


def _paired(people):
    """Give each proposed person a key, and each spouse the key of the partner.

    Spouses are known from the page itself — 配 follows the one married, 夫 is
    named in the daughter's entry — so they can be joined when the page is
    filed, rather than one by one afterwards.
    """
    keys = {id(person): index for index, person in enumerate(people)}
    for index, person in enumerate(people):
        partner = person.pop('_partner', None)
        person['key'] = index
        person['spouse'] = keys.get(id(partner)) if partner is not None else None
    return people


def _reread_names(page, boxes):
    """Read again, twice the size, a name the whole page gave only half of.

    In a photo of the whole page the large characters of a name are read at the
    same small scale as the rest, and one of the two is sometimes lost: 子魯錫
    comes back as 子魯. The column alone, enlarged, is read whole.
    """
    from PIL import Image
    for box in boxes:
        text = box['text']
        if not text or text[0] not in '子女':
            continue
        given = _name(text[1:])
        if len(given) >= GIVEN_NAME:
            continue
        # The reading of a small crop turns on its margin, so a few are tried;
        # only one that keeps the character already read (魯 of 子魯) and adds
        # the one lost is taken, which a misreading of both (子曾錫) is not.
        for pad in (int(box['w'] * 0.17), int(box['w'] * 0.11), int(box['w'] * 0.23)):
            crop = page.crop((max(0, int(box['x'] - pad)), max(0, int(box['y'] - pad)),
                              min(page.width, int(box['x'] + box['w'] + pad)), min(page.height, int(box['y'] + box['h'] + pad))))
            crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
            try:
                result, _ = _reader()(crop.rotate(90, expand=True))
            except Exception:
                break
            # Turned a quarter, down the column is along the picture.
            pieces = sorted(result or [], key=lambda one: min(point[0] for point in one[0]))
            again = ''.join(_traditional(found) for _, found, _ in pieces)
            name = _name(again[1:])
            if again[:1] == text[0] and len(name) == GIVEN_NAME and name.startswith(given):
                box['text'] = text[0] + name + text[1 + len(given):]
                break


def _low(box, spread, shifts):
    """Whether a box begins well below the rule at the head of its band."""
    middle = box['x'] + box['w'] / 2
    for page in spread:
        if not page['x0'] <= middle < page['x1']:
            continue
        lines = page['lines']
        above = _above(lines, middle, box['y'] + box['h'] / 2)
        if not 0 < above < len(lines):
            return False
        top, bottom = _y(lines[above - 1], middle), _y(lines[above], middle)
        return box['y'] - top > (bottom - top) * 0.25
    return False


def _reread_by_generation_name(page, ordered):
    """Read again the son whose name does not carry his brothers' shared character.

    The sons of one generation share a character (돌림자): 魯錫, 魯世 and 魯佶.
    One whose name was read without it (子結上 for 子魯佶) was misread, so his
    name alone is cropped and read again at a few sizes, and the reading that
    begins with the shared character is taken — the most often read, if they
    differ.
    """
    from PIL import Image
    sons = [(box, _name(box['text'][1:])) for box in ordered if box['text'][:1] == '子']
    firsts = [name[0] for _, name in sons if len(name) == GIVEN_NAME]
    shared = max(set(firsts), key=firsts.count) if firsts else ''
    if not shared or firsts.count(shared) < 2:
        return
    for box, name in sons:
        if len(name) == GIVEN_NAME and name[0] == shared:
            continue
        votes = {}
        for pad in (0.08, 0.17, 0.25):
            for scale in (1.5, 2, 3):
                margin = int(box['w'] * pad)
                # The name, in its large type, fills the top of the column.
                crop = page.crop((max(0, int(box['x'] - margin)), max(0, int(box['y'] - margin)),
                                  min(page.width, int(box['x'] + box['w'] + margin)),
                                  min(page.height, int(box['y'] + box['h'] * 0.55 + margin))))
                crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
                try:
                    result, _ = _reader()(crop.rotate(90, expand=True))
                except Exception:
                    return
                pieces = sorted(result or [], key=lambda one: min(point[0] for point in one[0]))
                again = ''.join(_traditional(found) for _, found, _ in pieces)
                found = _name(again[1:]) if again[:1] == '子' else ''
                if len(found) == GIVEN_NAME and found[0] == shared:
                    votes[found] = votes.get(found, 0) + 1
        if votes:
            best = max(votes, key=votes.get)
            box['text'] = '子' + best + box['text'][1 + len(name):]


def _read_ruled(boxes, spread, surname, page=None):
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
    edge = max((one['x1'] for one in spread), default=0)
    for box in boxes:
        text = re.sub(r'\s', '', box['text'])
        # A column the photo cuts off at its edge is only part read: 女金震埴
        # comes back as 女金司.
        if box['x'] <= 2 or box['x'] + box['w'] >= edge - 2:
            continue
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
        if page is not None:
            _reread_by_generation_name(page, ordered)
        stream, starts, heads = '', set(), []
        for box in ordered:
            # A person's entry opens at the head of the band, in large type. A
            # column that begins well down it (女智, the daughters a husband's
            # entry lists) goes on with the entry before and opens none.
            if not _low(box, spread, shifts):
                starts.add(len(stream))
            heads.append((len(stream), box))
            # A bracket left open in the column before holds the hangul of a
            # spouse's name, which the reader turns into a run of stray hanja
            # (潔明東國) that would pass for forebears.
            before = heads[-2][1]['text'] if len(heads) > 1 else ''
            open_bracket = len(re.findall(r'[（(]', before)) > len(re.findall(r'[）)]', before))
            forebears = [] if open_bracket else _lineage(box['text'])
            stream += (LINEAGE + ''.join(forebears) + LINEAGE_END) if forebears else box['text']
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
    # A line with no name, no date and nothing said of it is no one to enter.
    people = [person for person in people if person['hanja_name'] or person['birth_date']
              or person['death_date'] or person['note'] not in ('', '이름 판독 안 됨')]
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
