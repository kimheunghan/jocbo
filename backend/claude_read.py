# -*- coding: utf-8 -*-
"""Read a photographed 족보 page with Claude.

The local reader knows hanja only: it turns the hangul the page prints beside
every name into stray characters, and with them the notes, a spouse's father and
anything written in hangul. Claude reads both scripts, and the page grammar is
put to it in words, so it gives back the same proposal the local reader does —
one line per person, spouses and the family a spread starts marked — for a
person to correct before anything is filed.

The photo leaves this computer: it is sent to Anthropic, which is why this is
used only when asked for and only with a key the user has given.
"""
import base64
import io
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / '.env'
MODEL = 'claude-opus-5'
# Claude reads an image up to this long edge at full detail; beyond it the
# picture is scaled down, so each page is cut out and sent on its own.
LONG_EDGE = 2576


def available():
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


def stored_key():
    """The key the user saved, or one set in the environment."""
    if os.getenv('ANTHROPIC_API_KEY'):
        return os.getenv('ANTHROPIC_API_KEY')
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding='utf-8').splitlines():
            name, _, value = line.partition('=')
            if name.strip() == 'ANTHROPIC_API_KEY' and value.strip():
                return value.strip()
    return ''


def save_key(key):
    """Keep the key in .env beside the program, which git leaves alone."""
    lines = []
    if ENV_FILE.exists():
        lines = [line for line in ENV_FILE.read_text(encoding='utf-8').splitlines()
                 if line.partition('=')[0].strip() != 'ANTHROPIC_API_KEY']
    if key:
        lines.append('ANTHROPIC_API_KEY=' + key)
    ENV_FILE.write_text('\n'.join(lines) + ('\n' if lines else ''), encoding='utf-8')


def client(key=None):
    import anthropic
    key = key or stored_key()
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


def check_key(key):
    """Whether Anthropic accepts the key, asked with the cheapest call there is."""
    client(key).models.retrieve(MODEL)


def _pictures(path):
    """The photo as Claude should see it: each page of a spread on its own,
    the right-hand page first, as the book is read."""
    from PIL import Image, ImageOps
    from backend import readscan
    with Image.open(path) as page:
        page = ImageOps.exif_transpose(page).convert('RGB')
    try:
        spread = readscan.pages(page)
    except Exception:
        spread = []
    cuts = [(one['x0'], one['x1']) for one in spread] or [(0, page.width)]
    pictures = []
    for x0, x1 in reversed(cuts):
        # A little of the next page is kept, so an entry that runs over the
        # gutter is not cut in half.
        margin = int(page.width * 0.02)
        part = page.crop((max(0, x0 - margin), 0, min(page.width, x1 + margin), page.height))
        scale = LONG_EDGE / max(part.size)
        if scale < 1:
            part = part.resize((round(part.width * scale), round(part.height * scale)), Image.LANCZOS)
        buffer = io.BytesIO()
        part.save(buffer, 'JPEG', quality=92)
        pictures.append(base64.standard_b64encode(buffer.getvalue()).decode('ascii'))
    return pictures


PERSON = {
    'type': 'object',
    'properties': {
        'hanja_name': {'type': 'string'},
        'korean_name': {'type': 'string'},
        'gender': {'type': 'string', 'enum': ['남', '여', '미상']},
        'generation': {'type': 'integer'},
        'bon_gwan': {'type': 'string'},
        'birth_date': {'type': 'string'},
        'death_date': {'type': 'string'},
        'married_in': {'type': 'boolean'},
        'note': {'type': 'string'},
        'family': {'type': 'integer'},
        'spouse': {'type': 'integer'},
    },
    'required': ['hanja_name', 'korean_name', 'gender', 'generation', 'bon_gwan', 'birth_date',
                 'death_date', 'married_in', 'note', 'family', 'spouse'],
    'additionalProperties': False,
}
SCHEMA = {
    'type': 'object',
    'properties': {'page': {'type': 'string'}, 'people': {'type': 'array', 'items': PERSON}},
    'required': ['page', 'people'],
    'additionalProperties': False,
}

