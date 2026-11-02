#!/bin/bash
# 一键部署监听器：启动 + 守护 + 自检
# 用法：
#   bash install.sh            正常启动（保留已有去重记录）
#   bash install.sh --reset    清空去重记录后启动
#   bash install.sh --stop     停止监听器并移除守护
#   CIRCLE=xxx INTERVAL=10 bash install.sh    自定义圈子/间隔

set -u
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

CIRCLE="${CIRCLE:-<CIRCLE_ID>}"
DAYS="${DAYS:-7}"
INTERVAL="${INTERVAL:-180}"
PY="${PY:-python3}"
LOG="$DIR/watcher.log"
GUARD="$DIR/guard.sh"

info() { printf '\033[32m[OK]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[!!]\033[0m %s\n' "$*"; }
die()  { printf '\033[31m[XX]\033[0m %s\n' "$*"; exit 1; }

stop_it() {
  pkill -f "comment_watcher.py" 2>/dev/null && info "已停止运行中的监听器" || warn "没有在跑的监听器"
  if crontab -l 2>/dev/null | grep -q "$GUARD"; then
    crontab -l 2>/dev/null | grep -v "$GUARD" | crontab -
    info "已移除 crontab 守护"
  fi
}

if [ "${1:-}" = "--stop" ]; then
  stop_it
  exit 0
fi

# ---------- 前置检查 ----------
command -v "$PY" >/dev/null 2>&1 || die "找不到 $PY"
for f in comment_watcher.py feed_reader.py boost_protocol.py sign.py payload.py session_sample.json; do
  [ -f "$DIR/$f" ] || die "缺少文件 $f，请在解压后的项目目录里执行"
done
chmod 600 "$DIR/session_sample.json" 2>/dev/null || true

# ---------- 语法检查 ----------
"$PY" -m py_compile comment_watcher.py feed_reader.py boost_protocol.py sign.py payload.py 2>/dev/null \
  || die "Python 语法检查失败，手动执行：$PY -m py_compile comment_watcher.py"
info "语法检查通过"

# ---------- 接口自检 ----------
cat > "$DIR/_selftest.py" <<'PYEOF'
import sys
sys.path.insert(0, '.')
try:
    from feed_reader import FeedReader
    r = FeedReader()
    feeds, info = r.circle_feeds_since('<CIRCLE_ID>', days=7, count=20, max_pages=1, list_type='2')
    if not info.get('ok'):
        print('FAIL ' + str(info)[:120])
    else:
        print('OK feeds=%d total=%s' % (len(feeds), info.get('totalCount')))
except Exception as exc:
    print('FAIL %s: %s' % (type(exc).__name__, exc))
PYEOF
SELFTEST="$("$PY" "$DIR/_selftest.py" 2>&1 | tail -1)"
rm -f "$DIR/_selftest.py"
case "$SELFTEST" in
  OK*) info "接口自检通过（${SELFTEST}）" ;;
  *)   warn "接口自检未通过：${SELFTEST}（仍会启动，请留意日志）" ;;
esac

# ---------- 清空去重记录 ----------
if [ "${1:-}" = "--reset" ]; then
  rm -f "$DIR/watcher_state.json"
  info "已清空 watcher_state.json"
fi

# ---------- 停旧进程 ----------
pkill -f "comment_watcher.py" 2>/dev/null && sleep 1 && info "已停止旧进程" || true

# ---------- 生成守护脚本（含心跳检测）----------
cat > "$GUARD" <<'GUARDEOF'
#!/bin/bash
# 由 install.sh 生成：进程守护 + 心跳检测
DIR="__DIR__"
LOG="__LOG__"
PY="__PY__"
ARGS="comment_watcher.py --circle __CIRCLE__ --days __DAYS__ --interval __INTERVAL__"

cd "$DIR" || exit 1

is_running() { pgrep -f "comment_watcher.py --circle" > /dev/null; }

