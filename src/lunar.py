"""
Chinese lunar calendar module.

Ported from KindleNoodle's LUNAR_INFO-based algorithm (1900-2100).
Provides solar-to-lunar date conversion with Chinese formatting.

Reference: https://github.com/ZH-Labs/KindleNoodle
"""

from __future__ import annotations

from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LUNAR_MONTHS = [
    "正月", "二月", "三月", "四月", "五月", "六月",
    "七月", "八月", "九月", "十月", "冬月", "腊月",
]

LUNAR_DAYS = [
    "初一", "初二", "初三", "初四", "初五", "初六", "初七", "初八", "初九", "初十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "廿一", "廿二", "廿三", "廿四", "廿五", "廿六", "廿七", "廿八", "廿九", "三十",
]

GAN = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
ZHI = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

CN_DIGITS = ["〇", "一", "二", "三", "四", "五", "六", "七", "八", "九"]

# Each entry encodes one lunar year (1900-2100).
# Bits 4-15: which regular months are 30 days (big month).
# Bit 16 (0x10000): whether the leap month is big (30 days).
# Bits 0-3: which month is the leap month (0 = none).
LUNAR_INFO = [
    0x04bd8, 0x04ae0, 0x0a570, 0x054d5, 0x0d260, 0x0d950, 0x16554, 0x056a0, 0x09ad0, 0x055d2,
    0x04ae0, 0x0a5b6, 0x0a4d0, 0x0d250, 0x1d255, 0x0b540, 0x0d6a0, 0x0ada2, 0x095b0, 0x14977,
    0x04970, 0x0a4b0, 0x0b4b5, 0x06a50, 0x06d40, 0x1ab54, 0x02b60, 0x09570, 0x052f2, 0x04970,
    0x06566, 0x0d4a0, 0x0ea50, 0x06e95, 0x05ad0, 0x02b60, 0x186e3, 0x092e0, 0x1c8d7, 0x0c950,
    0x0d4a0, 0x1d8a6, 0x0b550, 0x056a0, 0x1a5b4, 0x025d0, 0x092d0, 0x0d2b2, 0x0a950, 0x0b557,
    0x06ca0, 0x0b550, 0x15355, 0x04da0, 0x0a5d0, 0x14573, 0x052d0, 0x0a9a8, 0x0e950, 0x06aa0,
    0x0aea6, 0x0ab50, 0x04b60, 0x0aae4, 0x0a570, 0x05260, 0x0f263, 0x0d950, 0x05b57, 0x056a0,
    0x096d0, 0x04dd5, 0x04ad0, 0x0a4d0, 0x0d4d4, 0x0d250, 0x0d558, 0x0b540, 0x0b6a0, 0x195a6,
    0x095b0, 0x049b0, 0x0a974, 0x0a4b0, 0x0b27a, 0x06a50, 0x06d40, 0x0af46, 0x0ab60, 0x09570,
    0x04af5, 0x04970, 0x064b0, 0x074a3, 0x0ea50, 0x06b58, 0x055c0, 0x0ab60, 0x096d5, 0x092e0,
    0x0c960, 0x0d954, 0x0d4a0, 0x0da50, 0x07552, 0x056a0, 0x0abb7, 0x025d0, 0x092d0, 0x0cab5,
    0x0a950, 0x0b4a0, 0x0baa4, 0x0ad50, 0x055d9, 0x04ba0, 0x0a5b0, 0x15176, 0x052b0, 0x0a930,
    0x07954, 0x06aa0, 0x0ad50, 0x05b52, 0x04b60, 0x0a6e6, 0x0a4e0, 0x0d260, 0x0ea65, 0x0d530,
    0x05aa0, 0x076a3, 0x096d0, 0x04bd7, 0x04ad0, 0x0a4d0, 0x1d0b6, 0x0d250, 0x0d520, 0x0dd45,
    0x0b5a0, 0x056d0, 0x055b2, 0x049b0, 0x0a577, 0x0a4b0, 0x0aa50, 0x1b255, 0x06d20, 0x0ada0,
    0x14b63, 0x09370, 0x049f8, 0x04970, 0x064b0, 0x168a6, 0x0ea50, 0x06b20, 0x1a6c4, 0x0aae0,
    0x0a2e0, 0x0d2e3, 0x0c960, 0x0d557, 0x0d4a0, 0x0da50, 0x05d55, 0x056a0, 0x0a6d0, 0x055d4,
    0x052d0, 0x0a9b8, 0x0a950, 0x0b4a0, 0x0b6a6, 0x0ad50, 0x055a0, 0x0aba4, 0x0a5b0, 0x052b0,
    0x0b273, 0x06930, 0x07337, 0x06aa0, 0x0ad50, 0x14b55, 0x04b60, 0x0a570, 0x054e4, 0x0d160,
    0x0e968, 0x0d520, 0x0daa0, 0x16aa6, 0x056d0, 0x04ae0, 0x0a9d4, 0x0a2d0, 0x0d150, 0x0f252,
    0x0d520,
]


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------

