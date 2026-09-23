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
