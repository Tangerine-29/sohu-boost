#!/usr/bin/env python3
"""评论曝光监听器：发现评论里的 <exposure:N> 标记，自动给对应帖子推 N 次曝光。

工作方式
    1. 轮询目标（圈子最近 N 条帖子 / 指定帖子列表）
    2. 拉每条帖子的评论，用正则匹配 <exposure:300>（兼容全角、空格、大小写）
    3. 命中且未处理过 → 发 N/2 条埋点（每条约 +2 曝光），落状态防重复
    4. 结果写日志；服务端约 30~100 秒批量落账

用法
    python3 comment_watcher.py --circle <CIRCLE_ID> --recent 30 --once
    python3 comment_watcher.py --circle <CIRCLE_ID> --recent 30 --interval 180
    python3 comment_watcher.py --feed 1492779605269086336 --interval 60
    python3 comment_watcher.py --circle ... --dry-run        # 只检测不发送

状态文件
    watcher_state.json   {"<commentId>": {"feedId":..., "n":300, "sent":150, "at":...}}
"""

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'sig_reverse'))

from feed_reader import FeedReader            # noqa: E402
from boost_protocol import Session            # noqa: E402
import watcher_config                          # noqa: E402
import ai_reply                               # noqa: E402

MARK_PATTERN = None            # 由配置动态生成，见 reload_config()
try:                            # 模块加载时先初始化一次，避免 parse_mark 在 reload 前返回 None
    MARK_PATTERN = watcher_config.build_regex()
except Exception:               # noqa: BLE001
    pass
STATE_PATH = HERE / 'watcher_state.json'
DEFAULT_WINDOW_DAYS = 7          # 只处理最近 N 天内发布的帖子
MAX_EXPOSURE = 50000             # 单条评论可要求的曝光上限
SCAN_WORKERS = 8                 # 并发扫描帖子的线程数


def ts_seconds(value):
    """把毫秒/秒时间戳统一成秒。"""
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return ts / 1000.0 if ts > 1e12 else ts


def in_window(create_time, days=DEFAULT_WINDOW_DAYS, now=None):
    """帖子发布时间是否在最近 days 天内。"""
    ts = ts_seconds(create_time)
    if ts is None:
        return False
    now = now if now is not None else time.time()
    return (now - ts) <= days * 86400


def now_str():
    return datetime.now().strftime('%H:%M:%S')


