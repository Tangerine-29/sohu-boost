#!/usr/bin/env python3
"""狐友帖子阅读器 · 网页版
不打开 App，纯协议取帖子内容 + 评论列表并渲染。

启动： python3 web_reader.py          → http://127.0.0.1:8788
"""

import argparse
import json
import re
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'sig_reverse'))
from feed_reader import FeedReader          # noqa: E402

READER = None
CACHE = {}
LOCK = threading.Lock()

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>帖子阅读器</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--fg:#e6edf3;--dim:#8b949e;--acc:#1f6feb;--ok:#3fb950;--warn:#d29922}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
.wrap{max-width:720px;margin:0 auto;padding:28px 16px 64px}
h1{font-size:20px;margin:0 0 18px;font-weight:600}
.search{display:flex;gap:10px;margin-bottom:22px}
input{flex:1;background:#0d1117;border:1px solid var(--line);border-radius:10px;color:var(--fg);padding:12px 14px;font-size:14px;font-family:inherit}
input:focus{outline:none;border-color:var(--acc)}
button{background:var(--acc);border:0;border-radius:10px;color:#fff;padding:0 20px;font-size:14px;font-weight:600;cursor:pointer}
button:disabled{opacity:.5}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:18px}
.head{display:flex;align-items:center;gap:12px;margin-bottom:14px}
.avatar{width:44px;height:44px;border-radius:50%;object-fit:cover;background:#21262d}
.who{display:flex;flex-direction:column}
.who b{font-size:15px}
.who span{font-size:12px;color:var(--dim)}
.content{font-size:16px;white-space:pre-wrap;word-break:break-word;margin:6px 0 14px}
.imgs{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:14px}
.imgs img{width:100%;height:110px;object-fit:cover;border-radius:8px;background:#21262d}
.meta{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--dim);border-top:1px solid var(--line);padding-top:12px}
.meta b{color:var(--fg);font-size:14px;font-variant-numeric:tabular-nums}
.section-title{font-size:14px;color:var(--dim);margin:22px 0 10px}
.cmt{display:flex;gap:10px;padding:12px 0;border-bottom:1px solid #21262d}
.cmt:last-child{border-bottom:0}
.cmt .avatar{width:34px;height:34px}
.cmt .body{flex:1;min-width:0}
.cmt .n{font-size:13px;color:var(--dim);margin-bottom:2px}
.cmt .t{font-size:14px;word-break:break-word}
.cmt .sub{font-size:12px;color:var(--dim);margin-top:4px}
.reply{margin-top:8px;padding-left:10px;border-left:2px solid var(--line)}
.empty{color:var(--dim);font-size:14px;padding:18px 0;text-align:center}
.err{color:#f85149;font-size:14px}
button.mini{padding:5px 12px;font-size:12px;background:#21262d;border:1px solid var(--line);color:var(--fg)}
button.mini:hover{background:#30363d}
.spin{display:inline-block;width:14px;height:14px;border:2px solid var(--line);border-top-color:var(--acc);border-radius:50%;animation:s .7s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes s{to{transform:rotate(360deg)}}
</style></head><body><div class="wrap">
<h1>帖子阅读器</h1>
<div class="search">
  <input id="link" placeholder="粘贴帖子分享链接，或 19 位 feedId">
  <button id="go">读取</button>
</div>
<div id="out"></div>
</div>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>n==null?'—':(n>=10000?(n/10000).toFixed(1)+'w':n);
function ts(t){ if(!t) return ''; const d=new Date(Number(t)); if(isNaN(d)) return ''; return d.toLocaleString('zh-CN',{hour12:false}); }
function avatar(u,name){
  if(u) return `<img class="avatar" src="${esc(u)}" onerror="this.style.visibility='hidden'">`;
  return `<div class="avatar"></div>`;
}
(function auto(){
  const sp=new URLSearchParams(location.search);
  const c=sp.get('circle');
  if(c){ setTimeout(()=>loadCircle(c), 80); return; }
  const q=sp.get('link');
  if(q){ $('link').value=q; setTimeout(()=>$('go').click(), 50); }
})();
$('go').onclick=async()=>{
  const link=$('link').value.trim();
  if(!link){$('out').innerHTML='<div class="err">请填写链接</div>';return;}
  $('go').disabled=true;
  $('out').innerHTML='<div class="card"><span class="spin"></span>读取中…</div>';
  try{
    const r=await fetch('/api/feed?link='+encodeURIComponent(link));
    const j=await r.json();
    if(!j.ok){$('out').innerHTML='<div class="card err">'+esc(j.error||'读取失败')+'</div>';$('go').disabled=false;return;}
    render(j);
  }catch(e){ $('out').innerHTML='<div class="card err">'+esc(String(e))+'</div>'; }
  $('go').disabled=false;
};
async function loadCircle(cid){
  $('out').innerHTML='<div class="card"><span class="spin"></span>加载圈子帖子…</div>';
  try{
    const r=await fetch('/api/circle?cid='+encodeURIComponent(cid)+'&pages=3');
    const j=await r.json();
    if(!j.ok){ $('out').innerHTML='<div class="card err">'+esc(j.error)+'</div>'; return; }
    renderCircle(cid, j);
  }catch(e){ $('out').innerHTML='<div class="card err">'+esc(String(e))+'</div>'; }
}
function renderCircle(cid, j){
  const feeds=j.feeds||[], pi=j.pageInfo||{};
  let html='<div class="card"><div class="head"><div class="who"><b>圈子 '+esc(cid)+'</b>'+
           '<span>共 '+fmt(pi.totalCount)+' 条帖 · 已取 '+feeds.length+' 条</span></div></div></div>';
  if(!feeds.length){ html+='<div class="card empty">没有帖子</div>'; }
  feeds.forEach(f=>{
    html+='<div class="card" style="padding:14px">'+
      '<div class="head" style="margin-bottom:8px">'+avatar(f.author.avatar)+
      '<div class="who"><b>'+esc(f.author.name||'匿名')+'</b><span>'+ts(f.createTime)+
      (f.author.level?(' · Lv'+f.author.level):'')+(f.tag?(' · '+esc(f.tag)):'')+'</span></div></div>'+
      '<div class="content" style="font-size:15px;margin:4px 0 8px">'+esc(f.content||'（无文字）')+'</div>';
    if(f.images&&f.images.length){ html+='<div class="imgs">'+f.images.slice(0,3).map(u=>'<img src="'+esc(u)+'">').join('')+'</div>'; }
    html+='<div class="meta" style="border-top:0;padding-top:0">'+
      '<span>曝光 <b>'+fmt(f.counts.exposure)+'</b></span>'+
      '<span>评论 <b>'+fmt(f.counts.comment)+'</b></span>'+
      '<span style="margin-left:auto"><button class="mini" onclick="openFeed(\''+esc(f.feedId)+'\')">看评论</button></span>'+
      '</div></div>';
  });
  if(pi.hasMore) html+='<div class="card empty">还有更多（共 '+fmt(pi.totalCount)+' 条），加大 pages 参数可继续取</div>';
  $('out').innerHTML=html;
  window.__cid=cid;
}
async function openFeed(fid){
  $('link').value=fid; $('go').click();
}
function render(j){
  const f=j.feed, cs=j.comments||[];
  let html='<div class="card">';
  html+='<div class="head">'+avatar(f.author.avatar,f.author.name)+
        '<div class="who"><b>'+esc(f.author.name||'未知作者')+'</b><span>'+esc(f.author.userId||'')+' · '+ts(f.createTime)+'</span></div></div>';
  html+='<div class="content">'+esc(f.content||'（无文字）')+'</div>';
  if(f.images&&f.images.length){ html+='<div class="imgs">'+f.images.map(u=>'<img src="'+esc(u)+'">').join('')+'</div>'; }
  html+='<div class="meta">'+
        '<span>曝光 <b>'+fmt(f.counts.exposure)+'</b></span>'+
        '<span>评论 <b>'+fmt(f.counts.comment)+'</b></span>'+
        '<span>转发 <b>'+fmt(f.counts.repost)+'</b></span>'+
        '<span>赞 <b>'+fmt(f.counts.like)+'</b></span>'+
        '</div>'+
        (f.circleId?('<div style="margin-top:10px"><button class="mini" onclick="loadCircle(\''+esc(f.circleId)+'\')">看这个圈的全部帖子</button></div>'):'')+
        '</div>';
  html+='<div class="section-title">评论 '+(j.pageInfo&&j.pageInfo.totalCount!=null?('（共 '+j.pageInfo.totalCount+' 条）'):'')+'</div>';
  if(!cs.length){ html+='<div class="card empty">这条帖子还没有评论</div>'; }
  else {
    html+='<div class="card">';
    cs.forEach(c=>{
      html+='<div class="cmt">'+avatar(c.user.avatar,c.user.name)+
            '<div class="body"><div class="n">'+esc(c.user.name||'匿名')+
            (c.createTime?(' · '+ts(c.createTime)):'')+
            (c.likeCount?(' · 赞 '+c.likeCount):'')+'</div>'+
            '<div class="t">'+esc(c.content)+'</div>';
      if(c.replies&&c.replies.length){
        html+='<div class="reply">'+c.replies.map(r=>'<div class="t"><span class="n">'+esc(r.user.name||'匿名')+'：</span>'+esc(r.content)+'</div>').join('')+'</div>';
      }
      html+='</div></div>';
    });
    html+='</div>';
  }
  $('out').innerHTML=html;
}
</script></body></html>"""


def extract_feed(link):
    link = (link or '').strip()
    if re.fullmatch(r'\d{16,22}', link):
        return link
    m = re.search(r'/share/feed/(\d{16,22})', link) or \
        re.search(r'feedId[=/](\d{16,22})', link) or \
        re.search(r'(\d{18,20})', link)
    return m.group(1) if m else None


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
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/', '/index.html'):
            return self._send(200, PAGE, 'text/html; charset=utf-8')
        if parsed.path == '/api/circle':
            qs = parse_qs(parsed.query)
            cid = (qs.get('cid') or [''])[0].strip()
            pages = min(int((qs.get('pages') or ['3'])[0]), 20)
            if not cid:
                return self._send(200, json.dumps({'ok': False, 'error': '缺少圈子 ID'}, ensure_ascii=False))
            try:
                with LOCK:
                    feeds, info = READER.circle_feeds(cid, count=20, max_pages=pages)
                if not info.get('ok'):
                    return self._send(200, json.dumps({'ok': False, 'error': str(info)[:200]}, ensure_ascii=False))
                return self._send(200, json.dumps({'ok': True, 'feeds': feeds, 'pageInfo': info},
                                                  ensure_ascii=False))
            except Exception as exc:  # noqa: BLE001
                return self._send(200, json.dumps({'ok': False, 'error': f'{exc.__class__.__name__}: {exc}'}, ensure_ascii=False))

        if parsed.path == '/api/feed':
            link = (parse_qs(parsed.query).get('link') or [''])[0]
            feed_id = extract_feed(link)
            if not feed_id:
                return self._send(200, json.dumps({'ok': False, 'error': '链接里没找到帖子 ID'}, ensure_ascii=False))
            try:
                with LOCK:
                    feed = READER.feed(feed_id)
                    comments, page_info = READER.comments(feed_id, count=20, max_pages=2)
                if not feed.get('ok'):
                    return self._send(200, json.dumps({'ok': False, 'error': '接口返回异常: ' + str(feed)[:200]}, ensure_ascii=False))
                return self._send(200, json.dumps({'ok': True, 'feed': feed, 'comments': comments,
                                                   'pageInfo': page_info}, ensure_ascii=False))
            except Exception as exc:  # noqa: BLE001
                return self._send(200, json.dumps({'ok': False, 'error': f'{exc.__class__.__name__}: {exc}'}, ensure_ascii=False))
        return self._send(404, 'not found', 'text/plain; charset=utf-8')


def main():
    global READER
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1', help='监听地址，0.0.0.0 表示对外')
    ap.add_argument('--port', type=int, default=8788)
    ap.add_argument('--open', action='store_true')
    args = ap.parse_args()
    READER = FeedReader()
    url = f'http://127.0.0.1:{args.port}'
    print(f'帖子阅读器：{url}   （Ctrl+C 停止）')
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
