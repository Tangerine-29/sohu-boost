# 排错手册

按症状查。每条给出：**现象 → 原因 → 处理**。

---

## 一、认证类

### 40110 登录失败，请重新登录

**原因**：token 失效。

App 每次活跃都会换发新 token，旧 token 立即作废。

**处理**：

1. 手机上**退出该账号的登录**（让 token 不再刷新）
2. 重新抓一次 `session_sample.json`（见 [GETTING-STARTED](GETTING-STARTED.md)）
3. 验证：

```bash
python3 -c "
from feed_reader import FeedReader
f = FeedReader().feed('<帖子ID>')
print(f.get('ok'), f.get('content'))
"
```

内容有值才说明好了。

---

### 320002 账户因违规已被狐友封禁

**原因**：账号被封。

**处理**：

看你要做什么：

| 还想做的事 | 可行性 |
|---|---|
| 刷曝光 | ✅ 实测仍计数 |
| 读帖子/评论 | ❌ 接口返回空 |
| 发评论/回复 | ❌ 直接拒绝 |

**换号流程**（已验证）：

```bash
# 1. 手机上退出被封账号
# 2. 用新手机号注册（可能需要先改设备标识，见下文）
# 3. 抓新号 token
# 4. 覆盖 session_sample.json
```

如果是**设备级封禁**（同设备换号注册也封），需要先改设备标识：

- iOS：Keychain 里的 `cidKey`（S-CID）和 `idfvKey`（IDFV）
- 改写后重启 App，再注册新号

（这部分不在本项目范围内，属于设备层面的操作）

---

### 400001 n:sig check fail!

**原因**：签名校验失败。**九成不是签名算法错**。

按概率排查：

| 排查项 | 怎么查 |
|---|---|
| **`key_jegb` 缺失或错** | 它在**请求体**里，64 字符，不在请求头 |
| **多线程共享 nonce** | 每次请求必须用局部 headers 副本 |
| **请求过于密集** | 加间隔：`feed_reader.set_min_gap(1.5)` |
| **`S-PID` / `S-PPID` 不匹配** | 两者必须属于同一账号 |
| **参数里混入了不该有的** | 如 `users/update` 不要带 `extras` |

**快速定位**：

```bash
# 单线程、单请求，看是否还失败
python3 -c "
import sys; sys.path.insert(0,'.')
from feed_reader import FeedReader
f = FeedReader().feed('<帖子ID>')
print(f.get('ok'), str(f)[:200])
"
```

单请求成功 → 是并发问题；仍失败 → 是参数/凭证问题。

---

## 二、接口类

### 200003 + desc 列出字段名

**这不是错误，是提示**。

```json
{"status": 200003, "desc": "score,list_type,tpl,stpl"}
```

`desc` 直接告诉缺哪些参数。补齐即可，**不用抓包**。

---

### 接口返回 200 但内容为 None

**原因**：token 已失效但服务端不报错，只返回空数据。

判断方法：看 `exposureCount`、`commentCount` 是不是也是 `None`。是 → token 问题。

---

### 列表返回 0 条

**原因**：可能是 `list_type` 用错。

| list_type | 行为 |
|---|---|
| 1 | 按热度，时间不连续 |
| **2** | **按时间倒序**（拉窗口数据必须用这个）|
| 3 | 返回空 |

---

### 评论列表拿到 3 条但 totalCount 是 5

**原因**：子回复不计入顶层列表。

顶层 `comment/list` 只返回顶层评论，子回复要用 `replylist` 查。

---

## 三、功能类

### 给帖子发不出评论

**检查顺序**：

1. **帖子是否有 0 条评论** → 早期版本会跳过一次请求，现在已修（`reply_all_feeds` 开启时不跳过）
2. **小时额度是否用完**（`feed_reply_hourly_cap`，默认 10）
3. **帖子是否在时间窗口内**（`feed_reply_only_after_start`）
4. **是否已标记过**（`__feed_marks__`，每帖只发一条）

查状态：

```bash
python3 -c "
import sys; sys.path.insert(0,'.')
from comment_watcher import Watcher
w = Watcher(dry_run=True); w.reload_config()
FID='<帖子ID>'
print('已标记:', w.feed_replied(FID))
print('本小时已发:', w.hourly_feed_replies(), '/', w.cfg['feed_reply_hourly_cap'])
print('启动时刻:', __import__('time').strftime('%H:%M:%S', __import__('time').localtime(w.started_at())))
"
```

---

### 评论回复没触发

**检查顺序**：

