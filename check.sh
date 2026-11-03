#!/bin/bash
# 一键自检：确认监听器、双账号、限速、接口、面板是否都正常
# 用法：bash check.sh [帖子ID]

set -u
cd "$(dirname "$0")" || exit 1
PY="${PY:-python3}"
FID="${1:-FEED_ID_HERE}"

ok()   { printf '\033[32m[OK]\033[0m %s\n' "$*"; }
bad()  { printf '\033[31m[XX]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[!!]\033[0m %s\n' "$*"; }
hr()   { printf '\n──────── %s ────────\n' "$*"; }

hr "1. 进程"
if pgrep -f "comment_watcher.py" > /dev/null; then
  PID=$(pgrep -f comment_watcher.py | head -1)
  ok "监听器在跑 pid=$PID"
  ps -p "$PID" -o etime= 2>/dev/null | sed 's/^/       已运行 /'
else
  bad "监听器没在跑 —— 执行 bash install.sh"
fi
if pgrep -f "web_watcher.py" > /dev/null; then
  ok "面板在跑 pid=$(pgrep -f web_watcher.py | head -1)"
elif ss -lnt 2>/dev/null | grep -q ':8790 '; then
  ok "8790 端口有服务（由宝塔管理的面板）"
else
  warn "面板没在跑（不影响刷量/回复）"
fi

hr "2. 双账号分工"
$PY - <<'PYEOF'
import sys
sys.path.insert(0, '.')
try:
    from boost_protocol import Session
    b = Session('session_boost.json')
    r = Session('session_sample.json')
    print(f'  刷量号: {b.user_id}  {b.passport}')
    print(f'  回复号: {r.user_id}  {r.passport}')
    if b.user_id and r.user_id and b.user_id != r.user_id:
        print('  \033[32m[OK]\033[0m 两个号已分离')
    else:
        print('  \033[31m[XX]\033[0m 两个号相同或缺失')
except Exception as e:
    print(f'  \033[31m[XX]\033[0m {type(e).__name__}: {e}')
PYEOF

hr "3. 关键配置"
$PY - <<'PYEOF'
import sys
sys.path.insert(0, '.')
try:
    import watcher_config
    c = watcher_config.load()
    keys = ['ai_reply_mode', 'feed_mention_reply', 'mention_keywords',
            'one_reply_per_feed', 'max_exposure', 'daily_cap_per_feed',
            'boost_workers', 'boost_batch_delay', 'boost_min_interval',
            'list_page_delay', 'reply_window_days', 'ai_model']
    for k in keys:
        print(f'  {k:<22} {c.get(k)}')
except Exception as e:
    print(f'  \033[31m[XX]\033[0m {e}')
PYEOF

hr "4. 日志（最近 8 行）"
if [ -f watcher.log ]; then
  tail -8 watcher.log
  LAST=$(stat -c %Y watcher.log 2>/dev/null || echo 0)
  AGE=$(( $(date +%s) - LAST ))
  if [ "$AGE" -gt 400 ]; then
    warn "日志 ${AGE}s 没更新（轮询 180s + 单轮 ~12s，超过 400s 就不正常）"
  else
    ok "日志 ${AGE}s 前有更新"
  fi
else
  bad "watcher.log 不存在 —— 监听器可能从未启动"
fi

hr "5. 接口连通（回复号读帖子）"
$PY - "$FID" <<'PYEOF'
import sys
sys.path.insert(0, '.')
fid = sys.argv[1] if len(sys.argv) > 1 else 'FEED_ID_HERE'
try:
    from feed_reader import FeedReader
    r = FeedReader()
    f = r.feed(fid)
    if f.get('ok') and f.get('content'):
        print(f'  \033[32m[OK]\033[0m 内容={str(f.get("content"))[:30]!r}')
        print(f'       曝光={f["counts"].get("exposure")} 评论={f["counts"].get("comment")}')
    elif f.get('ok'):
        print(f'  \033[31m[XX]\033[0m 接口返回 ok 但内容为空 —— token 可能失效（40110/320002）')
    else:
        print(f'  \033[31m[XX]\033[0m 读取失败: {str(f)[:120]}')
    cs, pi = r.comments(fid, count=5, max_pages=1)
    print(f'       评论: totalCount={pi.get("totalCount")} 拿到={len(cs)}')
except Exception as e:
    print(f'  \033[31m[XX]\033[0m {type(e).__name__}: {e}')
PYEOF

hr "6. 刷量号能否发送"
$PY - <<'PYEOF'
import sys, time
sys.path.insert(0, '.')
try:
    from boost_protocol import Session
    s = Session('session_boost.json')
    codes = [s.report_once('FEED_ID_HERE', int(time.time()*1000)+i) for i in range(3)]
    okn = sum(1 for c in codes if c == 200)
    print(f'  发送 3 条: {okn}/3 成功  返回码 {set(codes)}')
    print('  \033[32m[OK]\033[0m 刷量通道正常' if okn == 3 else '  \033[33m[!!]\033[0m 部分失败，可能被限流')
except Exception as e:
    print(f'  \033[31m[XX]\033[0m {type(e).__name__}: {e}')
PYEOF

hr "7. 面板接口"
if curl -sS -m 5 http://127.0.0.1:8790/api/config 2>/dev/null | head -c 80 | grep -q '"ok": true'; then
  ok "面板 /api/config 正常"
else
  warn "面板未响应（不影响后台任务）"
fi

hr "8. 去重与标记文件"
if [ -f watcher_state.json ]; then
  $PY - <<'PYEOF'
import json
try:
    d = json.load(open('watcher_state.json'))
    meta = d.get('__meta__') or {}
    marks = d.get('__feed_marks__') or {}
    done = [k for k in d if not str(k).startswith('__')]
    print(f'  已处理评论: {len(done)} 条')
    print(f'  顶层评论标记: {len(marks)} 个帖子')
    print(f'  启动时刻: {meta.get("started_at")} ({meta.get("at","")})')
except Exception as e:
    print(f'  \033[31m[XX]\033[0m 解析失败: {e}')
PYEOF
else
  warn "watcher_state.json 不存在（首次运行会重新记录启动时刻）"
fi

printf '\n'
