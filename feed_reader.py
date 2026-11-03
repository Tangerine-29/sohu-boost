#!/usr/bin/env python3
"""狐友帖子读取器：不打开 App，纯协议取帖子内容 + 评论列表。

依赖：sign.py（签名）、session_sample.json（身份样本）
接口：
    POST /330000/v7/feeds/show              帖子详情
    GET  /330000/v8/comment/list            评论列表（分页）
    GET  /330000/feed/repost/comment/list/v20  转发列表

用法：
    python3 feed_reader.py --feed 1492661190353174144
    python3 feed_reader.py --feed <id> --comments 50 --json
"""

import argparse
import http.client
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'sig_reverse'))
from sign import sign                      # noqa: E402
from boost_protocol import Session         # noqa: E402

HOST = 'cs-ol.sns.sohu.com'

# 全局最小请求间隔（秒）：同进程内两个请求至少间隔这么久，避免 sig check fail
_MIN_GAP = 0.0
_LAST_REQ_AT = 0.0


def set_min_gap(seconds):
    global _MIN_GAP
    _MIN_GAP = max(0.0, float(seconds))


def ts_seconds(value):
    """毫秒/秒时间戳统一成秒。"""
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return ts / 1000.0 if ts > 1e12 else ts


class FeedReader:
    def __init__(self, session_path=None):
        self.s = Session(str(session_path or (HERE / 'session_sample.json')))

    # ---------- 底层 ----------
    def _base_params(self):
        p = dict(self.s.show_body)
        p.pop('feed_id', None)
        p['flyer'] = str(int(time.time() * 1000))
        return p

    def _request(self, path, params, method='GET'):
        # 全局限速：避免同一进程内请求过密被判 sig check fail
        global _LAST_REQ_AT
        if _MIN_GAP > 0:
            wait = _MIN_GAP - (time.time() - _LAST_REQ_AT)
            if wait > 0:
                time.sleep(wait)
        _LAST_REQ_AT = time.time()
        # 并发安全：先复制 headers，再在副本上生成 nonce 并签名。
        # 直接改 self.s.headers 会让多线程互相覆盖 nonce，导致 sig check fail。
        headers = dict(self.s.headers)
        try:
            from boost_protocol import gen_nonce
            headers['s-nonce'] = gen_nonce()
        except Exception:  # noqa: BLE001
            pass
        p = dict(params)
        p['sig'] = sign(p, headers)
        try:
            if method == 'POST':
                body = '&'.join(f'{k}={v}' for k, v in p.items()).encode()
                conn = http.client.HTTPSConnection(HOST, timeout=15)
                conn.request('POST', path, body=body, headers=headers)
            else:
                conn = http.client.HTTPSConnection(HOST, timeout=15)
                conn.request('GET', path + '?' + urllib.parse.urlencode(p), headers=headers)
            resp = conn.getresponse()
            text = resp.read().decode('utf-8', 'replace')
            conn.close()
            return resp.status, text
        except Exception as exc:  # noqa: BLE001
            return None, f'ERR {exc.__class__.__name__}: {exc}'

    # ---------- 业务 ----------
    def feed(self, feed_id):
        """帖子详情：内容、作者、各类计数。"""
        params = self._base_params()
        params.update({'feed_id': str(feed_id), 'extras': '1'})
        status, text = self._request('/330000/v7/feeds/show', params, 'POST')
        if status != 200:
            return {'ok': False, 'http': status, 'raw': text[:300]}
        try:
            j = json.loads(text)
        except json.JSONDecodeError:
            return {'ok': False, 'http': status, 'raw': text[:300]}
        data = j.get('data') or {}
        sf = data.get('sourceFeed') or {}
        circle = sf.get('circle') or {}
        user = data.get('userInfo') or sf.get('userInfo') or {}
        # 作者信息可能散在多处，做一次宽松合并
        for key in ('userInfo', 'authorInfo', 'user'):
            if isinstance(data.get(key), dict):
                user = {**user, **data[key]}
            if isinstance(sf.get(key), dict):
                user = {**user, **sf[key]}
        return {
            'ok': True,
            'status': j.get('status'),
            'feedId': sf.get('feedId') or str(feed_id),
            'content': sf.get('content'),
            'createTime': sf.get('score'),
            'counts': {
                'exposure': sf.get('exposureCount'),
                'repost': sf.get('repostCount'),
                'comment': sf.get('commentCount'),
                'like': sf.get('likeCount') or sf.get('supportCount') or sf.get('praiseCount'),
            },
            'author': {
                'userId': user.get('userId') or user.get('uid') or sf.get('userId'),
                'name': user.get('nickName') or user.get('name') or sf.get('userName'),
                'avatar': user.get('avatar') or sf.get('avatar'),
            },
            'circleId': circle.get('circleId'),
            'circleName': circle.get('circleName'),
            'images': self._extract_images(sf),
            'pics': self.extract_pics(sf),
            'raw_keys': list(sf.keys())[:30],
        }

    @staticmethod
    def _extract_images(sf):
        """提取帖子图片 URL（原图优先）。

        实测帖子图片在 picFeed.pics[]，每项三个尺寸：
            tp=小图  bp=大图  rp=原图
        """
        out = []
        # 1) 主路径：picFeed.pics[]
        pf = sf.get('picFeed') if isinstance(sf, dict) else None
        if isinstance(pf, dict):
            for item in (pf.get('pics') or []):
                if not isinstance(item, dict):
                    continue
                url = item.get('rp') or item.get('bp') or item.get('tp')
                if url:
                    out.append(url)
        # 2) 兼容其它字段
        for key in ('images', 'picList', 'mediaList', 'imageList'):
            val = sf.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        url = (item.get('rp') or item.get('url')
                               or item.get('picUrl') or item.get('originUrl'))
                        if url:
                            out.append(url)
                    elif isinstance(item, str):
                        out.append(item)
        # 去重保序
        seen, uniq = set(), []
        for u in out:
            if u not in seen:
                seen.add(u)
                uniq.append(u)
        return uniq[:9]

    @staticmethod
    def extract_pics(sf):
        """返回图片的完整尺寸信息（含小/大/原图与宽高）。"""
        pf = sf.get('picFeed') if isinstance(sf, dict) else None
        if not isinstance(pf, dict):
            return []
        out = []
        for x in (pf.get('pics') or []):
            if not isinstance(x, dict):
                continue
            out.append({
                'small': x.get('tp'),
                'big': x.get('bp'),
                'raw': x.get('rp'),
                'w': x.get('bw') or x.get('tw'),
                'h': x.get('bh') or x.get('th'),
            })
        return out


    # ---------- 圈子 ----------
    def circle_feeds(self, circle_id, count=20, max_pages=1, list_type='1'):
        """圈子帖子列表，自动翻页。

        count  每页条数（服务端上限约 20-30）
        max_pages  最多翻几页（7599 条全量需要约 380 页）
        返回 (feeds, page_info)
        """
        collected, page_info = [], {}
        score = '0'
        for _ in range(max_pages):
            params = self._base_params()
            params.update({
                'circle_id': str(circle_id), 'count': str(count),
                'score': str(score), 'list_type': str(list_type),
                'tpl': '1', 'stpl': '1,2,4,8',
            })
            status, text = self._request('/330000/v8/circle/feed/list', params, 'GET')
            if status != 200:
                return collected, {'ok': False, 'http': status, 'raw': text[:200]}
            try:
                j = json.loads(text)
            except json.JSONDecodeError:
                return collected, {'ok': False, 'raw': text[:200]}
            if j.get('status') != 100000:
                return collected, {'ok': False, 'status': j.get('status'), 'desc': j.get('desc')}
            data = j.get('data') or {}
            page_info = data.get('pageInfo') or {}
            items = data.get('feedList') or []
            for it in items:
                collected.append(self._norm_feed(it))
            if not items or not page_info.get('hasMore'):
                break
            score = page_info.get('score', score)
            # 翻页限速：每页之间停一下，避免短时间连续请求
            try:
                import watcher_config as _wc
                _c = _wc.load()
                _d = float(_c.get('list_page_delay') or 0)
                if _d:
                    import random as _r
                    time.sleep(_d + _r.uniform(0, float(_c.get('api_jitter') or 0) * 3))
            except Exception:  # noqa: BLE001
                time.sleep(1.0)
        page_info['ok'] = True
        page_info['fetched'] = len(collected)
        return collected, page_info


    def circle_feeds_since(self, circle_id, days=7, count=20, max_pages=200, list_type='2'):
        """拉取最近 days 天内的全部圈子帖子（列表按时间倒序，遇到超期的就停）。

        返回 (feeds, info)  info 含 totalCount / fetched / pages / stopped_by
        """
        import time as _t
        cutoff = _t.time() - days * 86400
        collected, score, pages = [], '0', 0
        info = {'ok': True, 'days': days, 'totalCount': None, 'stopped_by': 'end'}
        for _ in range(max_pages):
            params = self._base_params()
            params.update({
                'circle_id': str(circle_id), 'count': str(count),
                'score': str(score), 'list_type': str(list_type),
                'tpl': '1', 'stpl': '1,2,4,8',
            })
            status, text = self._request('/330000/v8/circle/feed/list', params, 'GET')
            if status != 200:
                info.update({'ok': False, 'http': status, 'raw': text[:200]})
                break
            try:
                j = json.loads(text)
            except json.JSONDecodeError:
                info.update({'ok': False, 'raw': text[:200]})
                break
            if j.get('status') != 100000:
                info.update({'ok': False, 'status': j.get('status'), 'desc': j.get('desc')})
                break
            data = j.get('data') or {}
            page_info = data.get('pageInfo') or {}
            if info['totalCount'] is None:
                info['totalCount'] = page_info.get('totalCount')
            items = data.get('feedList') or []
            pages += 1
            reached_old = False
            for it in items:
                f = self._norm_feed(it)
                ts = ts_seconds(f.get('createTime'))
                if ts is not None and ts < cutoff:
                    reached_old = True
                    break
                collected.append(f)
            if reached_old:
                info['stopped_by'] = 'window'
                break
            if not items or not page_info.get('hasMore'):
                info['stopped_by'] = 'end'
                break
            score = page_info.get('score', score)
            # 翻页限速：每页之间停一下，避免短时间连续请求
            try:
                import random as _r
                import watcher_config as _wc
                _c = _wc.load()
                _d = float(_c.get('list_page_delay') or 0)
                _j = float(_c.get('api_jitter') or 0)
                if _d > 0:
                    time.sleep(_d + _r.uniform(0, _j * 3))
            except Exception:  # noqa: BLE001
                time.sleep(1.0)
        info['fetched'] = len(collected)
        info['pages'] = pages
        return collected, info

    @staticmethod
    def _norm_feed(it):
        """列表项结构：{tpl, sourceFeed:{...}, fastComment:{...}}"""
        if not isinstance(it, dict):
            return {'raw': it}
        sf = it.get('sourceFeed') or {}
        pics = []
        pf = sf.get('picFeed') or {}
        for pic in (pf.get('pics') or [])[:9]:
            if isinstance(pic, dict):
                url = pic.get('tp') or pic.get('bp') or pic.get('rp')
                if url:
                    pics.append(url)
        circle = sf.get('circle') or {}
        circle_user = sf.get('circleUser') or {}
        return {
            'feedId': sf.get('feedId'),
            'content': sf.get('content'),
            'createTime': sf.get('score'),
            'counts': {
                'exposure': sf.get('exposureCount'),
                'comment': sf.get('commentCount'),
                'repost': sf.get('repostCount'),
            },
            'author': {
                'userId': sf.get('userId'),
                'name': sf.get('userName'),
                'avatar': sf.get('avatar'),
                'level': circle_user.get('level'),
            },
            'circle': {'circleId': circle.get('circleId'), 'name': circle.get('circleName')},
            'tag': sf.get('tagDesc') or sf.get('tag'),
            'images': pics,
            'fastComment': (it.get('fastComment') or {}).get('totalCount'),
        }

    def comments(self, feed_id, count=20, max_pages=3):
        """评论列表，自动翻页。返回 (comments, page_info)。"""
        collected, page_info = [], {}
        score, jump = 0, '0'
        for _ in range(max_pages):
            params = self._base_params()
            params.update({
                'feed_id': str(feed_id), 'count': str(count),
                'score': str(score), 'jump_comment_id': str(jump), 'stpl': '1,4,8',
            })
            status, text = self._request('/330000/v8/comment/list', params, 'GET')
            if status != 200:
                return collected, {'ok': False, 'http': status, 'raw': text[:200]}
            try:
                j = json.loads(text)
            except json.JSONDecodeError:
                return collected, {'ok': False, 'raw': text[:200]}
            data = j.get('data') or {}
            page_info = data.get('pageInfo') or {}
            items = data.get('list') or []
            for it in items:
                collected.append(self._norm_comment(it))
            if not items or not page_info.get('hasMore'):
                break
            # 下一页：用最后一条的 score / commentId
            last = items[-1] if items else {}
            score = last.get('score') or page_info.get('score') or 0
            jump = last.get('commentId') or last.get('id') or '0'
        page_info['ok'] = True
        return collected, page_info

    @staticmethod
    def _norm_comment(it):
        """评论字段是扁平的：userName/userId/avatar/timeId/sourceRegion 直接在顶层。"""
        if not isinstance(it, dict):
            return {'raw': it}
        nested = it.get('userInfo') or it.get('user') or {}
        if not isinstance(nested, dict):
            nested = {}
        replies = it.get('replyList') or it.get('replies') or []
        return {
            'commentId': it.get('commentId') or it.get('id'),
            'content': it.get('content'),
            'user': {
                'userId': it.get('userId') or nested.get('userId'),
                'name': it.get('userName') or nested.get('nickName') or nested.get('name'),
                'avatar': it.get('avatar') or nested.get('avatar'),
            },
            'likeCount': it.get('likeCount'),
            'replyCount': it.get('replyCount'),
            'createTime': it.get('timeId') or it.get('createTime') or it.get('score'),
            'region': it.get('sourceRegion'),
            'anonymous': it.get('anonymous'),
            'replies': [FeedReader._norm_comment(r) for r in replies[:10]] if isinstance(replies, list) else [],
        }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--feed', required=True)
    ap.add_argument('--comments', type=int, default=20)
    ap.add_argument('--pages', type=int, default=1)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    r = FeedReader()
    feed = r.feed(args.feed)
    comments, page_info = r.comments(args.feed, args.comments, args.pages)

    if args.json:
        print(json.dumps({'feed': feed, 'comments': comments, 'pageInfo': page_info},
                         ensure_ascii=False, indent=2))
        return

    if not feed.get('ok'):
        print('详情获取失败:', feed)
        return
    c = feed['counts']
    print(f"帖子 {feed['feedId']}")
    print(f"  作者: {feed['author'].get('name')} ({feed['author'].get('userId')})")
    print(f"  内容: {feed['content']}")
    print(f"  曝光 {c['exposure']} | 转发 {c['repost']} | 评论 {c['comment']} | 赞 {c['like']}")
    if feed['images']:
        print(f"  图片 {len(feed['images'])} 张")
    print(f"\n评论 {len(comments)} 条  {page_info}")
    for i, cm in enumerate(comments, 1):
        print(f"  {i}. {cm['user'].get('name')}: {cm['content']}")
        for rep in cm.get('replies') or []:
            print(f"       └ {rep['user'].get('name')}: {rep['content']}")


if __name__ == '__main__':
    main()
