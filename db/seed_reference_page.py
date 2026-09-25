"""Import 淸道金氏大同譜 卷之九 玄風琴山, pages 116 and 618, and what has been
added to the book since.

Page 116 carries 二十一世 to 二十六世, page 618 carries 二十六世 to 三十一世.  The
printed dates are lunar and are stored here in ISO form, which is what the app's
date fields accept.  Names, generations and parent links come from the large
glyphs; the small annotations that the photograph cannot resolve are left out and
called out in each person's note.  Later generations and the forebears of people
who married in were entered by hand afterwards and are kept here so a fresh
install holds the same book.  Re-running the script updates in place.
"""
import os

from sqlalchemy import or_, select

from backend.main import books, engine, meta, persons, relations, users

BOOK_ID = 1
BOOK = dict(
    title='淸道金氏大同譜',
    clan_name='金氏',
    bon_gwan='淸道',
    branch_name='玄風琴山',
    volume='9',
    founder='英憲公(金之岱)',
    page='617',
    lineage='芝淑',
    description='청도김씨대동보 권9 현풍금산 116쪽(21~26세)과 618쪽(26~31세)의 판독 가능한 기록입니다. 원본 날짜는 음력이며 ISO 형식으로 옮겼습니다. 116쪽 소주(小註)와 618쪽 26~29세 칸은 사진으로 판독되지 않아 비워 두었습니다.',
)


# Everyone in this book is 淸道 金氏 unless they married in from another clan.
def person(hanja, generation, gender, birth='', death='', bon_gwan='淸道', note=''):
    return dict(hanja_name=hanja, generation=generation, gender=gender,
                birth_date=birth, death_date=death, bon_gwan=bon_gwan, note=note)


# Insertion order is the printed order of each 世 row, read right to left.
PEOPLE = {
    # --- 21세 ---
    '김홍묵': person('金洪默', 21, '남', note='卷之九 一一六쪽 기록. 字와 생몰 小註는 판독 미확정.'),
    # --- 22세 ---
    '김재우': person('金在佑', 22, '남', death='1890-03-31'),
    '김재덕': person('金在德', 22, '남'),
    # --- 23세 ---
    '김환용': person('金煥鎔', 23, '남', birth='1887-01-29', note='字 恭一(공일). 配 溫陽方氏(온양방씨) — 이름 판독 미확정.'),
    '김병현': person('金秉鉉', 23, '남'),
    # --- 24세 ---
    '김기창': person('金淇昶', 24, '남', birth='1919-04-16', death='1990-01-17', note='系子, 生父 東錫(동석). 一名 英俊(영준). 配 安東金氏 昌烈(창열)女 一九二六年 十月 二十日生 — 이름 판독 미확정.'),
    '김기선': person('金淇善', 24, '남', note='字 其五(기오).'),
    # --- 25세 ---
    '김용근': person('金容根', 25, '남', birth='1952-09-18'),
    '오선옥': person('吳善玉', 25, '여', birth='1955-06-05', bon_gwan='海州'),
    '김봉근': person('金鳳根', 25, '남', note='一名 鳳珠(봉주). 생년 판독 미확정.'),
    '이순아': person('李順兒', 25, '여', birth='1962-04-09', bon_gwan='慶州'),
    '김점술': person('金点述', 25, '여', birth='1959-01-24'),
    '김인영': person('金仁榮', 25, '남', birth='1966-01-10', note='系子, 生父 漢彦(한언). 字 陽次(양차). 一名 春植(춘식).'),
    # --- 26세 ---
    '김수진': person('金壽珍', 26, '남', birth='1978-02-07'),
    '김성진': person('金成珍', 26, '남', birth='1981-04-11'),
    '김상환': person('金相煥', 26, '남', birth='1988-09-20'),
    '김영환': person('金榮煥', 26, '남', birth='1989-07-23'),
    '김승수': person('金勝洙', 26, '남'),
    '김승국': person('金勝國', 26, '남'),
    # --- 28세 ---
    '김지숙': person('金芝淑', 28, '남', birth='1899-06-13', death='1968-01-04', note='字 聲後\n墓 陽洞後山(양동후산) 酉坐(유좌)'),
    '최평': person('崔平', 28, '여', death='--09-19', bon_gwan='全州', note='配 全州崔氏(전주최씨) 鶴林(학림) 女 忌 九月十九日\n墓는 同原酉坐(동원유좌)'),
    # --- 29세 ---
    '최삼순': person('崔三順', 29, '여', bon_gwan='京主', note='父 鍾翰(종한)'),
    '김점선': person('金点先', 29, '여'),
    '김상석': person('金相錫', 29, '남', birth='1921-12-26', death='1980-03-05', note='字 龍鶴(용학)\n墓는 大邱廣域市 達城郡 瑜伽面 陽里 山 一七一－三 酉坐封墳(유좌봉분)\n碑石 및 床石(비석 및 상석)있음'),
    '제갈지봉': person('諸葛芝奉', 29, '남', bon_gwan='', note='子 炳律(병률)'),
    # --- 30세 ---
    '김종환': person('金鍾煥', 30, '남', birth='1954-05-29'),
    '전경애': person('全京愛', 30, '여', birth='1956-07-27', bon_gwan='天安', note='父 東國(동국)'),
    '김기환': person('金起煥', 30, '남', birth='1956-08-11'),
    '김미란': person('金美蘭', 30, '여', birth='1960-01-11', bon_gwan='金寧', note='父 相範(상범)'),
    '김경환': person('金慶煥', 30, '남', birth='1958-10-25'),
    '박순남': person('朴順南', 30, '여', birth='1954-05-03', bon_gwan='密陽', note='父 泰鎬(태호)'),
    '김순희': person('金順熙', 30, '여'),
    '김정환': person('金正煥', 30, '남', birth='1948-02-26', note='初名 正熙'),
    '황혜숙': person('黃慧淑', 30, '여', birth='1947-07-16', bon_gwan='尚州'),
    # --- 31세 ---
    '김진영': person('金珍英', 31, '여', birth='1980-06-17', note='女 智恩(지은)·睿恩(예은)'),
    '김장순': person('金壯純', 31, '남', birth='1983-02-03'),
    '김흥한': person('金興漢', 31, '남', bon_gwan='安東', note='父 敬鎭(경진)'),
    '김경순': person('金磬純', 31, '남', birth='1985-11-24'),
    '강희선': person('姜熙善', 31, '여', birth='1987-06-03', bon_gwan='晋州', note='父 東原(동원)'),
    '김형순': person('金亨純', 31, '남', birth='1992-06-04'),
    '김강순': person('金康純', 31, '남', birth='1981-08-18'),
    '김소정': person('金昭貞', 31, '여', birth='1990-12-11'),
    # --- 32세 ---
    '김지은': person('金智恩', 32, '여', bon_gwan='安東'),
    '김예은': person('金睿恩', 32, '여', bon_gwan='安東'),
}

