# -*- coding: utf-8 -*-

import sys
import re
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

def get_shumbun(year):
    """
    春分の日の取得
    https://ja.wikipedia.org/wiki/%E6%98%A5%E5%88%86%E3%81%AE%E6%97%A5
    """
    defs = (
        (1900, 1923, 21, 21, 21, 22),
        (1924, 1959, 21, 21, 21, 21),
        (1960, 1991, 20, 21, 21, 21),
        (1992, 2023, 20, 20, 21, 21),
        (2024, 2055, 20, 20, 20, 21),
        (2056, 2091, 20, 20, 20, 20),
        (2092, 2099, 19, 20, 20, 20),
        (2100, 2123, 20, 21, 21, 21),
        (2124, 2155, 20, 20, 21, 21),
        (2156, 2187, 20, 20, 20, 21),
        (2188, 2199, 20, 20, 20, 20),
        (2200, 2223, 21, 21, 21, 21),
        (2224, 2255, 20, 21, 21, 21),
        (2256, 2287, 20, 20, 21, 21),
        (2288, 2299, 20, 20, 20, 21),
    )
    for entry in defs:
        if year >= entry[0] and year <= entry[1]:
            x = year % 4
            d = entry[2 + x]
            return datetime(year, 3, d)
    return None

def get_shubun(year):
    """
    秋分の日の取得
    https://ja.wikipedia.org/wiki/%E7%A7%8B%E5%88%86%E3%81%AE%E6%97%A5
    """
    defs = (
        (1900, 1919, 23, 24, 24, 24),
        (1920, 1947, 23, 23, 24, 24),
        (1948, 1979, 23, 23, 23, 24),
        (1980, 2011, 23, 23, 23, 23),
        (2012, 2043, 22, 23, 23, 23),
        (2044, 2075, 22, 22, 23, 23),
        (2076, 2099, 22, 22, 22, 23),
        (2100, 2107, 23, 23, 23, 24),
        (2108, 2139, 23, 23, 23, 23),
        (2140, 2167, 22, 23, 23, 23),
        (2168, 2199, 22, 22, 23, 23),
        (2200, 2227, 23, 23, 23, 24),
        (2228, 2263, 23, 23, 23, 23),
        (2264, 2291, 22, 23, 23, 23),
        (2292, 2299, 22, 22, 23, 23),
    )
    for entry in defs:
        if year >= entry[0] and year <= entry[1]:
            x = year % 4
            d = entry[2 + x]
            return datetime(year, 9, d)
    return None

def get_holidays(year):
    """
    指定した年の祝日・国民の休日を取得する
    """
    days = []
    # 固定日付の祝日
    for m, d in ((1,1), (2,11), (4,29), (5,3)
        , (5,4), (5,5), (8,11), (11,3), (11,23)):
        # オリンピックに関する祝日の移動
        if year == 2020 and m == 8 and d == 11:
            d = 10
        if year == 2021 and m == 8 and d == 11:
            d = 8
        days.append(datetime(year, m, d))
    # 天皇誕生日(平成)
    if year < 2019:
        days.append(datetime(year, 12, 23))
    # 天皇即位の日(2019)
    if year == 2019:
        #days.append(datetime(2019, 4, 30))
        days.append(datetime(2019, 5, 1))
        #days.append(datetime(2019, 5, 2))
        days.append(datetime(2019, 10, 22))
    # 天皇誕生日
    if year >= 2020:
        days.append(datetime(year, 2, 23))
    # 相対日付の祝日
    for m, w, d in ((1,2,0), (7,3,0), (9,3,0), (10,2,0)):
        if year == 2020 and m == 7:
            continue
        if year == 2021 and (m == 7 or m == 10):
            continue
        temp = datetime(year, m, 7*(w-1)+1)
        while temp.weekday() != d:
            temp = temp + timedelta(days=1)
        days.append(temp)
    # 2020年の海の日
    if year == 2020:
        days.append(datetime(year, 7, 23))
    # 2021年の海の日・スポーツの日
    if year == 2021:
        days.append(datetime(year, 7, 22))
        days.append(datetime(year, 7, 23))
    # 春分の日、秋分の日の追加
    d = get_shumbun(year)
    if d and not d in days:
        days.append(d)
    d = get_shubun(year)
    if d and not d in days:
        days.append(d)
    # 振替休日と国民の休日の追加
    days = sorted(days)
    additional = []
    for i in range(len(days)):
        if days[i].weekday() == 6:
            temp = days[i] + timedelta(days=1)
            while temp.weekday() == 6 or temp in days:
                temp = temp + timedelta(days=1)
            additional.append(temp)
        elif i < (len(days)-1):
            if (days[i+1] - days[i]).total_seconds() == 2*24*60*60:
                additional.append(days[i] + timedelta(days=1))
    if len(additional) > 0:
        days += additional
    # 日付順に並べて返す
    return sorted(days)

def is_leap_year(year):
    """
    うるう年判定
    """
    if (year % 4) == 0:
        return ((year % 100) != 0) or ((year % 400) == 0)
    else:
        return False


# 月の加算
def add_months(base_date, months, consider_holiday=False):
    """
    日本のカレンダーを基準に月を加算する
    """
    d = datetime(base_date.year, base_date.month, 1)

    # 年・月を計算する
    while months != 0:
        if months > 0:
            if d.month == 12:
                d = datetime(d.year + 1, 1, 1)
            else:
                d = datetime(d.year, d.month + 1, 1)
            months -= 1
        else:
            if d.month == 1:
                d = datetime(d.year - 1, 12, 1)
            else:
                d = datetime(d.year, d.month - 1, 1)
            months += 1

    # 末日の処理（対応する日がない場合は末日）
    if base_date.day == 31 and d.month in (4, 6, 9, 11):
        d = datetime(d.year, d.month, 30)
    elif base_date.day >= 29 and d.month == 2:
        if is_leap_year(d.year):
            d = datetime(d.year, d.month, 29)
        else:
            d = datetime(d.year, d.month, 28)
    else:
        d = datetime(d.year, d.month, base_date.day)

    # 休日の考慮
    if consider_holiday:
        while d.weekday() in (5, 6) or d in get_holidays(d.year):
            d = d + timedelta(days=1)

    # 計算した日付を返す
    return d

if __name__ == '__main__':
    for d in get_holidays(int(sys.argv[1])):
        print(d)