def _leap_month(year: int) -> int:
    """Return the leap month number for lunar *year* (0 if none)."""
    return LUNAR_INFO[year - 1900] & 0xF


def _leap_days(year: int) -> int:
    """Return the number of days in the leap month of lunar *year* (0 if none)."""
    if not _leap_month(year):
        return 0
    return 30 if LUNAR_INFO[year - 1900] & 0x10000 else 29


def _month_days(year: int, month: int) -> int:
    """Return the number of days in *month* of lunar *year*."""
    return 30 if LUNAR_INFO[year - 1900] & (0x10000 >> month) else 29


def _year_days(year: int) -> int:
    """Return the total number of days in lunar *year*."""
    total = 348
    i = 0x8000
    while i > 0x8:
        total += 1 if LUNAR_INFO[year - 1900] & i else 0
        i >>= 1
    return total + _leap_days(year)


# ---------------------------------------------------------------------------
# Solar-to-Lunar conversion
# ---------------------------------------------------------------------------

# The epoch: 1900-01-31 (solar) = lunar year 1900, month 1, day 1.
_EPOCH = date(1900, 1, 31)


def solar_to_lunar(solar_date: date) -> dict:
    """Convert a solar date to lunar date details.

    Returns:
        dict with keys:
            year (int): lunar year
            month (int): lunar month (1-12)
            day (int): lunar day (1-30)
            is_leap (bool): whether the month is a leap month
            year_gan (str): heavenly stem, e.g. "丙"
            year_zhi (str): earthly branch, e.g. "午"
            month_cn (str): Chinese month name, e.g. "五月"
            day_cn (str): Chinese day name, e.g. "初三"
            month_label (str): Full month label, e.g. "闰四月" or "五月"
            date_cn (str): Full date string, e.g. "丙午年 五月初三"
    """
    offset = (solar_date - _EPOCH).days

    # Walk forward year by year to find the lunar year
    lunar_year = 1900
    temp = 0
    while lunar_year < 2101 and offset > 0:
        temp = _year_days(lunar_year)
        offset -= temp
        lunar_year += 1

    if offset < 0:
        offset += temp
        lunar_year -= 1

    # Walk forward month by month to find the lunar month and day
    # Faithful port of the KindleNoodle JS algorithm
    leap = _leap_month(lunar_year)
    is_leap = False
    lunar_month = 1

    for lm in range(1, 14):
        if offset <= 0:
            break
        if leap > 0 and lm == (leap + 1) and not is_leap:
            lm -= 1
            is_leap = True
            temp = _leap_days(lunar_year)
        else:
            temp = _month_days(lunar_year, lm)
        if is_leap and lm == (leap + 1):
            is_leap = False
        offset -= temp

    if offset == 0 and leap > 0 and lm == (leap + 1):
        if is_leap:
            is_leap = False
        else:
            is_leap = True
            lm -= 1

    if offset < 0:
        offset += temp
        lm -= 1

    lunar_month = lm

    lunar_day = offset + 1  # 1-based

    # Compute heavenly stem and earthly branch for the year
    gan_idx = (lunar_year - 4) % 10
    zhi_idx = (lunar_year - 4) % 12
    year_gan = GAN[gan_idx]
    year_zhi = ZHI[zhi_idx]

    # Chinese formatting
    month_cn = LUNAR_MONTHS[lunar_month - 1]
    day_cn = LUNAR_DAYS[lunar_day - 1]
    month_label = ("闰" + month_cn) if is_leap else month_cn
    date_cn = f"{year_gan}{year_zhi}年 {month_label}{day_cn}"

    return {
        "year": lunar_year,
        "month": lunar_month,
        "day": lunar_day,
        "is_leap": is_leap,
        "year_gan": year_gan,
        "year_zhi": year_zhi,
        "month_cn": month_cn,
        "day_cn": day_cn,
        "month_label": month_label,
        "date_cn": date_cn,
    }


def year_cn(year: int) -> str:
    """Format a solar year in Chinese, e.g. 2026 → '二〇二六'."""
    return "".join(CN_DIGITS[int(d)] for d in str(year))


def weekday_cn(solar_date: date) -> str:
    """Return Chinese weekday name, e.g. '星期六'."""
    names = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"]
    return names[solar_date.weekday() if solar_date.weekday() != 6 else 0] if solar_date.weekday() == 6 else names[solar_date.weekday()]


def format_solar_date(solar_date: date) -> str:
    """Format solar date in Chinese, e.g. '2026年6月27日 星期六'."""
    weekdays = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"]
    weekday = weekdays[solar_date.weekday()]
    return f"{solar_date.year}年{solar_date.month}月{solar_date.day}日 {weekday}"


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    today = date.today()
    lunar = solar_to_lunar(today)
    print(f"公历: {format_solar_date(today)}")
    print(f"农历: {lunar['date_cn']}")
