"""The sample 族譜: a fictional 金海金氏 line of 25世 to 30世, twenty people.

Every name, date and place here is made up and belongs to no real family.
It fills a new book for the 예제 추가 button and the sale package's starter
book, so each can be looked round with every field of a record in use.
"""
from sqlalchemy import insert

BOOK = dict(
    title='金海金氏族譜', clan_name='金氏', bon_gwan='金海', branch_name='例示派',
    volume='1', founder='首露王', page='1', lineage='', page_breaks='',
    description='예제 족보입니다. 모든 인물은 가상 인물이며 실존 인물과 무관합니다.\n'
                '金海金氏 例示派 25世부터 30世까지 20명의 기록입니다.')

# key, korean, hanja, 世, gender, 본관, born, died, note
PEOPLE = [
    ('p1', '김영조', '金永祖', 25, '남', '金海', '1880-03-15', '1950-11-02',
     '字 仁甫(인보)\n號 靑山(청산)\n通政大夫(통정대부)\n墓는 靑山洞後山(청산동후산) 子坐(자좌) 合墳(합분)'),
    ('p2', '밀양박씨', '密陽朴氏', 25, '여', '密陽', '1884-07-21', '1960-02-10',
     '父 大仁(대인)'),
    ('p3', '김문수', '金文秀', 26, '남', '金海', '1905-06-10', '1975-08-20',
     '字 士文(사문)\n향교 전교 역임\n墓는 靑山洞後山(청산동후산) 午坐(오좌)'),
    ('p4', '이순례', '李順禮', 26, '여', '全州', '1908-09-03', '1990-12-01',
     '父 在明(재명)\n墓는 合墳(합분)'),
    ('p5', '김문희', '金文熙', 26, '여', '金海', '1910-02-01', '1995-03-03',
     '夫 崔明浩(최명호) 慶州人'),
    ('p6', '최명호', '崔明浩', 26, '남', '慶州', '1907-04-11', '1980-06-30',
     '父 秉浩(병호)\n子 在雄(재웅) · 女 貞淑(정숙)'),
    ('p7', '김지훈', '金志勳', 27, '남', '金海', '1932-11-05', '2008-01-17',
     '初名 志成(지성)\n서울대학교 사범대학 졸업\n중학교 교장 역임 · 국민훈장 목련장\n墓는 靑山洞後山(청산동후산) 子坐(자좌)'),
    ('p8', '권영자', '權英子', 27, '여', '安東', '1935-05-19', '',
     '父 泰植(태식)'),
    ('p9', '김지영', '金志英', 27, '남', '金海', '1936-08-08', '2015-10-12',
     '字 汝英(여영)\n농협 조합장 역임\n墓는 南山公園墓地(남산공원묘지)'),
    ('p10', '강숙자', '姜淑子', 27, '여', '晉州', '1938-12-24', '',
     '父 海文(해문)'),
    ('p11', '김지민', '金志敏', 27, '여', '金海', '1940-03-30', '',
     '夫 鄭大浩(정대호) 東萊人'),
    ('p12', '김태호', '金泰浩', 28, '남', '金海', '1958-02-14', '',
     '연세대학교 대학원 졸업 경영학 석사\n○○건설 대표이사 역임'),
    ('p13', '최미경', '崔美京', 28, '여', '慶州', '1960-10-02', '',
     '父 正洙(정수)\n이화여자대학교 졸업'),
    ('p14', '김태은', '金泰恩', 28, '여', '金海', '1962-07-07', '',
     '夫 尹成勳(윤성훈) 坡平人'),
    ('p15', '김태준', '金泰俊', 28, '남', '金海', '1965-04-25', '',
     '고려대학교 법과대학 졸업\n변호사'),
    ('p16', '한지현', '韓智賢', 28, '여', '淸州', '1968-01-12', '',
     '父 相文(상문)'),
    ('p17', '김민재', '金民宰', 29, '남', '金海', '1985-09-09', '',
     'KAIST 전산학과 졸업\n소프트웨어 개발자'),
    ('p18', '이서연', '李瑞妍', 29, '여', '全州', '1988-11-11', '',
     '父 承浩(승호)'),
    ('p19', '김민서', '金民瑞', 29, '여', '金海', '1990-05-05', '',
     '서울대학교 의과대학 졸업\n소아청소년과 전문의'),
    ('p20', '김도윤', '金道允', 30, '남', '金海', '2015-03-01', '', ''),
]
SPOUSES = [('p1', 'p2'), ('p3', 'p4'), ('p5', 'p6'), ('p7', 'p8'), ('p9', 'p10'),
           ('p12', 'p13'), ('p15', 'p16'), ('p17', 'p18')]
CHILDREN = [('p1', 'p3'), ('p2', 'p3'), ('p1', 'p5'), ('p2', 'p5'),
            ('p3', 'p7'), ('p4', 'p7'), ('p3', 'p9'), ('p4', 'p9'), ('p3', 'p11'), ('p4', 'p11'),
            ('p7', 'p12'), ('p8', 'p12'), ('p7', 'p14'), ('p8', 'p14'), ('p9', 'p15'), ('p10', 'p15'),
            ('p12', 'p17'), ('p13', 'p17'), ('p12', 'p19'), ('p13', 'p19'), ('p17', 'p20'), ('p18', 'p20')]


def create_sample(c, uid, books, persons, relations):
    """Fill a new sample book for the user; its id comes back."""
    bid = c.execute(insert(books).values(user_id=uid, **BOOK)).inserted_primary_key[0]
    ids = {}
    for key, korean, hanja, gen, gender, bon, born, died, note in PEOPLE:
        ids[key] = c.execute(insert(persons).values(
            book_id=bid, korean_name=korean, hanja_name=hanja, generation=gen, gender=gender,
            bon_gwan=bon, birth_date=born, death_date=died, note=note)).inserted_primary_key[0]
    for a, b in SPOUSES:
        x, y = sorted([ids[a], ids[b]])
        c.execute(insert(relations).values(source_id=x, target_id=y, kind='spouse'))
    for a, b in CHILDREN:
        c.execute(insert(relations).values(source_id=ids[a], target_id=ids[b], kind='parent'))
    return bid
