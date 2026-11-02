#!/usr/bin/env python3
"""Token 消耗统计与简介更新。

统计口径：1 碗大米饭 = 1,000,000 Tokens
累计 < 100 万 → 显示 0.x 碗
"""

import json
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATS_PATH = HERE / 'token_stats.json'
LOCK = threading.Lock()

TOKENS_PER_BOWL = 1_000_000


def _load():
    if STATS_PATH.exists():
        try:
            return json.loads(STATS_PATH.read_text())
        except json.JSONDecodeError:
            pass
    return {'total_tokens': 0, 'by_model': {}, 'calls': 0,
            'first_at': None, 'updated_at': None}


def _save(d):
    tmp = STATS_PATH.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    tmp.replace(STATS_PATH)


def record_usage(usage, model=None):
    """记录一次 AI 调用的 token 消耗。usage 来自接口响应。"""
    if not isinstance(usage, dict):
        return
    total = usage.get('total_tokens') or 0
    if not total:
        # 兼容某些网关只给 prompt/completion
        total = (usage.get('prompt_tokens') or 0) + (usage.get('completion_tokens') or 0)
    if not total:
        return
    with LOCK:
        d = _load()
        d['total_tokens'] = int(d.get('total_tokens') or 0) + int(total)
        d['calls'] = int(d.get('calls') or 0) + 1
        if model:
            bm = d.setdefault('by_model', {})
            bm[model] = int(bm.get(model) or 0) + int(total)
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        if not d.get('first_at'):
            d['first_at'] = now
        d['updated_at'] = now
        _save(d)


def get_stats():
    with LOCK:
        return _load()


def bowls(total=None):
    """换算成碗数（保留 2 位小数）。"""
    if total is None:
        total = get_stats().get('total_tokens') or 0
    return round(total / TOKENS_PER_BOWL, 2)


def format_desc(total=None):
    """生成简介文案：已吃了1.23碗大米饭 = 1234567Tokens"""
    if total is None:
        total = get_stats().get('total_tokens') or 0
    # 向下取整到 2 位，避免 999999 显示成 1.00 碗
    b = int(total / TOKENS_PER_BOWL * 100) / 100.0
    b_str = f'{b:.2f}' if b < 10 else f'{b:.1f}'
    return f'已吃了{b_str}碗大米饭 = {int(total)}Tokens'


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--add':
        record_usage({'total_tokens': int(sys.argv[2])})
        print('已累加', sys.argv[2])
    print('当前统计:')
    s = get_stats()
    print(f"  累计 Tokens : {s.get('total_tokens')}")
    print(f"  调用次数    : {s.get('calls')}")
    print(f"  折合碗数    : {bowls()}")
    print(f"  简介文案    : {format_desc()}")
    if s.get('by_model'):
        print('  按模型:')
        for m, v in s['by_model'].items():
            print(f"    {m:<28} {v}")