class Watcher:
    def __init__(self, dry_run=False, verbose=True, window_days=DEFAULT_WINDOW_DAYS,
                 boost_session=None):
        # 读接口 + 发评论用 session_sample.json（能正常读写的号）
        self.reader = FeedReader()
        # 刷量可用单独的号（封号后仍能刷曝光，与读写号解耦）
        boost_path = Path(boost_session) if boost_session else (HERE / 'session_boost.json')
        if not boost_path.exists():
            boost_path = HERE / 'session_sample.json'
        self.boost_session_path = str(boost_path)
        self.session = Session(self.boost_session_path)
        self.state = self._load_state()
        self.dry_run = dry_run
        self.verbose = verbose
        self.window_days = window_days
        self.skipped_old = 0
        self.window_feeds = []
        self._lock = threading.Lock()          # state 读写锁
        self._reply_lock = threading.Lock()    # 发评论串行锁（nonce 复用会导致 sig check fail）
        self._last_boost_at = 0                # 上次刷量时间
        self._banned = False                   # 检测到封禁后置 True
        self.reload_config()

    META_KEY = '__meta__'

    BAN_CODES = (320002, 40110, 400001)

    def check_ban(self, res):
        """检查响应里是否出现封禁/登录失效，命中就停掉所有写操作。"""
        if not isinstance(res, dict):
            return False
        code = res.get('status')
        desc = str(res.get('desc') or '')
        if code in self.BAN_CODES or '封禁' in desc or '登录失败' in desc:
            if not self._banned:
                self._banned = True
                print(f'[{now_str()}] ⛔ 账号异常！status={code} desc={desc[:60]}', flush=True)
                print(f'[{now_str()}] ⛔ 已停止自动回复（刷量继续，halt_boost_on_ban=false）', flush=True)
            return True
        return False

    FEED_MARK_KEY = '__feed_marks__'

    def feed_replied(self, feed_id):
        """该帖子是否已经发过 AI 评论（同一帖子只发一条）。"""
        marks = self.state.get(self.FEED_MARK_KEY) or {}
        if not isinstance(marks, dict):
            return False
        return str(feed_id) in marks

    def mark_feed(self, feed_id, comment_id=None, content=None):
        """标记该帖子已发过评论。"""
        with self._lock:
            marks = self.state.get(self.FEED_MARK_KEY)
            if not isinstance(marks, dict):
                marks = {}
                self.state[self.FEED_MARK_KEY] = marks
            marks[str(feed_id)] = {
                'at': now_str(),
                'ts': time.time(),
                'commentId': str(comment_id) if comment_id else None,
                'content': (content or '')[:40],
            }
            self._save_state()

    def hourly_feed_replies(self):
        """最近 1 小时内已发的顶层评论数（用于限流）。"""
        marks = self.state.get(self.FEED_MARK_KEY) or {}
        cutoff = time.time() - 3600
        n = 0
        for rec in marks.values():
            if not isinstance(rec, dict):
                continue
            ts = rec.get('ts')
            if ts and ts >= cutoff:
                n += 1
        return n

    def should_reply_feed(self, feed_content):
        """是否该给这篇帖子发顶层评论。

        reply_all_feeds=true  → 不看内容，全部回复（受每小时上限约束）
        否则回退到关键词匹配
        """
        cfg = self.cfg
        # 只评论启动之后发布的帖子（不往回延伸）
        if cfg.get('feed_reply_only_after_start'):
            pass          # 具体时间校验在 scan_feed 里用 feed createTime 做
        if cfg.get('reply_all_feeds'):
            cap = int(cfg.get('feed_reply_hourly_cap') or 0)
            if cap and self.hourly_feed_replies() >= cap:
                return False, f'本小时已发 {cap} 条顶层评论'
            return True, 'all'
        if self.feed_mentions_me(feed_content):
            return True, 'keyword'
        return False, ''

    def feed_mentions_me(self, feed_content):
        """帖子内容是否包含触发词（如「大肥鱼」）。"""
        cfg = self.cfg
        if not cfg.get('feed_mention_reply'):
            return False
        text = str(feed_content or '')
        if not text:
            return False
        kws = [k.strip() for k in str(cfg.get('mention_keywords') or '').split(',') if k.strip()]
        return any(k in text for k in kws)

    def can_boost(self, feed_id, n):
        """刷量前的三道闸门：封禁 / 频控 / 单帖日上限。"""
        if self._banned and self.cfg.get('halt_boost_on_ban'):
            return False, '账号已被封禁（halt_boost_on_ban=true）'
        cfg = self.cfg
        # 频控
        gap = int(cfg.get('boost_min_interval') or 0)
        if gap and time.time() - self._last_boost_at < gap:
            return False, f'距上次刷量不足 {gap}s'
        # 单帖日上限
        cap = int(cfg.get('daily_cap_per_feed') or 0)
        if cap:
            used = self._daily_used(feed_id)
            if used + n > cap:
                return False, f'该帖今日已刷 {used}，再加 {n} 超过上限 {cap}'
        return True, ''

    def _daily_used(self, feed_id):
        """当天该帖已刷的曝光数（从 state 统计）。"""
        today = time.strftime('%Y-%m-%d')
        total = 0
        for k, rec in self.state.items():
            if str(k).startswith('__') or not isinstance(rec, dict):
                continue
            if str(rec.get('feedId')) != str(feed_id):
                continue
            if str(rec.get('at') or '').startswith(today):
                total += int(rec.get('n') or 0)
        return total

    def started_at(self):
        """本次部署的启动时刻（持久化在 state 里，重启不重置）。"""
        meta = self.state.get(self.META_KEY)
        if not isinstance(meta, dict) or not meta.get('started_at'):
            with self._lock:
                if self.META_KEY not in self.state:
                    self.state[self.META_KEY] = {'started_at': int(time.time()), 'at': now_str()}
                    self._save_state()
            meta = self.state[self.META_KEY]
        return int(meta['started_at'])

    def comment_in_window(self, comment_time):
        """评论时间是否在「启动时刻 ~ 启动时刻 + reply_window_days 天」内。"""
        days = int(self.cfg.get('reply_window_days') or 0)
        if days <= 0:
            return True          # 0 表示不限制
        ts = ts_seconds(comment_time)
        if ts is None:
            return False
        start = self.started_at()
        grace = int(self.cfg.get('reply_grace_minutes') or 0) * 60
        return (start - grace) <= ts <= (start + days * 86400)

    def reload_config(self):
        """每轮重新读配置，网页改关键词后自动生效。"""
        global MARK_PATTERN
        cfg = watcher_config.load()
        MARK_PATTERN = watcher_config.build_regex(cfg)
        self.cfg = cfg
        self.max_exposure = int(cfg.get('max_exposure') or 50000)
        if self.window_days <= 0:
            self.window_days = int(cfg.get('window_days') or 7)
        self.rule_text = watcher_config.describe(cfg)
        return cfg

    # ---------- 状态 ----------
    def _load_state(self):
        if STATE_PATH.exists():
            try:
                return json.loads(STATE_PATH.read_text())
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_state(self):
        """原子写：先写临时文件再 rename，避免写一半崩溃导致状态文件损坏。"""
        tmp = STATE_PATH.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1))
        tmp.replace(STATE_PATH)

    # ---------- 匹配 ----------
    @staticmethod
    def parse_mark(text):
        """从评论文本里取出 <exposure:N> 的 N。"""
        if not text:
            return None
        pattern = MARK_PATTERN
        if pattern is None:
            try:
                pattern = watcher_config.build_regex()
            except Exception:  # noqa: BLE001
                return None
        m = pattern.search(str(text))
        if not m:
            return None
        cap = int(watcher_config.load().get('max_exposure') or MAX_EXPOSURE)
        return min(int(m.group(1)), cap)

    # ---------- 执行 ----------
    def boost(self, feed_id, n):
        """分批缓慢发送 N/2 条埋点（每条约 +2 曝光）。返回 (sent, before, count)。"""
        import random
        cfg = self.cfg
        count = max(1, n // 2)
        fid = str(feed_id)
        before = self.session.read_count(fid)
        base = int(time.time() * 1000)
        workers = max(1, int(cfg.get('boost_workers') or 4))
        batch = max(1, int(cfg.get('boost_batch_size') or 20))
        delay = float(cfg.get('boost_batch_delay') or 3.0)
        jitter = float(cfg.get('api_jitter') or 0.2)

        sent = 0
        for start in range(0, count, batch):
            chunk = range(start, min(start + batch, count))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                codes = list(pool.map(lambda i: self.session.report_once(fid, base + i), chunk))
            sent += sum(1 for c in codes if c == 200)
            if start + batch < count:
                pause = delay + random.uniform(0, jitter * 3)
                print(f'[{now_str()}] 已发 {sent}/{count}，停顿 {pause:.1f}s', flush=True)
                time.sleep(pause)
        return sent, before, count

    def handle_match(self, feed_id, comment, n):
        """命中处理：锁内查重+占位+落盘，锁外发送刷量，最后 AI 回复。"""
        cid = str(comment.get('commentId'))
        user = (comment.get('user') or {}).get('name') or '匿名'
        tag = 'DRY-RUN' if self.dry_run else 'EXEC'

        with self._lock:
            if cid in self.state:
                return None
            self.state[cid] = {
                'feedId': str(feed_id), 'n': n, 'sent': 0,
                'at': now_str(), 'status': 'running',
                'content': comment.get('content'),
            }
            self._save_state()

        print(f'[{now_str()}] [{tag}] 命中 feed={feed_id} 评论={cid} 作者={user} '
              f'要求={n} 曝光 → 发 {max(1, n // 2)} 条', flush=True)

        if self.dry_run:
            with self._lock:
                self.state[cid].update({'status': 'dry', 'dry': True})
                self._save_state()
            return {'dry': True}

        ok_boost, why = self.can_boost(feed_id, n)
        if not ok_boost:
            print(f'[{now_str()}] 跳过刷量（{why}）', flush=True)
            return {'skipped': why}

        sent, before, count = self.boost(feed_id, n)
        self._last_boost_at = time.time()

        with self._lock:
            self.state[cid].update({'sent': sent, 'status': 'done'})
            self._save_state()

        print(f'[{now_str()}] 已发 {sent}/{count} 条，曝光基线 {before}', flush=True)
        if sent == 0 and count > 0:
            self.check_ban({'status': 0, 'desc': '全部发送失败'})

        self._maybe_reply(feed_id, comment, n)
        return {'sent': sent, 'count': count, 'before': before}

    # ---------- 发评论 ----------
    def reply(self, feed_id, comment_id, content):
        """发表评论或楼中楼回复。

        顶层评论： comment_type=1      tid=0
        楼中楼：   comment_type=reply  tid=毫秒时间戳  reply_comment_id=父评论ID
        （实测：comment_type 必须是字符串 "reply"、tid 必须是时间戳，否则 reply_comment_id 被忽略）
        """
        is_reply = bool(comment_id) and str(comment_id) != '0'
        now_ms = str(int(time.time() * 1000))
        params = self.reader._base_params()
        params.update({
            # 实测：顶层评论 comment_type=comment，楼中楼=reply；tid 一律用毫秒时间戳
            'comment_type': 'reply' if is_reply else 'comment',
            'tid': now_ms,
            'feed_id': str(feed_id),
            'content': content,
        })
        if is_reply:
            params['reply_comment_id'] = str(comment_id)
        status, text = self.reader._request('/330000/v8/comment/text', params, 'POST')
        try:
            j = json.loads(text)
        except json.JSONDecodeError:
            return {'ok': False, 'http': status, 'raw': text[:200]}
        ok = j.get('status') == 100000
        data = j.get('data') or {}
        return {'ok': ok, 'status': j.get('status'), 'desc': j.get('desc'),
                'commentId': data.get('commentId'), 'isReply': is_reply,
                'data': data if ok else None}

    def post_feed_comment(self, feed_id, content):
        """给帖子发一条顶层评论（不是楼中楼）。每帖受 one_reply_per_feed 限制。"""
        cfg = watcher_config.load()
        if cfg.get('one_reply_per_feed', True) and self.feed_replied(feed_id):
            return {'ok': False, 'skipped': '该帖子已发过顶层评论'}
        res = self.reply(feed_id, 0, content)      # comment_id=0 → 顶层
        if res.get('ok'):
            self.mark_feed(feed_id, res.get('commentId'), content)
        return res

    def reply_list(self, feed_id, comment_id, count=20):
        """查某条评论下的楼中楼回复。"""
        params = self.reader._base_params()
        params.update({'comment_id': str(comment_id), 'feed_id': str(feed_id),
                       'count': str(count), 'score': '0', 'stpl': '1,2,4'})
        status, text = self.reader._request('/330000/v8/comment/replylist', params, 'GET')
        try:
            j = json.loads(text)
        except json.JSONDecodeError:
            return [], {'ok': False, 'raw': text[:200]}
        d = j.get('data') or {}
        info = dict(d.get('pageInfo') or {})
        info['ok'] = j.get('status') == 100000
        return [self.reader._norm_comment(x) for x in (d.get('list') or [])], info

    def delete_comment(self, feed_id, comment_id):
        """删除自己发的评论（310005 通常也表示已删除）。"""
        params = self.reader._base_params()
        params.update({'comment_id': str(comment_id), 'feed_id': str(feed_id)})
        status, text = self.reader._request('/330000/v6/feeds/comment/remove', params, 'POST')
        try:
            j = json.loads(text)
            return {'ok': j.get('status') in (100000, 310005), 'status': j.get('status'), 'desc': j.get('desc')}
        except json.JSONDecodeError:
            return {'ok': False, 'http': status}

    def _compose_reply(self, feed_id, comment, n, feed_content=None, feed_images=None):
        """决定回复内容：AI 优先，失败回落模板。

        feed_content 已知道时直接传进来，避免重复请求 feed 详情
        （短时间连发多个请求会被服务端判 sig 异常）。
        """
        cfg = watcher_config.load()
        ctext = str(comment.get('content') or '')
        author = (comment.get('user') or {}).get('name') or ''
        if cfg.get('ai_enabled'):
            if feed_content is None:
                try:
                    info = self.reader.feed(feed_id)
                    if info.get('ok'):
                        feed_content = str(info.get('content') or '')
                        feed_images = info.get('images') or []
                except Exception:  # noqa: BLE001
                    feed_content = ''
            feed_content = feed_content or ''
            if n:
                extra = ('这是圈里的暗号，对方在求个忙，你已经帮他办好了。'
                         '回一句极简的确认就行（"好了""OK""收到"这一类），'
                         '绝对不要提曝光、流量、数字这些词，不要让旁人看出有机制。')
            else:
                extra = ''
            ok, out = ai_reply.generate(cfg, ctext, feed_content, author, extra,
                                        images=feed_images or [])
            if ok:
                return out, 'ai'
            print(f'[{now_str()}] AI 生成失败，回落模板: {out}', flush=True)
        tpl = cfg.get('reply_template') or '已处理，+{n} 曝光'
        try:
            return tpl.format(n=n, feed=feed_id), 'template'
        except (KeyError, IndexError):
            return tpl, 'template'

    def _maybe_reply(self, feed_id, comment, n):
        """按配置自动回复（AI 或模板）。"""
        cfg = watcher_config.load()
        if not cfg.get('auto_reply'):
            return None
        if self._banned and cfg.get('halt_reply_on_ban', True):
            return None          # 封禁后回复必失败，直接跳过不浪费请求
        # 注意：这里的回复都是「楼中楼」，不受「每帖一条」限制
        # 每条评论都应该能被回复；限制只作用于「发到帖子的顶层评论」
        content, src = self._compose_reply(feed_id, comment, n)
        if not content:
            return None
        # 串行发送：并发请求复用同一 s-nonce 会被服务端判 sig check fail
        with self._reply_lock:
            res = self.reply(feed_id, comment.get('commentId'), content)
            time.sleep(0.8)      # 间隔一下，避免触发频控
        if res.get('ok'):
            print(f'[{now_str()}] 已自动回复[{src}]: {content}', flush=True)
        else:
            self.check_ban(res)
            print(f'[{now_str()}] 自动回复失败: {res}', flush=True)
        return res

    def scan_feed(self, feed_id, max_comments=30, create_time=None):
        """扫一条帖子的评论，返回命中数量。create_time 为空时先查详情。"""
        hits = 0
        if create_time is None:
            info = self.reader.feed(feed_id)
            create_time = info.get('createTime') if isinstance(info, dict) else None
            if not info.get('ok'):
                if self.verbose:
                    print(f'[{now_str()}] 帖子 {feed_id} 详情拉取失败，跳过', flush=True)
                return 0
        if not in_window(create_time, self.window_days):
            self.skipped_old += 1
            if self.verbose:
                print(f'[{now_str()}] 跳过过期帖子 {feed_id}（发布 {time.strftime("%Y-%m-%d %H:%M", time.localtime(ts_seconds(create_time) or 0))}，'
                      f'超过 {self.window_days} 天）', flush=True)
            return 0
        # 帖子内容触发：提到「大肥鱼」等关键词时发一条顶层评论（每帖限一条）
        try:
            feed_info = self.reader.feed(feed_id)
            _should, _why = (False, '')
            if feed_info.get('ok'):
                # 只回「启动后发布」的帖子
                skip_by_time = False
                if self.cfg.get('feed_reply_only_after_start'):
                    pub_ts = ts_seconds(feed_info.get('createTime'))
                    if pub_ts is None or pub_ts < self.started_at():
                        skip_by_time = True
                if not skip_by_time:
                    _should, _why = self.should_reply_feed(feed_info.get('content'))
            if _should:
                if not self.feed_replied(feed_id):
                    # 注意：comment 的 content 必须留空，否则会和 feed_content 重复，
                    # 模型会以为对方在复读（曾导致回复「你搁这当复读机呢」）。
                    content, src = self._compose_reply(
                        feed_id,
                        {'commentId': '0', 'content': '',
                         'user': {'name': (feed_info.get('author') or {}).get('name') or '楼主'}},
                        0,
                        feed_content=str(feed_info.get('content') or ''),
                        feed_images=feed_info.get('images') or [])
                    time.sleep(3.0)      # 与上一步的 feed 请求拉开间隔（太密会 sig check fail）
                    res = self.post_feed_comment(feed_id, content)
                    if res.get('ok'):
                        print(f'[{now_str()}] 帖子提到关键词，已发顶层评论[{src}]: {content}', flush=True)
                        hits += 1
                    else:
                        print(f'[{now_str()}] 发顶层评论失败: status={res.get("status")} desc={res.get("desc")} skipped={res.get("skipped")}', flush=True)
                else:
                    if self.verbose:
                        print(f'[{now_str()}] 帖子 {feed_id} 已有顶层评论，跳过', flush=True)
        except Exception as exc:  # noqa: BLE001
            if self.verbose:
                print(f'[{now_str()}] 帖子内容检查失败: {exc}', flush=True)

        comments, _ = self.reader.comments(feed_id, count=max_comments, max_pages=1)
        skipped_old = 0
        for c in comments:
            # 评论时间窗口：只处理启动时刻起 reply_window_days 天内产生的评论
            if not self.comment_in_window(c.get('createTime')):
                skipped_old += 1
                continue
            n = self.parse_mark(c.get('content'))
            if not n:
                for rep in (c.get('replies') or []):
                    n = self.parse_mark(rep.get('content'))
                    if n:
                        c = rep
                        break
            if n and str(c.get('commentId')) not in self.state:
                self.handle_match(feed_id, c, n)
                hits += 1
            elif not n and self.cfg.get('ai_enabled') and self.cfg.get('ai_reply_mode') == 'all':
                # 普通评论也回：只走 AI，不刷量
                cid = str(c.get('commentId'))
                if cid in self.state:
                    continue
                if self.cfg.get('ai_skip_own') and (c.get('user') or {}).get('userId') == self.reader.s.user_id:
                    continue
                with self._lock:
                    if cid in self.state:
                        continue
                    self.state[cid] = {'feedId': str(feed_id), 'n': 0, 'sent': 0,
                                       'at': now_str(), 'status': 'ai_only',
                                       'content': c.get('content')}
                    self._save_state()
                self._maybe_reply(feed_id, c, 0)
                hits += 1
        # 逐帖的窗口外跳过不单独打印，避免刷屏；由 scan_circle 汇总
        return hits

    def scan_circle(self, circle_id, recent=None):
        """扫描圈子里「最近 window_days 天」发布的全部帖子。"""
        self.reload_config()
        feeds, info = self.reader.circle_feeds_since(
            circle_id, days=self.window_days, count=20, max_pages=200, list_type='2')
        if not info.get('ok'):
            print(f'[{now_str()}] 圈子拉取失败: {info}', flush=True)
            return 0
        self.window_feeds = feeds          # 供网页/调用方查看
        todo, skipped = [], 0
        for f in feeds:
            fid = f.get('feedId')
            if not fid:
                continue
            if not in_window(f.get('createTime'), self.window_days):
                skipped += 1
                continue
            if (f.get('counts') or {}).get('comment') == 0:
                # 有「帖子评论」功能时不能跳过 0 评论的帖子，否则永远发不出顶层评论
                if not (self.cfg.get('reply_all_feeds') or self.cfg.get('feed_mention_reply')):
                    continue
            todo.append(f)
        total = 0
        scanned = len(todo)
        if todo:
            with ThreadPoolExecutor(max_workers=SCAN_WORKERS) as pool:
                results = list(pool.map(
                    lambda f: self.scan_feed(f.get('feedId'), create_time=f.get('createTime')), todo))
            total = sum(results)
        self.skipped_old += skipped
        if self.verbose:
            print(f'[{now_str()}] 圈子 {circle_id}: 窗口内 {len(feeds)} 条（{info["pages"]} 页），'
                  f'检查 {scanned} 条有评论的帖子，命中 {total}', flush=True)
        return total

    def scan_feeds(self, feed_ids):
        total = 0
        for fid in feed_ids:
            total += self.scan_feed(fid)
        return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--circle', help='圈子 ID，扫描其中最近的帖子')
    ap.add_argument('--feed', help='逗号分隔的帖子 ID（可与 --circle 同时用）')
    ap.add_argument('--recent', type=int, default=0, help='已废弃：现在默认扫描窗口内全部帖子')
    ap.add_argument('--interval', type=int, default=180,
                    help='轮询间隔秒（默认 180 = 3 分钟，0 表示只跑一次）')
    ap.add_argument('--once', action='store_true', help='只跑一次')
    ap.add_argument('--dry-run', action='store_true', help='只检测不发送')
    ap.add_argument('--boost-session', default=None,
                    help='刷量专用 session 文件（默认 session_boost.json，缺失则回退 session_sample.json）')
    ap.add_argument('--days', type=int, default=DEFAULT_WINDOW_DAYS,
                    help=f'只处理最近 N 天内发布的帖子（默认 {DEFAULT_WINDOW_DAYS}）')
    ap.add_argument('--reset', action='store_true', help='清空已处理记录')
    args = ap.parse_args()

    if not args.circle and not args.feed:
        print('需要 --circle 或 --feed 至少一个')
        return
    if args.reset and STATE_PATH.exists():
        STATE_PATH.unlink()
        print('已清空 watcher_state.json')

    w = Watcher(dry_run=args.dry_run, window_days=args.days,
                boost_session=args.boost_session)
    print(f'监听启动 {now_str()} | 回复号 {w.reader.s.user_id} | 刷量号 {w.session.user_id} | 已处理记录 {len(w.state)} 条 | '
          f'规则 {w.rule_text} | 窗口 {args.days} 天 | 上限 {w.max_exposure}'
          + ('（DRY-RUN）' if args.dry_run else ''), flush=True)

    def one_round():
        total = 0
        if args.feed:
            ids = [x.strip() for x in args.feed.split(',') if x.strip()]
            total += w.scan_feeds(ids)
        if args.circle:
            total += w.scan_circle(args.circle)
        return total

    if args.once or args.interval <= 0:
        n = one_round()
        print(f'本轮命中 {n} 条', flush=True)
        return

    while True:
        try:
            one_round()
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f'[{now_str()}] 本轮异常: {exc.__class__.__name__}: {exc}', flush=True)
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
