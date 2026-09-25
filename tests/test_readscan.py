# -*- coding: utf-8 -*-
"""The page grammar, held to the page — no reading engine needed for any of it."""
from backend import readscan as r


def test_a_year_and_its_간지_are_read_and_checked():
    assert r.ganji(1954) == '甲午'
    assert r.ganji(1983) == '癸亥'

    found = r._dates('一九八三年癸亥二月三日生')
    assert found[0]['date'] == '1983-02-03'
    assert found[0]['agrees'] is True

    # The two disagreeing is how a misread year gives itself away.
    wrong = r._dates('一九八四年癸亥二月三日生')
    assert wrong[0]['date'] == '1984-02-03'
    assert wrong[0]['agrees'] is False

    # Months and days are written 十一, 二十九, and the reader sometimes
    # drops an arabic numeral in among them.
    assert [one['date'] for one in r._dates('一九五四年甲午五月二十九日生')] == ['1954-05-29']
    assert [one['date'] for one in r._dates('一九八○年庚申六月十7日生')] == ['1980-06-17']
    assert [one['kind'] for one in r._dates('一九九〇年庚午十二月十一日卒')] == ['卒']


def test_an_entry_opens_with_子_女_or_配():
    band = '子壯純一九八三年癸亥二月三日生女珍英一九八○年庚申六月十七日生'
    read = r._entries(band, '金')
    assert [(one['hanja_name'], one['gender'], one['birth_date']) for one in read] == [
        ('金壯純', '남', '1983-02-03'),
        ('金珍英', '여', '1980-06-17'),
    ]

    # Someone who married in brings their own 본관 and their own family name.
    married = r._entries('配天安全氏京愛一九五六年丙申七月二十七日生', '金')
    assert married[0]['hanja_name'] == '全京愛'
    assert married[0]['bon_gwan'] == '天安'
    assert married[0]['married_in'] is True


def test_what_does_not_open_an_entry():
    # 子 is one of the twelve branches, so it stands inside every 庚子 on the page.
    assert r._entries('配金寧金氏美蘭一九六〇年庚子一月十一日生', '金')[0]['hanja_name'] == '金美蘭'
    assert len(r._entries('配金寧金氏美蘭一九六〇年庚子一月十一日生', '金')) == 1

    # And it stands inside the small notes the page sets in brackets.
    assert len(r._entries('配天安全氏京愛（子）一九五六年丙申七月二十七日生', '金')) == 1

    # A bracket the reader failed to close must not silence the rest of the page.
    swallowed = r._entries('配天安全氏京愛（社子起煥一九五六年丙申八月十一日生', '金')
    assert [one['hanja_name'] for one in swallowed] == ['全京愛', '金起煥']


def test_a_name_stops_where_the_name_stops():
    # The small 字 note that follows a name is read as more characters.
    assert r._entries('子鐘煥吾鬥一九五四年甲午五月二十九日生', '金')[0]['hanja_name'] == '金鍾煥'
    # 朴 is a surname in its own right; the simplified table turns it into 樸.
    assert r._entries('配密陽樸氏順南', '金')[0]['hanja_name'] == '朴順南'


def test_the_head_of_the_sheet_is_not_a_generation():
    # 권 and 쪽 marks are a few characters tall where an entry runs the band.
    page = [{'x': 100, 'y': 10, 'w': 60, 'h': 60, 'text': '年一九', 'score': 1.0},
            {'x': 100, 'y': 200, 'w': 60, 'h': 500, 'text': '子壯純', 'score': 1.0},
            {'x': 40, 'y': 210, 'w': 60, 'h': 480, 'text': '一九八三年癸亥二月三日生', 'score': 1.0}]
    grouped = r.bands(page)
    assert len(grouped) == 1
    # Right to left, as the page is read.
    assert [box['text'] for box in grouped[0]] == ['子壯純', '一九八三年癸亥二月三日生']


def test_dates_the_reader_half_loses():
    # 正月 is the first month, and 日 is sometimes left out before 卒.
    read = r._entries('子芝淑字聲後一八九九年已亥六月十三日生一九六八年戊中正月四日卒', '金')[0]
    assert (read['birth_date'], read['death_date']) == ('1899-06-13', '1968-01-04')
    # 已 and 中 are how the reader sees 己 and 申, and the 간지 still checks.
    assert read['ganji_agrees'] is True
    assert read['note'] == '字 聲後'

    later = r._entries('子相錫一九二一年辛酉十二月二十六日生一九八○年庚申三月五卒', '金')[0]
    assert later['death_date'] == '1980-03-05'

    # A 卒 misread still leaves the second date as the death.
    lost = r._entries('子芝淑一八九九年己亥六月十三日生一九六八年戊申正月四日年墓', '金')[0]
    assert lost['death_date'] == '1968-01-04'


def test_what_a_spouse_and_a_daughter_bring():
    # A spouse named with a numeral, and remembered on a day without a year.
    wife = r._entries('配慶州崔氏三順忌二九月十九日', '金')[0]
    assert (wife['hanja_name'], wife['bon_gwan']) == ('崔三順', '慶州')
    assert wife['note'] == '기일 9월 19일'

    # When the name after the 본관 is lost, the person is still proposed.
    assert r._entries('配全州崔氏（對）', '金')[0]['hanja_name'] == '崔'

    # A daughter's son belongs to her husband's line, not this book's.
    band = r._entries('女點先夫諸葛芝奉（제갈지봉）子柄律子相錫一九二一年辛酉十二月二十六日生', '金')
    assert [one['hanja_name'] for one in band] == ['金点先', '金相錫']
    assert band[0]['note'] == '夫 諸葛芝奉 · 子 柄律'


