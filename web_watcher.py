#!/usr/bin/env python3
"""曝光触发监控面板
显示圈子「最近 N 天」发布的全部帖子，以及哪些帖子的评论触发了 <exposure:N>。

启动： python3 web_watcher.py --circle <CIRCLE_ID> --days 7
访问： http://127.0.0.1:8790
"""

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
WEB_DIST = HERE / 'web_dist'          # Vite 构建产物（存在则优先使用）
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'sig_reverse'))
from feed_reader import FeedReader, ts_seconds      # noqa: E402
import watcher_config                                # noqa: E402
import ai_reply                                      # noqa: E402
import knowledge                                     # noqa: E402

READER = None
STATE_PATH = HERE / 'watcher_state.json'
DEFAULTS = {'circle': '<CIRCLE_ID>', 'days': 7}
CACHE = {'at': 0, 'key': None, 'data': None}
LOCK = threading.Lock()

PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>曝光触发监控</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--line:#30363d;--fg:#e6edf3;--dim:#8b949e;--acc:#1f6feb;--ok:#3fb950;--warn:#d29922}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:26px 16px 60px}
h1{font-size:19px;margin:0 0 6px;font-weight:600}
.sub{color:var(--dim);font-size:13px;margin-bottom:18px}
.bar{display:flex;gap:10px;margin-bottom:18px;flex-wrap:wrap}
.card2{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:12px 14px;margin-bottom:18px}
textarea:focus,#ai_mode:focus{outline:none;border-color:var(--acc)}
.ai-ok{color:var(--ok);font-weight:600}
.ai-err{color:#f85149}
.cfgrow{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.cfgrow label{font-size:12px;color:var(--dim);white-space:nowrap}
.hint{font-size:12px;color:var(--dim)}
#cfgmsg.ok{color:var(--ok)}
#cfgmsg.err{color:#f85149}
input{background:#0d1117;border:1px solid var(--line);border-radius:9px;color:var(--fg);padding:10px 12px;font-size:13px;font-family:inherit}
input:focus{outline:none;border-color:var(--acc)}
button{background:var(--acc);border:0;border-radius:9px;color:#fff;padding:0 18px;font-size:13px;font-weight:600;cursor:pointer}
button:disabled{opacity:.5}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:11px;padding:12px 14px}
.stat b{display:block;font-size:20px;font-variant-numeric:tabular-nums}
.stat span{font-size:11px;color:var(--dim)}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:10px 8px;border-bottom:1px solid #21262d;vertical-align:top}
th{color:var(--dim);font-weight:500;font-size:12px;position:sticky;top:0;background:var(--bg)}
tr.hit{background:rgba(63,185,80,.06)}
td.id{font:12px ui-monospace,Menlo,monospace;color:var(--dim)}
td.c{max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:11px;font-weight:600}
.b-hit{background:rgba(63,185,80,.15);color:var(--ok)}
.b-none{background:#21262d;color:var(--dim)}
.b-old{background:rgba(210,153,34,.15);color:var(--warn)}
.row{display:flex;gap:12px;align-items:center;padding:6px 0;font-size:12px;color:var(--dim)}
.spin{display:inline-block;width:13px;height:13px;border:2px solid var(--line);border-top-color:var(--acc);border-radius:50%;animation:s .7s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes s{to{transform:rotate(360deg)}}
.err{color:#f85149}
</style></head><body><div class="wrap">
<h1>曝光触发监控</h1>
<div class="sub" id="sub">加载中…</div>
<div class="card2">
  <div class="cfgrow">
    <label>触发关键词</label>
    <input id="kw" placeholder="exposure" style="width:130px">
    <span class="hint" id="ruleHint">‹exposure:数字›</span>
    <label style="margin-left:8px">窗口(天)</label>
    <input id="wd" type="number" min="1" max="60" style="width:70px">
    <label style="margin-left:8px">曝光上限</label>
    <input id="maxexp" type="number" min="1" step="1000" style="width:110px">
    <button id="savecfg">保存规则</button>
    <span id="cfgmsg" class="hint"></span>
  </div>
  <div class="cfgrow" style="margin-top:8px">
    <label>圈子 ID</label>
    <input id="cid" style="flex:1;min-width:240px" placeholder="圈子 ID">
    <button id="go">刷新列表</button>
  </div>
  <details style="margin-top:10px">
    <summary style="cursor:pointer;font-size:12px;color:var(--dim)">AI 自动回复设置</summary>
    <div class="cfgrow" style="margin-top:10px">
      <label>启用</label>
      <input id="ai_en" type="checkbox" style="width:auto">
      <label>字数上限</label>
      <input id="ai_len" type="number" min="4" max="200" style="width:70px">
      <label>回复范围</label>
      <select id="ai_mode" style="background:#0d1117;border:1px solid var(--line);border-radius:8px;color:var(--fg);padding:8px 10px;font-size:13px">
        <option value="trigger_only">只回暗号</option>
        <option value="all">回所有评论</option>
      </select>
      <label>跳过自己</label>
      <input id="ai_skip" type="checkbox" style="width:auto">
    </div>
    <div class="cfgrow" style="margin-top:8px">
      <label>接口</label>
      <input id="ai_base" placeholder="https://api.xxx.com/v1" style="flex:1;min-width:220px">
    </div>
    <div class="cfgrow" style="margin-top:8px">
      <label>密钥</label>
      <input id="ai_key" type="password" placeholder="sk-..." style="flex:1;min-width:220px">
      <label>模型</label>
      <input id="ai_model" placeholder="glm-5.3" style="width:150px">
    </div>
    <div class="cfgrow" style="margin-top:8px;align-items:flex-start">
      <label style="padding-top:8px">人设</label>
      <textarea id="ai_prompt" rows="5" placeholder="留空使用内置人格（建院大肥鱼）" style="flex:1;min-width:300px;background:#0d1117;border:1px solid var(--line);border-radius:8px;color:var(--fg);padding:10px;font-size:12px;font-family:inherit;line-height:1.6"></textarea>
    </div>
    <div class="cfgrow" style="margin-top:10px">
      <label>测试</label>
      <input id="ai_tfeed" placeholder="帖子内容" value="大家好" style="width:150px">
      <input id="ai_ttext" placeholder="对方回复" value="不好" style="width:130px">
      <button id="ai_test">测试生成</button>
      <button id="ai_save">保存 AI 设置</button>
      <span id="ai_msg" class="hint"></span>
    </div>
    <div class="cfgrow" style="margin-top:8px">
      <label>结果</label>
      <div id="ai_out" style="flex:1;font-size:13px;color:var(--fg);min-height:20px"></div>
    </div>
  </details>
  <details style="margin-top:10px">
    <summary style="cursor:pointer;font-size:12px;color:var(--dim)">知识库（让 AI 知道学校的真实情况）</summary>
    <div class="cfgrow" style="margin-top:10px">
      <input id="kb_title" placeholder="标题，如「食堂分布」" style="width:180px">
      <input id="kb_tags" placeholder="关键词（逗号分隔）如 食堂,吃饭" style="width:220px">
      <label style="display:flex;align-items:center;gap:6px"><input id="kb_en" type="checkbox" checked style="width:auto">启用</label>
    </div>
    <div class="cfgrow" style="margin-top:8px;align-items:flex-start">
      <textarea id="kb_content" rows="3" placeholder="具体内容，如「一食堂在教学楼东侧，早餐 6:30-9:00」" style="flex:1;min-width:300px;background:#0d1117;border:1px solid var(--line);border-radius:8px;color:var(--fg);padding:10px;font-size:13px;font-family:inherit;line-height:1.6"></textarea>
    </div>
    <div class="cfgrow" style="margin-top:8px">
      <button id="kb_add">添加条目</button>
      <button id="kb_reload">刷新</button>
      <span id="kb_msg" class="hint"></span>
    </div>
    <div id="kb_list" style="margin-top:12px"></div>
  </details>
</div>
<div class="stats">
  <div class="stat"><b id="s-feeds">—</b><span>窗口内帖子</span></div>
  <div class="stat"><b id="s-hits">—</b><span>已触发帖数</span></div>
  <div class="stat"><b id="s-exp">—</b><span>累计推送曝光</span></div>
  <div class="stat"><b id="s-cmt">—</b><span>触发评论数</span></div>
</div>
<div id="out"><div class="row"><span class="spin"></span>读取中…</div></div>
</div>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=n=>n==null?'—':(n>=10000?(n/10000).toFixed(1)+'w':n);
const tstr=t=>{ if(!t) return ''; const d=new Date(Number(t)); return isNaN(d)?'':d.toLocaleString('zh-CN',{hour12:false,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}); };
let timer=null;

async function load(){
  const cid=$('cid').value.trim()||'<CIRCLE_ID>';
  const days=($('wd')&&$('wd').value)||7;
  $('go').disabled=true;
  $('out').innerHTML='<div class="row"><span class="spin"></span>读取中…</div>';
  try{
    const r=await fetch('/api/window?circle='+encodeURIComponent(cid)+'&days='+days);
    const j=await r.json();
    $('go').disabled=false;
    if(!j.ok){ $('out').innerHTML='<div class="row err">'+esc(j.error||'失败')+'</div>'; return; }
    render(j);
  }catch(e){ $('go').disabled=false; $('out').innerHTML='<div class="row err">'+esc(String(e))+'</div>'; }
}
function render(j){
  const feeds=j.feeds||[], trig=j.triggered||{}, cmts=j.triggeredComments||[];
  const hitFeeds=Object.keys(trig).length;
  const totalExp=Object.values(trig).reduce((a,b)=>a+(b.n||0),0);
  $('s-feeds').textContent=feeds.length;
  $('s-hits').textContent=hitFeeds;
  $('s-exp').textContent=fmt(totalExp);
  $('s-cmt').textContent=cmts.length;
  $('sub').textContent='圈子 '+j.circle+' · 最近 '+j.days+' 天 · 更新 '+new Date().toLocaleTimeString('zh-CN',{hour12:false});
  if(!feeds.length){ $('out').innerHTML='<div class="row">窗口内没有帖子</div>'; return; }
  let h='<table><thead><tr><th>时间</th><th>作者</th><th>内容</th><th>评论</th><th>曝光</th><th>触发</th></tr></thead><tbody>';
  feeds.forEach(f=>{
    const t=trig[f.feedId];
    h+='<tr class="'+(t?'hit':'')+'">'+
       '<td style="white-space:nowrap">'+tstr(f.createTime)+'</td>'+
       '<td style="white-space:nowrap">'+esc((f.author&&f.author.name)||'匿名')+'</td>'+
       '<td class="c" title="'+esc(f.content)+'">'+esc(f.content||'（无文字）')+'</td>'+
       '<td>'+(f.counts?f.counts.comment:'—')+'</td>'+
       '<td>'+(f.counts?fmt(f.counts.exposure):'—')+'</td>'+
       '<td>'+(t?('<span class="badge b-hit">✓ +'+t.n+'</span>'+(t.sent?('<div class="row" style="padding:2px 0">已发 '+t.sent+' 条</div>'):''))
              :'<span class="badge b-none">—</span>')+'</td>'+
       '</tr>';
  });
  h+='</tbody></table>';
  if(cmts.length){
    h+='<div class="row" style="margin-top:18px">触发明细</div><table><thead><tr><th>时间</th><th>帖子</th><th>评论</th><th>要求</th><th>已发</th></tr></thead><tbody>';
    cmts.forEach(c=>{
      h+='<tr><td style="white-space:nowrap">'+esc(c.at||'')+'</td>'+
         '<td class="id">'+esc(c.feedId)+'</td>'+
         '<td class="c" title="'+esc(c.content)+'">'+esc(c.content||'')+'</td>'+
         '<td>+'+esc(c.n)+'</td><td>'+esc(c.sent||0)+' 条</td></tr>';
    });
    h+='</tbody></table>';
  }
  $('out').innerHTML=h;
}
async function loadConfig(){
  try{
    const r=await fetch('/api/config'); const j=await r.json();
    if(!j.ok) return;
    $('kw').value=j.config.keyword||'exposure';
    $('wd').value=j.config.window_days||7;
    $('maxexp').value=j.config.max_exposure||50000;
    $('ruleHint').textContent='生效：'+j.rule;
  }catch(e){}
}
$('savecfg').onclick=async()=>{
  const body={keyword:$('kw').value.trim()||'exposure',
              window_days:parseInt($('wd').value,10)||7,
              max_exposure:parseInt($('maxexp').value,10)||50000};
  $('cfgmsg').textContent='保存中…'; $('cfgmsg').className='hint';
  try{
    const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const j=await r.json();
    if(j.ok){ $('cfgmsg').textContent='已保存，下一轮生效'; $('cfgmsg').className='hint ok'; $('ruleHint').textContent='生效：'+j.rule; }
    else { $('cfgmsg').textContent=j.error||'失败'; $('cfgmsg').className='hint err'; }
  }catch(e){ $('cfgmsg').textContent=String(e); $('cfgmsg').className='hint err'; }
};
async function loadAi(){
  try{
    const r=await fetch('/api/config'); const j=await r.json();
    if(!j.ok) return;
    const c=j.config;
    $('ai_en').checked=!!c.ai_enabled;
    $('ai_skip').checked=!!c.ai_skip_own;
    $('ai_len').value=c.ai_max_len||20;
    $('ai_mode').value=c.ai_reply_mode||'trigger_only';
    $('ai_base').value=c.ai_base_url||'';
    $('ai_key').value=c.ai_api_key||'';
    $('ai_model').value=c.ai_model||'';
    $('ai_prompt').value=c.ai_system_prompt||'';
  }catch(e){}
}
$('ai_save').onclick=async()=>{
  $('ai_msg').textContent='保存中…'; $('ai_msg').className='hint';
  const body={
    keyword:($('kw')&&$('kw').value)||'exposure',
    window_days:parseInt($('wd').value,10)||7,
    max_exposure:parseInt($('maxexp').value,10)||50000,
    ai_enabled:$('ai_en').checked,
    ai_skip_own:$('ai_skip').checked,
    ai_max_len:parseInt($('ai_len').value,10)||20,
    ai_reply_mode:$('ai_mode').value,
    ai_base_url:$('ai_base').value.trim(),
    ai_api_key:$('ai_key').value.trim(),
    ai_model:$('ai_model').value.trim(),
    ai_system_prompt:$('ai_prompt').value.trim(),
    auto_reply:true,
  };
  try{
    const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const j=await r.json();
    if(j.ok){ $('ai_msg').textContent='已保存，下一轮生效'; $('ai_msg').className='hint ai-ok'; }
    else { $('ai_msg').textContent=j.error||'失败'; $('ai_msg').className='hint ai-err'; }
  }catch(e){ $('ai_msg').textContent=String(e); $('ai_msg').className='hint ai-err'; }
};
$('ai_test').onclick=async()=>{
  $('ai_out').innerHTML='<span class="hint">生成中…（首次可能 3-10 秒）</span>';
  try{
    const q='?text='+encodeURIComponent($('ai_ttext').value||'不好')
           +'&feed='+encodeURIComponent($('ai_tfeed').value||'大家好');
    const r=await fetch('/api/ai/test'+q);
    const j=await r.json();
    $('ai_out').innerHTML = j.ok
      ? '<span class="ai-ok">'+esc(j.text)+'</span> <span class="hint">（'+esc(j.model||'')+' · '+String(j.text).length+'字）</span>'
      : '<span class="ai-err">'+esc(j.text)+'</span>';
  }catch(e){ $('ai_out').innerHTML='<span class="ai-err">'+esc(String(e))+'</span>'; }
};
$('go').onclick=load;
loadConfig();
loadAi();
document.getElementById('savecfg').addEventListener('click',()=>setTimeout(load,300));
$('cid').value=localStorage.getItem('cid')||'<CIRCLE_ID>';
$('wd').value=localStorage.getItem('wd')||'7';
$('cid').onchange=()=>localStorage.setItem('cid',$('cid').value);
$('wd').onchange=()=>localStorage.setItem('wd',$('wd').value);
load();
setInterval(load, 180000);   // 3 分钟自动刷新，与监听器轮询间隔一致

// ---------- 知识库 ----------
function kbMsg(t, ok){
  const el=$('kb_msg'); if(!el) return;
  el.textContent=t; el.style.color = ok===false ? '#ff7b72' : '#7ee787';
  clearTimeout(kbMsg._t); kbMsg._t=setTimeout(()=>{el.textContent='';},4000);
}
async function kbLoad(){
  const box=$('kb_list'); if(!box) return;
  box.innerHTML='<div class="hint">加载中…</div>';
  try{
    const r=await fetch('/api/kb'); const j=await r.json();
    if(!j.ok){ box.innerHTML='<div class="hint" style="color:#ff7b72">'+esc(j.error||'失败')+'</div>'; return; }
    const list=j.entries||[];
    if(!list.length){ box.innerHTML='<div class="hint">还没有条目，上面添加一条试试</div>'; return; }
    box.innerHTML = list.map(e=>`
      <div style="border:1px solid var(--line);border-radius:8px;padding:10px;margin-bottom:8px;${e.enabled?'':'opacity:.5'}">
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">
          <b style="font-size:13px">${esc(e.title)}</b>
          ${e.tags?'<span class="hint" style="font-size:11px">'+esc(e.tags)+'</span>':''}
          <span style="flex:1"></span>
          <button class="mini" onclick="kbToggle('${e.id}',${!e.enabled})">${e.enabled?'停用':'启用'}</button>
          <button class="mini" onclick="kbEdit('${e.id}')">编辑</button>
          <button class="mini" onclick="kbDel('${e.id}')" style="color:#ff7b72">删除</button>
        </div>
        <div style="font-size:12px;color:var(--dim);line-height:1.7;white-space:pre-wrap">${esc(e.content)}</div>
      </div>`).join('');
  }catch(err){ box.innerHTML='<div class="hint" style="color:#ff7b72">'+esc(String(err))+'</div>'; }
}
async function kbAdd(){
  const title=($('kb_title').value||'').trim();
  const content=($('kb_content').value||'').trim();
  const tags=($('kb_tags').value||'').trim();
  const enabled=$('kb_en').checked;
  if(!title||!content){ kbMsg('标题和内容都不能为空', false); return; }
  try{
    const r=await fetch('/api/kb',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({title,content,tags,enabled})});
    const j=await r.json();
    if(!j.ok){ kbMsg(j.error||'添加失败', false); return; }
    kbMsg('已添加：'+title, true);
    $('kb_title').value=''; $('kb_content').value=''; $('kb_tags').value='';
    kbLoad();
  }catch(err){ kbMsg(String(err), false); }
}
async function kbToggle(id, enabled){
  try{
    const r=await fetch('/api/kb',{method:'PUT',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id,enabled})});
    const j=await r.json();
    if(j.ok){ kbMsg(enabled?'已启用':'已停用', true); kbLoad(); }
    else kbMsg(j.error||'失败', false);
  }catch(err){ kbMsg(String(err), false); }
}
async function kbEdit(id){
  const r=await fetch('/api/kb'); const j=await r.json();
  const e=(j.entries||[]).find(x=>x.id===id); if(!e) return;
  const title=prompt('标题', e.title); if(title===null) return;
  const tags=prompt('关键词（逗号分隔）', e.tags||''); if(tags===null) return;
  const content=prompt('内容', e.content); if(content===null) return;
  try{
    const rr=await fetch('/api/kb',{method:'PUT',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id,title,tags,content})});
    const jj=await rr.json();
    if(jj.ok){ kbMsg('已保存', true); kbLoad(); }
    else kbMsg(jj.error||'失败', false);
  }catch(err){ kbMsg(String(err), false); }
}
async function kbDel(id){
  if(!confirm('确定删除这条？')) return;
  try{
    const r=await fetch('/api/kb',{method:'DELETE',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id})});
    const j=await r.json();
    if(j.ok){ kbMsg('已删除', true); kbLoad(); }
    else kbMsg(j.error||'失败', false);
  }catch(err){ kbMsg(String(err), false); }
}
if($('kb_add')){
  $('kb_add').onclick=kbAdd;
  $('kb_reload').onclick=kbLoad;
  kbLoad();
}
</script></body></html>"""


def load_triggered():
    """从 watcher_state.json 汇总触发记录。"""
    if not STATE_PATH.exists():
        return {}, []
    try:
        state = json.loads(STATE_PATH.read_text())
    except json.JSONDecodeError:
        return {}, []
    by_feed, comments = {}, []
    for cid, rec in state.items():
        if str(cid).startswith('__'):      # __meta__ 等内部键
            continue
        if not isinstance(rec, dict) or rec.get('dry'):
            continue
        fid = str(rec.get('feedId') or '')
        n = int(rec.get('n') or 0)
        ent = by_feed.setdefault(fid, {'n': 0, 'sent': 0, 'count': 0, 'at': rec.get('at')})
        ent['n'] += n
        ent['sent'] += int(rec.get('sent') or 0)
        ent['count'] += 1
        ent['at'] = rec.get('at') or ent['at']
        comments.append({'commentId': cid, 'feedId': fid, 'n': n,
                         'sent': rec.get('sent'), 'at': rec.get('at'),
                         'content': rec.get('content')})
    comments.sort(key=lambda x: str(x.get('at') or ''), reverse=True)
    return by_feed, comments


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        data = body.encode('utf-8') if isinstance(body, str) else body
        try:
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            # 浏览器刷新/切页/超时导致客户端提前断开，属正常现象
            pass

    def _send_file(self, path, ctype=None):
        """返回静态文件。"""
        try:
            data = path.read_bytes()
        except OSError:
            return self._send(404, 'not found', 'text/plain; charset=utf-8')
        if ctype is None:
            ext = path.suffix.lower()
            ctype = {
                '.js': 'text/javascript; charset=utf-8',
                '.css': 'text/css; charset=utf-8',
                '.html': 'text/html; charset=utf-8',
                '.json': 'application/json; charset=utf-8',
                '.svg': 'image/svg+xml',
                '.png': 'image/png',
                '.ico': 'image/x-icon',
                '.woff2': 'font/woff2',
            }.get(ext, 'application/octet-stream')
        try:
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'public, max-age=3600' if path.suffix != '.html' else 'no-store')
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass

    def _read_json(self):
        """读请求体并解析 JSON，失败返回空 dict。"""
        try:
            length = int(self.headers.get('Content-Length') or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            d = json.loads(raw or b'{}')
            return d if isinstance(d, dict) else {}
        except Exception:  # noqa: BLE001
            return {}

    def do_POST(self):
        parsed = urlparse(self.path)

        # ---- 账号信息更新（给 iOS 插件用）----
        if parsed.path == '/api/session/update':
            try:
                # 简单鉴权：X-Auth-Token 必须匹配配置里的 session_push_key
                cfg = watcher_config.load()
                expect = str(cfg.get('session_push_key') or '').strip()
                got = str(self.headers.get('X-Auth-Token') or '').strip()
                if expect and got != expect:
                    return self._send(403, json.dumps(
                        {'ok': False, 'error': 'auth failed'}, ensure_ascii=False))

                body = self._read_json()
                target = str(body.get('name') or 'session_sample').strip()
                if target not in ('session_sample', 'session_boost'):
                    return self._send(400, json.dumps(
                        {'ok': False, 'error': 'name 只能是 session_sample / session_boost'},
                        ensure_ascii=False))

                headers = body.get('headers') or {}
                if not isinstance(headers, dict) or not headers.get('token'):
                    return self._send(400, json.dumps(
                        {'ok': False, 'error': 'headers.token 缺失'}, ensure_ascii=False))

                # 必须有的字段
                need = ['S-CID', 'S-PID', 'S-PPID', 'token']
                miss = [k for k in need if not headers.get(k)]
                if miss:
                    return self._send(400, json.dumps(
                        {'ok': False, 'error': '缺少 ' + ','.join(miss)}, ensure_ascii=False))

                path = Path(__file__).resolve().parent / f'{target}.json'
                bak = path.with_suffix('.json.bak')

                # 备份：只在「旧文件是真实数据」且「备份文件还不存在」时写入，
                # 避免多次测试把真数据的备份覆盖成测试数据
                if path.exists() and not bak.exists():
                    try:
                        old = json.loads(path.read_text())
                        old_tok = str((old.get('headers') or {}).get('token') or '')
                        # 真实 token 一般 100+ 字符；测试 token 很短
                        if len(old_tok) >= 60:
                            bak.write_bytes(path.read_bytes())
                            print(f'[{time.strftime("%H:%M:%S")}] 备份 {target} → .bak', flush=True)
                    except (OSError, json.JSONDecodeError):
                        pass

                payload = {
                    'event': 'push',
                    'at': int(body.get('at') or time.time() * 1000),
                    'url': str(body.get('url') or ''),
                    'method': str(body.get('method') or 'POST'),
                    'body': str(body.get('body') or ''),
                    'headers': headers,
                    'cookie': body.get('cookie'),
                }
                tmp = path.with_suffix('.json.tmp')
                tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
                tmp.replace(path)
                try:
                    path.chmod(0o600)
                except OSError:
                    pass

                print(f'[{time.strftime("%H:%M:%S")}] 收到 {target} 更新: '
                      f'S-PID={headers.get("S-PID")} S-CID={headers.get("S-CID")}', flush=True)
                return self._send(200, json.dumps({
                    'ok': True,
                    'updated': f'{target}.json',
                    'pid': headers.get('S-PID'),
                    'cid': headers.get('S-CID'),
                    'token_len': len(str(headers.get('token') or '')),
                }, ensure_ascii=False))
            except Exception as exc:  # noqa: BLE001
                return self._send(500, json.dumps(
                    {'ok': False, 'error': str(exc)[:200]}, ensure_ascii=False))

        # ---- 知识库：新增 ----
        if parsed.path == '/api/kb':
            try:
                body = self._read_json()
                # 整体覆盖
                if 'text' in body:
                    n = knowledge.replace_all(body.get('text') or '')
                    return self._send(200, json.dumps(
                        {'ok': True, 'total': n}, ensure_ascii=False))
                # 追加一行
                line = str(body.get('line') or '').strip()
                if not line:
                    return self._send(400, json.dumps(
                        {'ok': False, 'error': '内容不能为空'}, ensure_ascii=False))
                added = knowledge.add_line(line)
                return self._send(200, json.dumps(
                    {'ok': True, 'added': added,
                     'total': len(knowledge.load_lines())}, ensure_ascii=False))
            except Exception as exc:  # noqa: BLE001
                return self._send(500, json.dumps({'ok': False, 'error': str(exc)[:200]},
                                                  ensure_ascii=False))

        if parsed.path != '/api/config':
            return self._send(404, 'not found', 'text/plain')
        try:
            length = int(self.headers.get('Content-Length') or 0)
            payload = json.loads(self.rfile.read(length) or b'{}')
        except Exception:  # noqa: BLE001
            return self._send(400, json.dumps({'ok': False, 'error': '请求格式错误'}, ensure_ascii=False))
        cfg = watcher_config.save(payload or {})
        # 让列表缓存失效，下一轮重新拉
        CACHE['at'] = 0
        return self._send(200, json.dumps({'ok': True, 'config': cfg,
                                           'rule': watcher_config.describe(cfg)}, ensure_ascii=False))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/kb':
            try:
                body = self._read_json()
                eid = str(body.get('id') or '').strip()
                if not eid:
                    return self._send(400, json.dumps({'ok': False, 'error': '缺少 id'},
                                                      ensure_ascii=False))
                e = knowledge.update(eid, content=body.get('content') or '')
                if e is None:
                    return self._send(404, json.dumps({'ok': False, 'error': '条目不存在'},
                                                      ensure_ascii=False))
                return self._send(200, json.dumps({'ok': True, 'entry': e}, ensure_ascii=False))
            except Exception as exc:  # noqa: BLE001
                return self._send(500, json.dumps({'ok': False, 'error': str(exc)[:200]},
                                                  ensure_ascii=False))
        return self._send(404, json.dumps({'ok': False, 'error': 'not found'}, ensure_ascii=False))

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/kb':
            try:
                body = self._read_json()
                eid = str(body.get('id') or '').strip()
                ok = knowledge.delete(eid) if eid else False
                return self._send(200 if ok else 404, json.dumps(
                    {'ok': ok, 'error': '' if ok else '条目不存在'}, ensure_ascii=False))
            except Exception as exc:  # noqa: BLE001
                return self._send(500, json.dumps({'ok': False, 'error': str(exc)[:200]},
                                                  ensure_ascii=False))
        return self._send(404, json.dumps({'ok': False, 'error': 'not found'}, ensure_ascii=False))

    def do_GET(self):
        parsed = urlparse(self.path)

        # ---- 知识库：列表 ----
        if parsed.path == '/api/kb':
            try:
                lines = knowledge.load_lines()
                return self._send(200, json.dumps(
                    {'ok': True, 'lines': lines, 'total': len(lines)}, ensure_ascii=False))
            except Exception as exc:  # noqa: BLE001
                return self._send(500, json.dumps({'ok': False, 'error': str(exc)[:200]},
                                                  ensure_ascii=False))
        if parsed.path in ('/', '/index.html') and WEB_DIST.exists():
            return self._send_file(WEB_DIST / 'index.html', 'text/html; charset=utf-8')
        if parsed.path.startswith('/assets/') and WEB_DIST.exists():
            rel = parsed.path.lstrip('/')
            target = (WEB_DIST / rel).resolve()
            # 防止路径穿越
            if WEB_DIST.resolve() in target.parents and target.is_file():
                return self._send_file(target)
        if parsed.path in ('/', '/index.html'):
            return self._send(200, PAGE, 'text/html; charset=utf-8')
        if parsed.path == '/api/ai/test':
            qs = parse_qs(parsed.query)
            text = (qs.get('text') or ['不好'])[0]
            feed = (qs.get('feed') or ['大家好'])[0]
            author = (qs.get('author') or ['小明'])[0]
            cfg = watcher_config.load()
            try:
                ok, out = ai_reply.generate(cfg, text, feed, author)
            except Exception as exc:  # noqa: BLE001
                ok, out = False, f'{exc.__class__.__name__}: {exc}'
            return self._send(200, json.dumps({'ok': ok, 'text': out,
                                               'model': cfg.get('ai_model')}, ensure_ascii=False))
        if parsed.path == '/api/config':
            cfg = watcher_config.load()
            return self._send(200, json.dumps({'ok': True, 'config': cfg,
                                               'rule': watcher_config.describe(cfg)}, ensure_ascii=False))
        if parsed.path == '/api/window':
            qs = parse_qs(parsed.query)
            circle = (qs.get('circle') or [DEFAULTS['circle']])[0]
            days = min(int((qs.get('days') or [DEFAULTS['days']])[0]), 60)
            key = f'{circle}:{days}'
            with LOCK:
                if CACHE['key'] == key and time.time() - CACHE['at'] < 180:
                    payload = dict(CACHE['data'])
                else:
                    try:
                        max_pages = min(int((qs.get('pages') or ['5'])[0]), 20)
                        feeds, info = READER.circle_feeds_since(circle, days=days, count=20, max_pages=max_pages)
                    except Exception as exc:  # noqa: BLE001
                        return self._send(200, json.dumps({'ok': False, 'error': f'{exc.__class__.__name__}: {exc}'}, ensure_ascii=False))
                    if not info.get('ok'):
                        return self._send(200, json.dumps({'ok': False, 'error': str(info)[:200]}, ensure_ascii=False))
                    payload = {'ok': True, 'circle': circle, 'days': days, 'feeds': feeds,
                               'info': {'totalCount': info.get('totalCount'), 'pages': info.get('pages')}}
                    CACHE.update({'key': key, 'at': time.time(), 'data': payload})
            trig, cmts = load_triggered()
            payload = dict(payload)
            payload['triggered'] = trig
            payload['triggeredComments'] = cmts
            return self._send(200, json.dumps(payload, ensure_ascii=False))
        return self._send(404, 'not found', 'text/plain; charset=utf-8')


class QuietServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        import sys as _sys
        exc = _sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, TimeoutError)):
            return          # 客户端断开，不打印
        super().handle_error(request, client_address)


def main():
    global READER
    ap = argparse.ArgumentParser()
    ap.add_argument('--host', default='127.0.0.1', help='监听地址，0.0.0.0 表示对外')
    ap.add_argument('--port', type=int, default=8790)
    ap.add_argument('--circle', default=DEFAULTS['circle'])
    ap.add_argument('--days', type=int, default=DEFAULTS['days'])
    ap.add_argument('--open', action='store_true')
    args = ap.parse_args()
    DEFAULTS['circle'] = args.circle
    DEFAULTS['days'] = args.days
    READER = FeedReader()
    url = f'http://127.0.0.1:{args.port}'
    print(f'曝光触发监控：{url}   （Ctrl+C 停止）')
    import webbrowser
    if args.open:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    QuietServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
