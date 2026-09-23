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
    assert r._entries('子鐘煥吾鬥一九五四年甲午五月二十九日生', '金')[0]['hanja_name'] == '金鐘煥'
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
