#!/usr/bin/env python3
"""统一时间显示：固定北京时间（UTC+8），不依赖服务器时区。

服务器多数是 UTC，直接 time.strftime 会差 8 小时。
这个模块提供北京时间的格式化与「今天」判断。

注意：所有「时间戳」计算（time.time()）不受影响，只有「显示」需要用它。
"""

from datetime import datetime, timedelta, timezone

# 北京时间
BJ = timezone(timedelta(hours=8))

__all__ = ['BJ', 'now', 'now_str', 'today', 'fmt', 'fmt_full', 'fmt_time', 'from_ms']


def now():
    """当前北京时间 datetime。"""
    return datetime.now(BJ)


def now_str():
    """HH:MM:SS"""
    return now().strftime('%H:%M:%S')


def today():
    """YYYY-MM-DD（北京时间的今天，用于每日限额）。"""
    return now().strftime('%Y-%m-%d')


def fmt(dt=None, pattern='%Y-%m-%d %H:%M:%S'):
    """格式化 datetime（默认当前北京时间）。"""
    return (dt or now()).strftime(pattern)


def fmt_full(pattern='%Y-%m-%d %H:%M:%S'):
    return now().strftime(pattern)


def fmt_time(pattern='%H:%M:%S'):
    return now().strftime(pattern)


def from_ms(ts_ms, pattern='%m-%d %H:%M'):
    """毫秒时间戳 → 北京时间字符串。"""
    try:
        ts = int(ts_ms) / 1000.0
    except (TypeError, ValueError):
        return '?'
    return datetime.fromtimestamp(ts, BJ).strftime(pattern)


if __name__ == '__main__':
    import time
    print(f'系统时区时间  : {time.strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'北京时间      : {now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'今天（北京）  : {today()}')
    print(f'毫秒转北京    : {from_ms(int(time.time()*1000), "%Y-%m-%d %H:%M:%S")}')
    print(f'UTC 偏移      : {now().utcoffset()}')