SPOUSES = [
    ('김종환', '전경애'),
    ('김용근', '오선옥'),
    ('김봉근', '이순아'),
    ('김기환', '김미란'),
    ('김경환', '박순남'),
    ('김흥한', '김진영'),
    ('김경순', '강희선'),
    ('김상석', '최삼순'),
    ('김지숙', '최평'),
    ('제갈지봉', '김점선'),
    ('김정환', '황혜숙'),
]

# (아버지, 어머니, 자녀들) — 어느 한쪽만 기록된 경우 나머지는 None.
FAMILIES = [
    ('김종환', '전경애', ['김진영', '김장순']),
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
    ('김기환', '김미란', ['김경순', '김형순']),
    ('김경환', '박순남', ['김강순', '김소정']),
    ('김흥한', '김진영', ['김지은', '김예은']),
    ('김상석', '최삼순', ['김종환']),
    ('김지숙', None, ['김상석', '김점선']),
    ('김상석', None, ['김정환', '김기환', '김경환', '김순희']),
]

def ensure_relation(connection, source_id, target_id, kind):
    existing = connection.execute(select(relations.c.id).where(
        relations.c.kind == kind,
        or_(
            (relations.c.source_id == source_id) & (relations.c.target_id == target_id),
            (relations.c.source_id == target_id) & (relations.c.target_id == source_id),
        ),
    )).scalar_one_or_none()
    if existing is None:
        connection.execute(relations.insert().values(
            source_id=source_id, target_id=target_id, kind=kind))


# The book belongs to whoever is using this install. On a machine that already
# has an account it goes to that one; on a bare machine the owner's account is
# made so the same email opens the same book everywhere.
OWNER = os.getenv('JOCBO_EMAIL', 'hung6789@naver.com')
OWNER_PASSWORD = '5140cae88a4b872bba90894cd8ea3a7b:3515ec0db96fd5dbd7ff518ab28dad8a75309208b5ff0d08bf807c33390605ecf2fbd79d8a7e87e6df2405f2289be98caa16969516bc9a8bcbd2c5a539a297cb'


def ensure_book(connection):
    if connection.execute(select(books.c.id).where(books.c.id == BOOK_ID)).scalar_one_or_none():
        return
    user_id = connection.execute(select(users.c.id).where(users.c.email == OWNER)).scalar_one_or_none()
    if user_id is None:
        # An account already here is the person's own, whatever they signed up as.
        user_id = connection.execute(select(users.c.id).order_by(users.c.id)).scalars().first()
    if user_id is None:
        user_id = connection.execute(users.insert().values(
            email=OWNER, password_hash=OWNER_PASSWORD)).inserted_primary_key[0]
        print(f'Account created: {OWNER} / Jocbo2026!  (change it after signing in)')
    connection.execute(books.insert().values(id=BOOK_ID, user_id=user_id, **BOOK))


meta.create_all(engine)
with engine.begin() as connection:
    ensure_book(connection)
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

print(f'{len(PEOPLE)} people and {len(SPOUSES)} marriages applied to family book {BOOK_ID}.')
print(f'Book {BOOK_ID} belongs to the account already on this install, or to {OWNER}.')