def test_columns_are_read_right_to_left_and_down():
    # One column broken into two pieces stays one column; two side by side do not.
    page = [{'x': 205, 'y': 2710, 'w': 268, 'h': 1163, 'text': '七年丁亥七月十六', 'score': 1.0},
            {'x': 168, 'y': 2698, 'w': 156, 'h': 287, 'text': '日生', 'score': 1.0},
            {'x': 433, 'y': 2726, 'w': 193, 'h': 561, 'text': '（종만）', 'score': 1.0},
            {'x': 374, 'y': 3300, 'w': 197, 'h': 568, 'text': '女一九四', 'score': 1.0}]
    assert ''.join(box['text'] for box in r.columns(page)) == '（종만）女一九四七年丁亥七月十六日生'


def test_misreads_no_name_or_본관_would_carry():
    # 踢 is all but never given in a name; it is 錫 with the wrong radical.
    assert r._entries('子相踢一九二一年辛酉十二月二十六日生', '金')[0]['hanja_name'] == '金相錫'
    # 摩州 is no 본관; 慶州 is one character away, and nothing else is.
    assert r._entries('配摩州崔氏三順', '金')[0]['bon_gwan'] == '慶州'
    assert r._entries('配天安全氏京愛', '金')[0]['bon_gwan'] == '天安'


def test_what_only_the_head_of_a_column_can_open():
    # With the boxes' beginnings known, an entry opens only at the head of one:
    # 東國(동국)女 names a spouse's father, and the sons a daughter's entry lists
    # after her husband (子柄) belong to his line.
    stream = '配天安全氏京愛（社潔明東國（子）女一九五六年丙申七月二十七日生' + '女金震填瑞興（）人寒暄堂宏弼後子' + '柄'
    starts = {0, stream.index('女金震'), len(stream) - 1}
    read = r._entries(stream, '金', starts)
    assert [one['hanja_name'] for one in read] == ['全京愛', '金氏']
    assert read[0]['birth_date'] == '1956-07-27'
    assert read[0]['note'] == '父 東國(확인 필요)'
    # An older book names a daughter by her husband and his 본관.
    assert read[1]['note'] == '사위 金震埴(瑞興人) · 딸 이름 미기재'


def test_a_date_is_not_a_name():
    # (지한)女 一九二四年: the reader's 女 before a year is no daughter named 一九.
    assert r._entries('女一九二四年甲子八月一日生', '金') == []


def test_a_name_may_end_in_子():
    assert r._entries('配金海金氏英子（召', '金')[0]['hanja_name'] == '金英子'
    # …but a 子 with a name after it opens the next entry.
    assert [one['hanja_name'] for one in r._entries('配金寧金氏美蘭子起煥', '金')] == ['金美蘭', '金起煥']


def test_the_margin_names_the_generation():
    assert r._generation('二十六世') == 26
    assert r._generation('三十一世') == 31
    assert r._generation('九世') == 9
    assert r._generation('十川') is None
    assert r.GENERATION_LABEL.match('庫一十川')


def test_the_two_pages_of_a_spread_are_read_as_one_row():
    # Where the pages meet, each row's rule on the left meets its rule on the
    # right, even when one page shows a rule the other lost.
    left = {'x0': 0, 'x1': 100, 'lines': [{'slope': 0.0, 'base': y} for y in (100, 400, 700)]}
    right = {'x0': 100, 'x1': 200, 'lines': [{'slope': 0.0, 'base': y} for y in (-150, 105, 395, 705)]}
    assert r._aligned([left, right]) == [1, 0]


def test_a_spouse_whose_본관_lost_a_character_is_still_proposed():
    read = r._entries('配金金氏美蘭一九六〇年庚子一月十一日生', '金')[0]
    assert (read['hanja_name'], read['bon_gwan'], read['birth_date']) == ('金美蘭', '', '1960-01-11')


def test_a_family_that_starts_on_the_left_page_is_set_apart():
    # The right page (side 1) carries 30世 and 31世 on. On the left page (side 0)
    # 鎭元 of 27世 and his daughter of 28世 are older than any of them, so a new
    # family starts; its 30世 grandson to their left is of it, while the entry
    # that ran over the gutter, right of that family's edge, stays with the old.
    def one(name, generation, side, x):
        return {'hanja_name': name, 'generation': generation, '_side': side,
                '_box': {'x': x, 'w': 80}}
    people = [one('金鍾煥', 30, 1, 3200), one('金壯純', 31, 1, 3280),
              one('金順熙', 30, 1, 1930), one('', 30, 0, 1500),
              one('金氏', 28, 0, 1255), one('金鎭元', 27, 0, 470), one('金鍾煥', 30, 0, 355)]
    r._families(people, 1)
    assert [(p['hanja_name'], p['family']) for p in people] == [
        ('金鍾煥', 0), ('金壯純', 0), ('金順熙', 0), ('', 0),
        ('金氏', 1), ('金鎭元', 1), ('金鍾煥', 1)]