1. 评论时间是否 >= 启动时刻（`reply_grace_minutes`，默认 0 = 严格）
2. 是否在窗口内（`reply_window_days`，默认 2 天）
3. 是否已处理过（`watcher_state.json` 里的记录）
4. `ai_reply_mode` 是否允许（`all` 才回普通评论）

---

### 刷了曝光但数字没变

**三个检查点**：

1. **等 30~100 秒**（服务端批量落账）
2. **直接读**，别用列表接口（有缓存）：

```bash
python3 -c "
from boost_protocol import Session
s = Session('session_sample.json')
print(s.read_count('<帖子ID>'))
"
```

3. **封号后读接口全废**，只能用另一台设备或 H5 页面确认

---

### AI 回复只输出一两个字

**原因**：`max_tokens` 太小，被思考链吃掉。

某些模型（flash 系列）响应里有 `reasoning_content`（思考链），会消耗 token。

**处理**：

```json
{"ai_max_len": 20}
```

`ai_reply.py` 里 `max_tokens` 固定 400，够用。如果还不够，改代码里的值。

---

### AI 报 403 error code 1010

**原因**：Cloudflare 拦了 Python 默认 UA。

**处理**：`ai_reply.py` 已伪装 Chrome UA，如果你改过代码，检查这里：

```python
'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ...'
```

---

### AI 返回的是"用户要我..."这种旁白

**原因**：模型把思考过程写进了 `content`。

**处理**：代码里有 `looks_like_reasoning()` 检测，命中会重试。如果频繁出现：

1. 换模型（`glm` 系列比 `flash` 系列稳）
2. 或加强提示词里"只输出你要说的那一句话"这条约束

---

## 四、部署类

### 面板一直显示"读取中"

**原因**：后端要翻 5 页（每页限速 1.5 秒），首次约 9 秒。

**处理**：

- 等着就行（前端有秒数计时）
- 或者调小 `list_page_delay`

---

### 日志刷屏 BrokenPipeError

**原因**：浏览器刷新/切页时断开连接，服务器还在写响应。

**处理**：`web_watcher.py` 已捕获并静默这类异常。如果还刷屏，说明你的版本旧，更新即可。

---

### 日志 6 分钟不动

**原因**：进程卡死（活着但不干活）。

**处理**：`guard.sh` 会检测到并重启。手动处理：

```bash
pkill -f comment_watcher.py
cd /www/wwwroot/sohu-boost
nohup python3 comment_watcher.py --circle <圈子ID> --days 7 --interval 180 >> watcher.log 2>&1 &
```

---

### 连续出现多个"监听启动"

**原因**：`install.sh` 被执行了多次，或 crontab 守护在反复拉起。

**处理**：

```bash
# 先确认是不是真的在反复重启
grep -c "监听启动" watcher.log

# 停掉所有守护，手动跑一次观察
bash install.sh --stop
pkill -f comment_watcher.py
sleep 1
nohup python3 comment_watcher.py --circle <圈子ID> --interval 180 >> watcher.log 2>&1 &
sleep 30 && tail -5 watcher.log
```

如果手动跑正常，说明守护脚本的 `pgrep` 判断有问题。

---

## 五、数据类

### 已处理记录突然清零

**原因**：`watcher_state.json` 被删或损坏。

**影响**：所有历史评论会被重新处理一遍。

**处理**：正常情况下 `install.sh` 不会删它，检查是不是手动执行了 `rm` 或 `--reset`。

---

### 想重发某个帖子的评论

```bash
python3 -c "
import json
p='watcher_state.json'
d=json.load(open(p))
d.get('__feed_marks__',{}).pop('<帖子ID>', None)
json.dump(d, open(p,'w'), ensure_ascii=False, indent=1)
print('已清除该帖的标记')
"
```

下一轮会重新发一条。

---

### 想重置启动时刻（让窗口从现在开始算）

```bash
python3 -c "
import json, time
p='watcher_state.json'
d=json.load(open(p))
d['__meta__'] = {'started_at': int(time.time()), 'at': time.strftime('%H:%M:%S')}
json.dump(d, open(p,'w'), ensure_ascii=False, indent=1)
print('已重置，历史去重记录保留')
"
```

---

## 六、实在搞不定

收集这些信息再问：

```bash
cd /www/wwwroot/sohu-boost

# 1. 版本与环境
python3 --version
ls -la

# 2. 自检结果
bash check.sh

# 3. 最近日志
tail -30 watcher.log

# 4. 复现命令 + 输出
```

**提问时把 token、用户 ID、API key 全部打码。**
