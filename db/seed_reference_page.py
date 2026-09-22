"""Import the legible records of 淸道金氏大同譜 卷之九 外鰲山, pages 116 and 618.

Page 116 carries 二十一世 to 二十六世, page 618 carries 二十六世 to 三十一世.  The
printed dates are lunar and are stored here in ISO form, which is what the app's
date fields accept.  Names, generations and parent links come from the large
glyphs; the small annotations that the photograph cannot resolve are left out and
called out in each person's note.  Re-running the script updates in place.
"""
from sqlalchemy import or_, select

from backend.main import books, engine, persons, relations

BOOK_ID = 1
BOOK = dict(
    title='淸道金氏大同譜',
    clan_name='金氏',
    bon_gwan='淸道',
    branch_name='外鰲山',
    volume='9',
    description=(
        '始祖 英憲公(金之岱)\n'
        '청도김씨대동보 권9 외오산 116쪽(21~26세)과 618쪽(26~31세)의 판독 가능한 기록입니다. '
        '원본 날짜는 음력이며 ISO 형식으로 옮겼습니다. '
        '116쪽 소주(小註)와 618쪽 26~29세 칸은 사진으로 판독되지 않아 비워 두었습니다.'
    ),
)


# Everyone on these pages is 淸道 金氏 unless they married in from another clan.
def person(hanja, generation, gender, birth='', death='', bon_gwan='淸道', note=''):
    return dict(hanja_name=hanja, generation=generation, gender=gender,
                birth_date=birth, death_date=death, bon_gwan=bon_gwan, note=note)


# Insertion order is the printed order of each 世 row, read right to left.
PEOPLE = {
    # --- 卷之九 116쪽 · 二十一世 ~ 二十六世 ---
    '김홍묵': person('金洪默', 21, '남', note='卷之九 一一六쪽 기록. 字와 생몰 小註는 판독 미확정.'),
    '김재우': person('金在佑', 22, '남'),
    '김재덕': person('金在德', 22, '남'),
    '김환용': person('金煥鎔', 23, '남', birth='1887-01-29',
                  note='字 恭一(공일). 配 溫陽方氏(온양방씨) — 이름 판독 미확정.'),
    '김병현': person('金秉鉉', 23, '남'),
    '김기창': person('金淇昶', 24, '남', birth='1919-04-16', death='1990-01-17',
                  note='系子, 生父 東錫(동석). 一名 英俊(영준). '
                       '配 安東金氏 昌烈(창열)女 一九二六年 十月 二十日生 — 이름 판독 미확정.'),
    '김기선': person('金淇善', 24, '남', note='字 其五(기오).'),
    '김용근': person('金容根', 25, '남', birth='1952-09-18'),
    '오선옥': person('吳善玉', 25, '여', birth='1955-06-05', bon_gwan='海州'),
    '김봉근': person('金鳳根', 25, '남', note='一名 鳳珠(봉주). 생년 판독 미확정.'),
    '이순아': person('李順兒', 25, '여', birth='1962-04-09', bon_gwan='慶州'),
    '김점술': person('金点述', 25, '여', birth='1959-01-24'),
    '김인영': person('金仁榮', 25, '남', birth='1966-01-10',
                  note='系子, 生父 漢彦(한언). 字 陽次(양차). 一名 春植(춘식).'),
    '김수진': person('金壽珍', 26, '남', birth='1978-02-07'),
    '김성진': person('金成珍', 26, '남', birth='1981-04-11'),
    '김상환': person('金相煥', 26, '남', birth='1988-09-20'),
    '김영환': person('金榮煥', 26, '남', birth='1989-07-23'),
    '김승수': person('金勝洙', 26, '남'),
    '김승국': person('金勝國', 26, '남'),
    # --- 卷之九 618쪽 · 三十世 ~ 三十一世 ---
    # 二十六世~二十九世 칸은 앞 쪽에서 이어지는 주기(註記)뿐이라 인물을 넣지 않았습니다.
    '김종환': person('金鍾煥', 30, '남', birth='1954-05-29'),
    '전경애': person('全京愛', 30, '여', birth='1956-07-27', bon_gwan='天安', note='父 東國(동국)'),
    '김기환': person('金起煥', 30, '남', birth='1956-08-11'),
    '김미란': person('金美蘭', 30, '여', birth='1960-01-11', bon_gwan='金寧', note='父 相範(상범)'),
    '김경환': person('金慶煥', 30, '남', birth='1958-10-25'),
    '박순남': person('朴順南', 30, '여', birth='1954-05-03', bon_gwan='密陽', note='父 泰鎬(태호)'),
    '김순희': person('金順熙', 30, '여'),
    '김장순': person('金壯純', 31, '남', birth='1983-02-03'),
    '김진영': person('金珍英', 31, '여', birth='1980-06-17', note='女 智恩(지은)·睿恩(예은)'),
    '김흥한': person('金興漢', 31, '남', bon_gwan='安東', note='父 敬鎭(경진)'),
    '김경순': person('金磬純', 31, '남', birth='1985-11-24'),
    '강희선': person('姜熙善', 31, '여', birth='1987-06-03', bon_gwan='晋州', note='父 東原(동원)'),
    '김형순': person('金亨純', 31, '남', birth='1992-06-04'),
    '김강순': person('金康純', 31, '남', birth='1981-08-18'),
    '김소정': person('金昭貞', 31, '여', birth='1990-12-11'),
}

