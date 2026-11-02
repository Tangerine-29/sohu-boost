#!/usr/bin/env python3
"""定时把 Token 消耗写进个人简介。

用法：
    python3 profile_updater.py              # 持续运行，每 10 分钟更新一次
    python3 profile_updater.py --once       # 只更新一次
    python3 profile_updater.py --interval 300
"""

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'sig_reverse'))

import token_stats                       # noqa: E402
from feed_reader import FeedReader       # noqa: E402


def now_str():
    return time.strftime('%H:%M:%S')


def update_profile(reader=None):
    """把当前 token 统计写进简介。返回 (ok, text, resp)。"""
    r = reader or FeedReader()
    desc = token_stats.format_desc()
    p = r._base_params()
    p.pop('extras', None)               # users/update 不需要这个
    p.update({
        'user_id': r.s.user_id,
        'description': desc,
        'banned_word': '1',
    })
    status, text = r._request('/330000/v5/users/update', p, 'POST')
    ok = '"status":100000' in text or '"status": 100000' in text
    return ok, desc, text[:120]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--interval', type=int, default=10800, help='更新间隔秒（默认 10800 = 3 小时）')
    ap.add_argument('--once', action='store_true')
    args = ap.parse_args()

    reader = FeedReader()
    print(f'简介更新器启动 | 账号 {reader.s.user_id} | 间隔 {args.interval}s', flush=True)

    if args.once:
        ok, desc, resp = update_profile(reader)
        print(f'[{now_str()}] {"OK " if ok else "ERR"} {desc}')
        return

    while True:
        try:
            ok, desc, resp = update_profile(reader)
            s = token_stats.get_stats()
            print(f'[{now_str()}] {"OK " if ok else "ERR"} {desc}  '
                  f'(累计 {s.get("total_tokens")} tokens / {s.get("calls")} 次调用)', flush=True)
            if not ok:
                print(f'           响应: {resp}', flush=True)
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f'[{now_str()}] 更新失败: {exc.__class__.__name__}: {exc}', flush=True)
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
