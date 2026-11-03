#!/usr/bin/env python3
"""私聊自动回复监听。

用法：
    python3 dm_watcher.py                      # 持续运行，默认 60 秒一轮
    python3 dm_watcher.py --interval 30
    python3 dm_watcher.py --once --dry-run     # 只检测不发送
    python3 dm_watcher.py --no-reply           # 只记录不自动回
"""

import tz
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'sig_reverse'))

import ai_reply            # noqa: E402
import knowledge           # noqa: E402
import token_stats         # noqa: E402
import watcher_config      # noqa: E402
from dm_client import DMClient   # noqa: E402


def now_str():
    return tz.now_str()


class DMWatcher:
    def __init__(self, dry_run=False, no_reply=False, verbose=True):
        self.dry_run = dry_run
        self.no_reply = no_reply
        self.verbose = verbose
        self.client = DMClient()
        self.cfg = watcher_config.load()
        self._stats = {'pulled': 0, 'replied': 0, 'skipped': 0}

    def reload_config(self):
        self.cfg = watcher_config.load()

    def log(self, msg):
        if self.verbose:
            print(f'[{now_str()}] {msg}', flush=True)

    def compose(self, msg):
        """生成回复内容。"""
        cfg = self.cfg
        # 私聊没有帖子上下文，把对方的话当"评论"
        text = str(msg.get('text') or '')[:300]
        extra = ('这是私聊，不是帖子评论。像朋友聊天一样自然口语化，'
                 '不要说"有什么需要帮忙的"这种客服腔，一句话说完即可。')

        if cfg.get('ai_enabled'):
            try:
                ok, out = ai_reply.generate(
                    cfg, text, '', '', extra,
                    max_len=int(cfg.get('dm_max_len') or 50),
                )
                if ok:
                    return out, 'ai'
                self.log(f'AI 生成失败，回落模板: {out}')
            except Exception as exc:  # noqa: BLE001
                self.log(f'AI 异常: {exc.__class__.__name__}: {exc}')

        tpl = cfg.get('dm_reply_template') or '在的，稍等'
        return tpl, 'template'

    def handle(self, msg):
        """处理一条私聊。"""
        sender = msg['from']
        text = msg['text']

        if self.cfg.get('dm_skip_keywords'):
            kws = [k.strip() for k in str(self.cfg['dm_skip_keywords']).split(',') if k.strip()]
            if any(k in text for k in kws):
                self.log(f'跳过（命中忽略词）: {text[:20]!r}')
                self._stats['skipped'] += 1
                return

        # 每日上限
        cap = int(self.cfg.get('dm_daily_cap') or 0)
        if cap and self._today_count() >= cap:
            self.log(f'跳过（今日已达 {cap} 条上限）')
            self._stats['skipped'] += 1
            return

        content, src = self.compose(msg)
        tag = 'DRY' if self.dry_run else 'EXEC'
        self.log(f'[{tag}] {sender}: {text[:24]!r} → {content!r} ({src})')

        if self.dry_run:
            self._stats['replied'] += 1
            return

        if self.no_reply:
            self._stats['skipped'] += 1
            return

        ok, info = self.client.send(sender, content)
        if ok:
            self._stats['replied'] += 1
            self._bump_today()
            self.log(f'✅ 已回复 {sender}')
        else:
            self.log(f'❌ 发送失败: {info}')

    def _today_count(self):
        day = tz.today()
        return int((self.client._state.get('daily') or {}).get(day) or 0)

    def _bump_today(self):
        day = tz.today()
        daily = self.client._state.setdefault('daily', {})
        daily[day] = int(daily.get(day) or 0) + 1
        # 只留最近 7 天
        if len(daily) > 7:
            keep = dict(sorted(daily.items())[-7:])
            self.client._state['daily'] = keep
        self.client._save_state()

    def maybe_reload_session(self):
        """session 变了就重建 client。"""
        try:
            sp = Path(self.client.reader.session_path)
            mt = sp.stat().st_mtime
        except (OSError, AttributeError):
            return
        if getattr(self, '_sess_mt', None) is None:
            self._sess_mt = mt
            return
        if mt != self._sess_mt:
            self._sess_mt = mt
            try:
                self.client = DMClient()
                print(f'[{now_str()}] session 已热重载', flush=True)
            except Exception as exc:  # noqa: BLE001
                print(f'[{now_str()}] session 重载失败: {exc}', flush=True)

    def one_round(self):
        self.maybe_reload_session()
        self.reload_config()
        convs, info = self.client.pull(limit=int(self.cfg.get('dm_pull_limit') or 100))
        if not info.get('ok'):
            self.log(f'拉取失败: {info}')
            return 0

        # 从 pending 取（包含本轮新拉到的 + 之前没处理成功的）
        pend = self.client.pending()
        seen = self.client._state.get('seen') or {}
        news = [m for m in pend
                if m.get('from') and m['from'] != self.client.me
                and m.get('text') and m['msg_id'] not in seen]

        if not news:
            if info.get('fresh'):
                self.log(f'拉起 {info["fresh"]} 条，无待回消息')
            return 0

        self.log(f'待处理私聊 {len(news)} 条（本轮新拉 {info.get("fresh", 0)}）')
        self._stats['pulled'] += len(news)

        handled = []
        for m in news:
            try:
                self.handle(m)
                handled.append(m['msg_id'])
            except Exception as exc:  # noqa: BLE001
                self.log(f'处理失败: {exc.__class__.__name__}: {exc}')
            time.sleep(1.5)      # 消息间隔

        if handled:
            self.client.mark_seen(handled)
            self.client.clear_pending(handled)
        return len(news)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--interval', type=int, default=60, help='轮询间隔秒（默认 60）')
    ap.add_argument('--once', action='store_true')
    ap.add_argument('--dry-run', action='store_true', help='只检测不发送')
    ap.add_argument('--no-reply', action='store_true', help='只记录不回复')
    ap.add_argument('--reset', action='store_true', help='从头拉一次')
    args = ap.parse_args()

    w = DMWatcher(dry_run=args.dry_run, no_reply=args.no_reply)
    mode = 'DRY-RUN' if args.dry_run else ('只记录' if args.no_reply else '自动回复')
    print(f'私聊监听启动 | 账号 {w.client.me} | 模式 {mode} | 间隔 {args.interval}s', flush=True)

    if args.reset:
        w.client.pull(limit=100, reset=True)
        print('  已重置游标', flush=True)

    if args.once:
        n = w.one_round()
        print(f'本轮处理 {n} 条', flush=True)
        return

    while True:
        try:
            w.one_round()
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f'[{now_str()}] 轮次异常: {exc.__class__.__name__}: {exc}', flush=True)
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
