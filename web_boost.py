#!/usr/bin/env python3
"""狐友流量控制台（极简版）：粘链接 + 填次数，其余全部内部固定。

启动：
    python3 web_boost.py            # http://127.0.0.1:8787
    python3 web_boost.py --port 9000 --open

内部固定：并发 32、每条 ≈ +2 曝光、结束自动等 100 s 落账再报增量。
"""

import argparse
import json
import re
import sys
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from boost_protocol import Session  # noqa: E402

WORKERS = 32          # 固定并发，不暴露到界面
FLUSH_WAIT = 100      # 服务端批量落账等待秒数

SESSION = None
JOBS = {}
JOBS_LOCK = threading.Lock()

PAGE_FILE = HERE / "console.html"


def page():
    return PAGE_FILE.read_text(encoding="utf-8")


def extract_feed(link):
    link = (link or '').strip()
    if re.fullmatch(r'\d{16,22}', link):
        return link
    m = re.search(r'/share/feed/(\d{16,22})', link) or \
        re.search(r'feedId[=/](\d{16,22})', link) or \
        re.search(r'(\d{18,20})', link)
    return m.group(1) if m else None


def run_job(job_id, feed, count):
    job = JOBS[job_id]
    try:
        job['phase'] = 'reading'
        before = SESSION.read_count(feed)
        job['before'] = before

        job['phase'] = 'sending'
        base = int(time.time() * 1000)
        started = time.time()
        done = [0]

        def one(i):
            code = SESSION.report_once(feed, base + i)
            done[0] += 1
            job['sent'] = done[0]
            return code

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            codes = list(pool.map(one, range(count)))
        ok = sum(1 for c in codes if c == 200)
        if ok == 0:
            job['phase'] = 'error'
            job['message'] = '全部失败：身份样本已过期，需要重新抓取'
            return

        job['phase'] = 'flushing'
        job['message'] = f'等待落账 {FLUSH_WAIT}s'
        time.sleep(FLUSH_WAIT)
        after = SESSION.read_count(feed)
        delta = (after - before) if (before is not None and after is not None) else 0
        job['result'] = {'before': before, 'after': after, 'delta': delta,
                         'ok': ok, 'bad': count - ok, 'seconds': round(time.time() - started, 1)}
        job['phase'] = 'done'
    except Exception as exc:  # noqa: BLE001
        job['phase'] = 'error'
        job['message'] = f'{exc.__class__.__name__}: {exc}'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ('/', '/index.html'):
            return self._send(200, page(), 'text/html; charset=utf-8')
        if path == '/api/status':
            job_id = (parse_qs(urlparse(self.path).query).get('id') or [''])[0]
            job = JOBS.get(job_id)
            if not job:
                return self._send(404, json.dumps({'error': 'job not found'}))
            return self._send(200, json.dumps(job, ensure_ascii=False))
        return self._send(404, 'not found', 'text/plain; charset=utf-8')

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_POST(self):
        if urlparse(self.path).path != '/api/start':
            return self._send(404, 'not found', 'text/plain')
        try:
            length = int(self.headers.get('Content-Length') or 0)
            payload = json.loads(self.rfile.read(length) or b'{}')
        except Exception:  # noqa: BLE001
            return self._send(400, json.dumps({'ok': False, 'error': '请求格式错误'}))
        feed = extract_feed(payload.get('link', ''))
        if not feed:
            return self._send(200, json.dumps({'ok': False, 'error': '链接里没找到帖子 ID'}, ensure_ascii=False))
        count = max(1, min(int(payload.get('count') or 250), 20000))
        job_id = uuid.uuid4().hex[:12]
        with JOBS_LOCK:
            JOBS[job_id] = {'id': job_id, 'feed': feed, 'total': count, 'sent': 0,
                            'phase': 'queued', 'message': '', 'result': None}
        threading.Thread(target=run_job, args=(job_id, feed, count), daemon=True).start()
        return self._send(200, json.dumps({'ok': True, 'id': job_id, 'feed': feed}, ensure_ascii=False))


def main():
    global SESSION
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1', help='监听地址，0.0.0.0 表示对外')
    ap.add_argument('--port', type=int, default=8787)
    ap.add_argument('--dump', default=str(HERE / 'session_sample.json'))
    ap.add_argument('--open', action='store_true')
    args = ap.parse_args()

    SESSION = Session(args.dump)
    url = f'http://127.0.0.1:{args.port}'
    print(f'控制台：{url}   （Ctrl+C 停止）')
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
