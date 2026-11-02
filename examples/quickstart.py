#!/usr/bin/env python3
"""最小可运行示例。

前置：
    1. 同目录或上级目录有 session_sample.json（见 docs/GETTING-STARTED.md）
    2. 把下面的 FEED_ID 换成真实帖子 ID

用法：
    python3 examples/quickstart.py
"""

import sys
import time
from pathlib import Path

# 让脚本能从项目根目录导入模块
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ============ 改这里 ============
FEED_ID = '替换成真实帖子ID'
SESSION = ROOT / 'session_sample.json'
BOOST_COUNT = 20          # 刷几条（每条约 +2 曝光）
# ==============================

from feed_reader import FeedReader      # noqa: E402
from boost_protocol import Session      # noqa: E402


def main():
    if not SESSION.exists():
        print(f'❌ 找不到 {SESSION}')
        print('   请先按 docs/GETTING-STARTED.md 抓包生成')
        return 1

    if FEED_ID.startswith('替换'):
        print('❌ 请先把 FEED_ID 换成真实帖子 ID')
        return 1

    # ---------- 1. 读帖子 ----------
    print('=' * 50)
    print('1. 读帖子')
    r = FeedReader(str(SESSION))
    print(f'   身份: {r.s.user_id} | {r.s.passport}')

    info = r.feed(FEED_ID)
    if not info.get('ok'):
        print(f'   ❌ 失败: {info}')
        return 1
    if not info.get('content'):
        print('   ⚠️ 内容为空 —— token 可能已失效（40110）')
        print('      处理：手机上退出该账号登录，重新抓包')
        return 1

    print(f"   内容: {str(info['content'])[:40]!r}")
    print(f"   作者: {info['author'].get('name')}")
    print(f"   曝光: {info['counts'].get('exposure')} | 评论: {info['counts'].get('comment')}")

    # ---------- 2. 读评论 ----------
    print('\n2. 读评论')
    comments, page = r.comments(FEED_ID, count=10)
    print(f"   totalCount: {page.get('totalCount')} | 拿到 {len(comments)} 条")
    for c in comments[:3]:
        print(f"     {c['user']['name']}: {str(c['content'])[:30]!r}")

    # ---------- 3. 刷曝光 ----------
    print(f'\n3. 刷曝光（{BOOST_COUNT} 条 ≈ +{BOOST_COUNT * 2}）')
    s = Session(str(SESSION))
    before = s.read_count(FEED_ID)
    print(f'   刷前: {before}')

    base = int(time.time() * 1000)
    codes = [s.report_once(FEED_ID, base + i) for i in range(BOOST_COUNT)]
    ok = sum(1 for c in codes if c == 200)
    print(f'   发送: {ok}/{BOOST_COUNT} 成功')

    if ok == 0:
        print('   ❌ 全部失败，检查凭证或接口')
        return 1

    print('   等待 100 秒落账…')
    time.sleep(100)
    after = s.read_count(FEED_ID)
    print(f'   刷后: {after}')
    if before is not None and after is not None:
        print(f'   增量: {after - before:+d}')

    print('\n' + '=' * 50)
    print('✅ 全部完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