# Each father heads the column his children are printed under; the mother is added
# alongside so the tree view links both parents.
FAMILIES = [
    ('김홍묵', None, ['김재우', '김재덕']),
    ('김재우', None, ['김환용']),
    ('김재덕', None, ['김병현']),
    ('김환용', None, ['김기창']),
    ('김병현', None, ['김기선']),
    ('김기창', None, ['김용근', '김봉근', '김점술']),
    ('김기선', None, ['김인영']),
    ('김용근', '오선옥', ['김수진', '김성진']),
    ('김봉근', '이순아', ['김상환', '김영환']),
    ('김인영', None, ['김승수', '김승국']),
    ('김종환', '전경애', ['김장순', '김진영']),
    ('김기환', '김미란', ['김경순', '김형순']),
    ('김경환', '박순남', ['김강순', '김소정']),
]

SPOUSES = [
    ('김용근', '오선옥'),
    ('김봉근', '이순아'),
    ('김종환', '전경애'),
    ('김기환', '김미란'),
    ('김경환', '박순남'),
    ('김진영', '김흥한'),
    ('김경순', '강희선'),
]


def ensure_relation(connection, source_id, target_id, kind):
    if kind == 'spouse':
        source_id, target_id = sorted((source_id, target_id))
        condition = or_(
            (relations.c.source_id == source_id) & (relations.c.target_id == target_id),
            (relations.c.source_id == target_id) & (relations.c.target_id == source_id),
        )
    else:
        condition = (relations.c.source_id == source_id) & (relations.c.target_id == target_id)
    found = connection.execute(select(relations.c.id).where(condition, relations.c.kind == kind)).scalar_one_or_none()
    if found is None:
        connection.execute(relations.insert().values(source_id=source_id, target_id=target_id, kind=kind))


with engine.begin() as connection:
    connection.execute(books.update().where(books.c.id == BOOK_ID).values(**BOOK))
    ids = {}
    for korean_name, values in PEOPLE.items():
        person_id = connection.execute(select(persons.c.id).where(
            persons.c.book_id == BOOK_ID, persons.c.korean_name == korean_name
        )).scalar_one_or_none()
        if person_id is None:
            person_id = connection.execute(persons.insert().values(
                book_id=BOOK_ID, korean_name=korean_name, **values
            )).inserted_primary_key[0]
        else:
            connection.execute(persons.update().where(persons.c.id == person_id).values(**values))
        ids[korean_name] = person_id
    for husband, wife in SPOUSES:
        ensure_relation(connection, ids[husband], ids[wife], 'spouse')
    for father, mother, children in FAMILIES:
        for parent in (father, mother):
            if parent:
                for child in children:
                    ensure_relation(connection, ids[parent], ids[child], 'parent')

print(f'{len(PEOPLE)} people from 卷之九 pages 116 and 618 applied to family book {BOOK_ID}.')