INSTRUCTIONS = """You are transcribing one photographed spread of a Korean genealogy (족보) so that its people can be entered into a family-tree program. A person will check every line against the photo before anything is saved, so a blank is better than a guess.

How the page is laid out
- Text runs in vertical columns read top to bottom, columns right to left. With two pages, the right-hand page is read first. The images you get are the pages cut apart, right-hand page first.
- Horizontal rules divide each page into bands; each band is one generation. The margin names each band's generation (二十六世 = 26). Both pages of a spread share the same bands.
- An entry opens with a large 子 (son of the line), 女 (daughter of the line) or 配 (a wife who married in), followed by the name in large characters and its hangul reading in small type beside it (相助 상조).
- Children of the line are printed without the family name; the family name is the book's (given below).
- 配 is written 配 <본관 two characters><family name>氏<given name>(<hangul of all of it>) <father's name>(<hangul>)女 <birth date>: e.g. 配天安全氏京愛(천안전씨경애)東國(동국)女 一九五六年丙申七月二十七日生. She is the wife of the son whose entry comes just before her.
- A daughter's entry may name her husband: 夫金熙旋(김희선) 瑞興(서흥)人 父學龍(학룡) 子東炫 女志娟. The husband, his 본관 (瑞興) and his father belong to her entry; the 子 and 女 after him are their children of his line and are NOT people of this book.
- An older style names a daughter only by her husband: 女嚴柱華 寧越人 — the daughter's own name is not given.
- Dates are written 一九五四年甲午五月二十九日生 (born) and …卒 (died); 忌 is the day a death is remembered, often without a year. The 간지 (甲午) must agree with the year; use it to check the digits.
- Everything else small in an entry is a note: 字, 初名, 一名, 號, 系子/生父, 忌, 墓 (grave place and the way it faces, 坐), 設壇, and lines written in hangul such as education, career and awards.
- Faint mirror-image characters showing through from the other side of the paper are not part of this page; ignore them.
- A band may begin with the tail of an entry that started on the previous page (text with no 子/女/配 before it). That is not a person; skip it.

What to give back: one item per person, in reading order.
- hanja_name: the full name in hanja with the family name (the book's family name for 子/女; the printed family name for 配). For a daughter named only by her husband, the family name followed by 氏 (e.g. 金氏).
- korean_name: the name in hangul, from the printed reading where there is one (전경애, 김상조). For 金氏 write 김씨.
- gender: 남 for 子 and for a husband, 여 for 女 and 配, 미상 if unknown.
- generation: from the margin label of the band; 0 if it cannot be told.
- bon_gwan: for 配 and for a husband, their 본관 in hanja (天安, 瑞興); otherwise "".
- birth_date / death_date: as the page gives them, in digits: YYYY-MM-DD, or YYYY-MM or YYYY when only that much is given, or --MM-DD for a month and day with no year. Do not convert from the lunar calendar. "" when not given.
- married_in: true for 配 and for a husband; false for 子 and 女.
- note: the rest of the person's own entry, in the page's own words, each item followed by its hangul reading in brackets where the page prints one, items joined with " · ". For example: 字 玉汝 · 忌 六月四日 · 墓 陽洞後山(양동후산) 設壇碑(설단비). Keep hangul lines (연세대학교 대학원 졸업 교육공학 석사 · 2014.8.31 대통령표창) as written. For 配 begin with 父 and her father's name (父 東國(동국)). Leave out what has a field of its own (name, 본관, dates) and what the spouse link already says.
- A daughter's note is hers alone: it stops where 夫 begins. Her husband's name, 본관, father and their children go on his own line, not hers. For a daughter named only by her husband, her note is 딸 이름 미기재.
- family: 0 for the family carried on from the right-hand page. If the left-hand page starts another family — a person there of an older generation (smaller number) than anyone on the right-hand page begins it — that family and everyone printed to the left of its right-most column is 1. Otherwise 0.
- spouse: for 配, the index (0-based, in this list) of the son she married; for a husband, the index of the daughter he married; -1 for everyone else.
- For every daughter's husband named with 夫, and for the husband of a daughter named only by him, add a separate item right after her: hanja_name his full name, korean_name his reading, gender 남, bon_gwan his 본관, married_in true, family as hers, generation as hers, spouse her index, and note only what is left of him: his father and their children, e.g. 父 學龍(학룡) · 子 東炫 · 女 志娟. Not his name, not his 본관, not whose husband he is.

Accuracy
- Read every character from the photo. Where one cannot be made out, write □ in its place rather than guessing; where a whole name cannot be read, leave hanja_name "" and put 이름 판독 안 됨 in the note.
- Check each date against its 간지, and each name against its printed hangul reading.

The page number
- `page` is the page number printed in Arabic figures at the head, foot or side of the page (612). With two pages, give the right-hand page's. If no number can be read clearly, give an empty string."""