# 1) 日志 6 分钟没更新 → 判定卡死，杀掉重来
if [ -f "$LOG" ] && is_running; then
  AGE=$(( $(date +%s) - $(stat -c %Y "$LOG" 2>/dev/null || echo 0) ))
  if [ "$AGE" -gt 360 ]; then
    echo "[$(date '+%F %T')] [GUARD] 日志 ${AGE}s 未更新，判定卡死，重启" >> "$LOG"
    pkill -f "comment_watcher.py --circle"
    sleep 2
  fi
fi

# 2) 没在跑就拉起来
if ! is_running; then
  echo "[$(date '+%F %T')] [GUARD] 进程不在，启动" >> "$LOG"
  nohup "$PY" $ARGS >> "$LOG" 2>&1 &
  sleep 2
fi

# 3) 记录存活
is_running && echo "[$(date '+%F %T')] [GUARD] alive pid=$(pgrep -f 'comment_watcher.py --circle' | head -1)" >> "$DIR/guard_status.log"
exit 0
GUARDEOF

python3 - "$GUARD" "$DIR" "$LOG" "$PY" "$CIRCLE" "$DAYS" "$INTERVAL" <<'PYEOF2'
import sys, pathlib
path, d, log, py, circle, days, interval = sys.argv[1:8]
f = pathlib.Path(path)
t = f.read_text()
t = t.replace('__DIR__', d).replace('__LOG__', log).replace('__PY__', py)
t = t.replace('__CIRCLE__', circle).replace('__DAYS__', days).replace('__INTERVAL__', interval)
f.write_text(t)
PYEOF2
chmod +x "$GUARD"
info "守护脚本：${GUARD}（含心跳检测，日志 6 分钟不动会重启）"

# ---------- 启动监听器 ----------
nohup "$PY" comment_watcher.py --circle "$CIRCLE" --days "$DAYS" --interval "$INTERVAL" >> "$LOG" 2>&1 &
sleep 3

if pgrep -f "comment_watcher.py" > /dev/null; then
  PID="$(pgrep -f comment_watcher.py | head -1)"
  info "监听器已启动 pid=${PID}（圈子 ${CIRCLE} / 窗口 ${DAYS} 天 / 间隔 ${INTERVAL}s）"
else
  die "启动失败，查看日志：tail -30 ${LOG}"
fi

# ---------- 启动简介更新器（每 10 分钟）----------
pkill -f "profile_updater.py" 2>/dev/null || true
nohup "$PY" profile_updater.py --interval 10800 >> "$DIR/profile.log" 2>&1 &
sleep 2
if pgrep -f "profile_updater.py" > /dev/null; then
  info "简介更新器已启动（每 3 小时刷新 Token 消耗）"
else
  warn "简介更新器未启动，查看 $DIR/profile.log"
fi

# ---------- crontab 守护 ----------
CRON_LINE="*/2 * * * * /bin/bash $GUARD >/dev/null 2>&1"
if command -v crontab >/dev/null 2>&1; then
  ( crontab -l 2>/dev/null | grep -v "$GUARD" ; echo "$CRON_LINE" ) | crontab - 2>/dev/null \
    && info "已加入 crontab 守护（每 2 分钟检查）" \
    || warn "crontab 写入失败，手动加入：${CRON_LINE}"
else
  warn "系统没有 crontab，请用宝塔计划任务守护 ${GUARD}"
fi

# ---------- 面板 ----------
if command -v ss >/dev/null 2>&1 && ss -lnt 2>/dev/null | grep -q ':8790 '; then
  info "面板已在监听 8790（跳过启动）"
else
  nohup "$PY" web_watcher.py --host 0.0.0.0 --port 8790 >> "$DIR/web_watcher.log" 2>&1 &
  sleep 2
  if ss -lnt 2>/dev/null | grep -q ':8790 '; then
    info "面板已启动：http://<服务器IP>:8790"
  else
    warn "面板未起来，查看 ${DIR}/web_watcher.log"
  fi
fi

echo
echo "──────────── 状态 ────────────"
echo "进程:  $(pgrep -f comment_watcher.py | tr '\n' ' ')"
echo "日志:  tail -f ${LOG}"
echo "停止:  bash install.sh --stop"
echo "重置:  bash install.sh --reset"
echo "配置:  ${PY} watcher_config.py --show"
echo "──────────────────────────────"
tail -3 "$LOG" 2>/dev/null
