#!/usr/bin/env python3
"""私聊客户端：拉会话、读消息、发消息。

实测接口（2026-11）：
    POST dm-ol.sns.sohu.com/dm/api/v2/message      发消息
         to_user_id / message / type=0(文本)
    GET  dm-ol.sns.sohu.com/dm/api/v3/message      拉消息（增量）
         last_grp_eid / last_priv_eid / limit
    GET  dm-spc-ol.sns.sohu.com/dm-poll/api/v2/newmsgcount   未读数

响应结构：
    data.msg_data = {
        conversation_id: "p{uid1}{uid2}",
        from_user_id, to_user_id, msg, send_time,
        id: "p_2117496013853016090"
    }
    data.priv_msgs = [{conversation_id, from_user_id, msgs: [msg_data...]}]
    data.priv_eid  = "14"   ← 下轮拉取的游标
"""

import tz
import json
import time
from pathlib import Path
from typing import Optional

from feed_reader import FeedReader

DM_HOST = 'dm-ol.sns.sohu.com'
DM_POLL_HOST = 'dm-spc-ol.sns.sohu.com'
STATE_PATH = Path(__file__).resolve().parent / 'dm_state.json'


def now_str() -> str:
    return tz.now_str()


class DMClient:
    def __init__(self, session='session_sample.json'):
        self.reader = FeedReader(session)
        self.me = str(self.reader.s.user_id)
        self._state = self._load_state()

    # ---------- 状态 ----------
    def _load_state(self):
        if STATE_PATH.exists():
            try:
                return json.loads(STATE_PATH.read_text())
            except json.JSONDecodeError:
                pass
        return {'priv_eid': '', 'grp_eid': '', 'seen': {}, 'pending': []}

    def _save_state(self):
        tmp = STATE_PATH.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(self._state, ensure_ascii=False, indent=1))
        tmp.replace(STATE_PATH)

    # ---------- 请求 ----------
    def _req(self, path, params, method='GET', host=DM_HOST):
        p = self.reader._base_params()
        p.pop('extras', None)      # dm 接口不接受这个
        p.update(params)
        return self.reader._request(path, p, method, host=host)

    # ---------- 发消息 ----------
    def send(self, to_user_id, text, mtype='0'):
        """发一条私聊。返回 (ok, msg_data_or_error)。"""
        to_user_id = str(to_user_id).strip()
        if not to_user_id:
            return False, 'to_user_id 为空'
        st, tx = self._req('/dm/api/v2/message',
                           {'to_user_id': to_user_id, 'message': text, 'type': mtype},
                           'POST')
        try:
            j = json.loads(tx)
        except json.JSONDecodeError:
            return False, f'HTTP {st} {tx[:120]}'
        if j.get('status') != 100000:
            return False, f"{j.get('status')} {j.get('desc')}"
        return True, (j.get('data') or {}).get('msg_data') or {}

    # ---------- 拉消息 ----------
    def pull(self, limit=100, reset=False):
        """拉取自上次以来的新消息。

        返回 (conversations, raw_data)
        conversations = [{conversation_id, from_user_id, msgs: [...]}]
        """
        eid = '' if reset else self._state.get('priv_eid', '')
        st, tx = self._req('/dm/api/v3/message', {
            'last_grp_eid': '' if reset else self._state.get('grp_eid', ''),
            'last_priv_eid': eid,
            'limit': str(limit),
        }, 'GET')
        try:
            j = json.loads(tx)
        except json.JSONDecodeError:
            return [], {'ok': False, 'raw': f'HTTP {st} {tx[:120]}'}

        d = j.get('data') or {}
        convs = d.get('priv_msgs') or []

        # 关键：先把新消息存进 pending，再推进游标。
        # 服务端是一次性消费语义，拉到后拉不回来，落盘能防处理失败丢消息。
        # 只存别人发来的（自己发的不进 pending，否则会被当成待回复）
        fresh = [m for m in self.flatten(convs) if m['from'] != self.me]
        if fresh:
            pend = self._state.setdefault('pending', [])
            known = {x.get('msg_id') for x in pend}
            for m in fresh:
                if m['msg_id'] not in known:
                    pend.append(m)

        # 更新游标
        if d.get('priv_eid'):
            self._state['priv_eid'] = str(d['priv_eid'])
        if d.get('grp_eid'):
            self._state['grp_eid'] = str(d['grp_eid'])
        self._save_state()

        return convs, {'ok': j.get('status') == 100000, 'status': j.get('status'),
                       'fresh': len(fresh), 'raw_total': len(self.flatten(convs))}

    # ---------- 整理 ----------
    def flatten(self, convs):
        """把嵌套结构拉平，只保留别人发来的文本消息。

        返回 [{'msg_id','from','to','text','ts','conversation_id'}]
        """
        out = []
        for c in convs:
            cid = c.get('conversation_id') or ''
            for m in (c.get('msgs') or []):
                # 有的版本 msgs 里直接是字段，有的套一层 msg
                md = m if isinstance(m.get('msg'), str) else (m.get('msg') or {})
                sender = str(m.get('from_user_id') or md.get('from_user_id') or '')
                text = m.get('msg') if isinstance(m.get('msg'), str) else (md.get('msg') or '')
                msg_id = str(m.get('id') or md.get('id') or '')
                ts = m.get('send_time') or md.get('send_time') or 0
                out.append({
                    'msg_id': msg_id,
                    'from': sender,
                    'to': str(m.get('to_user_id') or md.get('to_user_id') or ''),
                    'text': str(text or ''),
                    'ts': int(ts) if ts else 0,
                    'conversation_id': cid,
                })
        return out

    def new_from_others(self, convs):
        """只要别人发给我的、没处理过的文本消息。"""
        seen = self._state.get('seen') or {}
        out = []
        for m in self.flatten(convs):
            if not m['text']:
                continue                      # 跳过非文本（语音/图片）
            if m['from'] == self.me:
                continue                      # 自己发的
            if m['msg_id'] in seen:
                continue
            out.append(m)
        return out

    def pending(self):
        """取出待处理消息（没处理成功的会留在这里）。"""
        return list(self._state.get('pending') or [])

    def clear_pending(self, msg_ids):
        """处理成功后才移除。"""
        drop = {str(x) for x in msg_ids}
        self._state['pending'] = [
            m for m in (self._state.get('pending') or [])
            if str(m.get('msg_id')) not in drop
        ]
        self._save_state()

    def mark_seen(self, msg_ids):
        seen = self._state.setdefault('seen', {})
        ts = int(time.time())
        for x in msg_ids:
            seen[str(x)] = ts
        # 只保留最近 2000 条，防止无限增长
        if len(seen) > 2000:
            keep = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:2000]
            self._state['seen'] = dict(keep)
        self._save_state()

    # ---------- 未读数 ----------
    def unread(self):
        st, tx = self._req('/dm-poll/api/v2/newmsgcount', {}, 'GET', host=DM_POLL_HOST)
        try:
            return json.loads(tx)
        except json.JSONDecodeError:
            return {'ok': False, 'raw': f'HTTP {st} {tx[:100]}'}


if __name__ == '__main__':
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument('--send', help='发给 who（用户 ID）')
    ap.add_argument('--text', default='测试', help='消息内容')
    ap.add_argument('--pull', action='store_true', help='拉消息')
    ap.add_argument('--reset', action='store_true', help='从头拉')
    ap.add_argument('--unread', action='store_true', help='未读数')
    args = ap.parse_args()

    c = DMClient()
    print(f'我的 ID: {c.me}')

    if args.send:
        ok, info = c.send(args.send, args.text)
        print(f'发送: {"✅" if ok else "❌"} {info}')

    if args.pull:
        convs, info = c.pull(limit=100, reset=args.reset)
        print(f'会话数: {len(convs)}')
        rows = c.flatten(convs)
        print(f'消息数: {len(rows)}')
        for r in rows[-10:]:
            t = tz.from_ms(r['ts']) if r['ts'] else '?'
            who = '我' if r['from'] == c.me else r['from']
            print(f'  [{t}] {who}: {r["text"][:40]}')

    if args.unread:
        print('未读数:', json.dumps(c.unread(), ensure_ascii=False)[:300])