def read(path, book):
    """Propose the people on a photographed page, in the local reader's shape."""
    import anthropic
    surname = (book.get('clan_name') or '').replace('氏', '').strip()[:1]
    context = (f"The book: {book.get('title') or ''} — family name {surname or '(not given)'}"
               f"{', 본관 ' + book['bon_gwan'] if book.get('bon_gwan') else ''}"
               f"{', 파 ' + book['branch_name'] if book.get('branch_name') else ''}"
               f"{', traced from ' + book['lineage'] if book.get('lineage') else ''}.")
    pictures = _pictures(path)
    content = []
    for index, data in enumerate(pictures):
        side = ('right-hand page (read first)' if index == 0 else 'left-hand page') if len(pictures) > 1 else 'the page'
        content.append({'type': 'text', 'text': f'Image {index + 1}: {side}.'})
        content.append({'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': data}})
    content.append({'type': 'text', 'text': context + '\n\nTranscribe the people on this spread.'})
    # A reading can run to minutes and a long answer, so it is streamed; a
    # decline by the model's safeguards is retried on another model rather
    # than handed back empty.
    with client().beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        betas=['server-side-fallback-2026-07-01'],
        fallbacks='default',
        thinking={'type': 'adaptive'},
        output_config={'effort': 'high', 'format': {'type': 'json_schema', 'schema': SCHEMA}},
        system=INSTRUCTIONS,
        messages=[{'role': 'user', 'content': content}],
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason == 'refusal':
        raise RuntimeError('Claude가 이 사진의 판독을 거절했습니다.')
    if message.stop_reason == 'max_tokens':
        raise RuntimeError('판독 결과가 너무 길어 끊겼습니다. 한 쪽씩 찍어 올려 주십시오.')
    text = next((block.text for block in message.content if block.type == 'text'), '')
    answer = json.loads(text)
    page = answer.get('page', '').strip()
    return {'people': shaped(answer['people']), 'bands': 0, 'boxes': 0, 'engine': 'claude',
            'page': page if page.isdigit() else '',
            'usage': {'input': message.usage.input_tokens, 'output': message.usage.output_tokens}}


def shaped(people):
    """Claude's answer in the local reader's shape, with its pairings checked."""
    out = []
    for index, one in enumerate(people):
        spouse = one.get('spouse', -1)
        out.append({
            'hanja_name': one.get('hanja_name', ''),
            'korean_name': one.get('korean_name', ''),
            'gender': one.get('gender') if one.get('gender') in ('남', '여', '미상') else '미상',
            'generation': one.get('generation') or None,
            'bon_gwan': one.get('bon_gwan', ''),
            'birth_date': one.get('birth_date', ''),
            'death_date': one.get('death_date', ''),
            'married_in': bool(one.get('married_in')),
            'ganji_agrees': None,
            'note': one.get('note', ''),
            'family': 1 if one.get('family') == 1 else 0,
            'band': 0,
            'key': index,
            'spouse': spouse if isinstance(spouse, int) and 0 <= spouse < len(people) and spouse != index else None,
        })
    return out
