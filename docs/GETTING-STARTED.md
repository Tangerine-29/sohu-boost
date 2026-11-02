# 从零开始：拿到 token 并跑起来

这份文档假设你**完全没接触过抓包**，一步步走到能执行第一条命令。

预计耗时：20~30 分钟。

---

## 目录

- [第 0 步：确认你要什么](#第-0-步确认你要什么)
- [第 1 步：准备环境](#第-1-步准备环境)
- [第 2 步：抓包拿 token（三种方式）](#第-2-步抓包拿-token三种方式)
- [第 3 步：拼出 session_sample.json](#第-3-步拼出-session_samplejson)
- [第 4 步：验证](#第-4-步验证)
- [第 5 步：跑起来](#第-5-步跑起来)
- [常见问题](#常见问题)

---

## 第 0 步：确认你要什么

这个项目需要一份 **`session_sample.json`**，本质是「一次成功请求的完整快照」，包含：

| 必须有的 | 从哪来 |
|---|---|
| `token` | 请求头 |
| `S-CID`（设备 ID）| 请求头 |
| `S-PID`（用户数字 ID）| 请求头 |
| `S-PPID`（passport）| 请求头 |
| `key_jegb` | 请求体 |
| `s-nonce` | 请求头 |

**只要抓到任意一个 `cs-ol.sns.sohu.com` 的请求**，这些字段全都有。

---

## 第 1 步：准备环境

### 需要的东西

| 项 | 说明 |
|---|---|
| 一台电脑 | macOS / Windows / Linux 都行 |
| 手机 | 已登录目标账号的狐友 App |
| 同一个 WiFi | 手机和电脑连同一个网络 |
| Python 3.8+ | `python3 --version` 确认 |

### 电脑上装工具（选一种）

**方式 A：mitmproxy（命令行，推荐）**

```bash
# macOS
brew install mitmproxy

# 或者用 pip
pip3 install mitmproxy
```

**方式 B：Charles（图形界面，付费但好用）**

官网下载：https://www.charlesproxy.com/

**方式 C：手机端 App（最省事）**

App Store 搜 **Stream**（免费）或 **Thor**（付费），直接在手机上抓，不需要电脑。

---

## 第 2 步：抓包拿 token（三种方式）

### 方式 A：mitmproxy（推荐）

**1. 电脑上启动**

```bash
mitmproxy --listen-port 8080
```

记下电脑的局域网 IP：

```bash
# macOS
ipconfig getifaddr en0
# 假设输出 192.168.1.100
```

**2. 手机设置代理**

- iPhone：设置 → 无线局域网 → 点当前 WiFi 的 ⓘ → 配置代理 → 手动
  - 服务器：`192.168.1.100`
  - 端口：`8080`
- Android：设置 → WLAN → 长按当前网络 → 修改网络 → 高级 → 代理 → 手动

**3. 手机装证书**

手机浏览器打开 `http://mitm.it`，选对应系统的证书下载并安装。

- **iPhone 还要额外一步**：设置 → 通用 → 关于本机 → 证书信任设置 → 打开 mitmproxy 的开关

**4. 打开狐友 App，刷一下首页**

mitmproxy 窗口会刷出请求。

**5. 找到目标请求**

在 mitmproxy 里按 `/` 搜索 `cs-ol.sns.sohu.com`，回车定位。

推荐抓这几个之一（都能拿到全部字段）：

```
POST  cs-ol.sns.sohu.com/330000/v7/feeds/show
GET   cs-ol.sns.sohu.com/330000/v8/comment/list
POST  cs-ol.sns.sohu.com/330000/v8/circle/feed/list
```

**6. 导出为文件**

选中该请求 → 按 `e` → 选 `raw` → 保存成 `request.txt`。

或者按 `w` 保存 body。

---

### 方式 B：Charles

**1. 启动 Charles**，菜单 Proxy → Proxy Settings，确认端口 `8888`

**2. 手机设代理**：同上，端口改成 `8888`

**3. 手机装证书**：浏览器打开 `chls.pro/ssl`

**4. 打开狐友，刷一下**

**5. Charles 里搜 `cs-ol`**，右键目标请求 → **Export Session** 或 **Copy cURL Request**

拿到 cURL 后可以转成 Python 请求，字段都在里面。

---

### 方式 C：手机端 Stream（不需要电脑）

**1. App Store 装 Stream**

**2. 打开 Stream → 开始抓包**

**3. 切到狐友 App，刷一下首页**

**4. 回 Stream，找到 `cs-ol.sns.sohu.com` 的请求**

**5. 点开 → 看「请求头」和「请求体」**

把这两部分抄下来（或截图后对着填）。

---

## 第 3 步：拼出 session_sample.json

拿到请求后，按下面的模板填。

### 模板

```json
{
  "event": "dump",
  "at": 1793589975846,
  "url": "https://cs-ol.sns.sohu.com/330000/v7/feeds/show",
  "method": "POST",
  "body": "app_key_vs=6.24.1&appid=330000&extras=1&feed_id=任意帖子ID&flyer=任意毫秒时间戳&key_jegb=从请求体复制&log_user_id=从请求体复制",
  "headers": {
    "S-CID": "从请求头复制",
    "S-PID": "从请求头复制",
    "S-PPID": "从请求头复制",
    "S-VS": "6.24.1",
    "S-DV": "iPhone15,2",
    "S-OS": "iOS 16.0.3",
    "S-TO": "中国移动",
    "P-APPID": "110501",
    "appid": "330000",
    "gid": "从请求头复制",
    "s-nonce": "随便填，每次请求会重新生成",
    "token": "从请求头复制",
    "User-Agent": "sohuhy/6.24.1 (com.sohu.sohuhy; build:170; iOS 16.0.3) Alamofire/5.9.0",
    "Content-Type": "application/x-www-form-urlencoded; charset=utf-8"
  },
  "cookie": null
}
```

### 字段从哪复制（对照表）

在抓到的那条请求里找：

| JSON 字段 | 请求里的位置 | 长什么样 |
|---|---|---|
| `headers.token` | **请求头** `token` | `eyJleHAiOjE3...`（JWT，200+ 字符）|
| `headers.S-CID` | **请求头** `S-CID` | `01` + 19 位数字（共 21 位）|
| `headers.S-PID` | **请求头** `S-PID` | `<你的用户ID>`（19 位数字）|
| `headers.S-PPID` | **请求头** `S-PPID` | `2117080695704129536@sohu.com` |
| `headers.gid` | **请求头** `gid` | `x011050110101d603c...`（44 字符）|
| `body` 里的 `key_jegb` | **请求体** `key_jegb=` | `RYSVnOko92PS354y43XH2qza...`（64 字符）|
| `body` 里的 `log_user_id` | **请求体** `log_user_id=` | 与 `S-PID` **相同** |

### 三个容易踩的坑

**1. `key_jegb` 一定要有**

它是 64 字符的设备级密钥，**没有它签名永远失败**。在请求体里，不在请求头。

**2. `S-TO` 可以是任意值**

它是运营商（`中国移动`/`中国联通`），不参与签名，随便填。

但注意：**带中文的 header 会让 Python 报编码错**。代码里已经过滤了非 ASCII 的 header，所以留着也没事。

**3. `s-nonce` 随便填**

代码每次请求都会重新生成，模板里的值会被覆盖。

---

## 第 4 步：验证

把 `session_sample.json` 放到项目目录，跑：

```bash
python3 -c "
import sys; sys.path.insert(0, '.')
from feed_reader import FeedReader

r = FeedReader('session_sample.json')
print('身份:', r.s.user_id, '|', r.s.passport)

f = r.feed('<随便一个帖子ID>')
print('读帖子:', f.get('ok'))
print('  内容:', f.get('content'))
print('  曝光:', f['counts']['exposure'], '评论:', f['counts']['comment'])
"
```

### 结果对照

| 输出 | 说明 |
|---|---|
| `内容: 'xxx'` + 曝光数字 | ✅ 全对 |
| `内容: None`，`ok=True` | ⚠️ token 失效（`40110`）|
| `Error: 40110` | ⚠️ token 失效 |
| `Error: 320002` | ❌ 账号被封 |
| `Error: 400001 sig check fail` | ❌ 签名错，检查 `key_jegb` 和 `S-PID`/`S-PPID` |

---

## 第 5 步：跑起来

验证通过后：

```bash
# 1. 刷曝光（300 曝光 = 150 条）
python3 -c "
import sys, time; sys.path.insert(0, '.')
from boost_protocol import Session
s = Session('session_sample.json')
codes = [s.report_once('<帖子ID>', int(time.time()*1000)+i) for i in range(150)]
print(sum(1 for c in codes if c==200), '/150 成功')
"

# 2. 读评论
python3 feed_reader.py --feed <帖子ID>

# 3. 监听圈子（命中 <exposure:N> 自动刷量）
python3 comment_watcher.py --circle <圈子ID> --days 7 --interval 180
```

---

## 常见问题

### Q: token 能用多久？

`token` 是 JWT，`exp` 通常在 400 天后。**但 App 每次活跃都会换发新 token，旧 token 立即作废。**

所以：
- 手机上**退出该账号的登录** → token 长期有效
- 手机上继续用 → 服务器上这份很快失效

### Q: 抓不到 `cs-ol` 的请求？

1. 确认手机上 App 真的刷新了（下拉首页）
2. 确认证书已信任（iPhone 还要在「证书信任设置」里打开）
3. 有些 App 会做 SSL Pinning，但狐友实测**没做**（mitmproxy 能正常抓）

### Q: 抓到了但字段不全？

换一个接口抓。推荐这三个（字段全）：

```
POST /330000/v7/feeds/show          ← 最好抓，App 一进帖子就有
GET  /330000/v8/comment/list
GET  /330000/v8/circle/feed/list
```

### Q: 手机设代理后 App 打不开？

- 检查电脑防火墙是否拦了 8080
- 或者先关代理，抓包时再开

### Q: 用 Stream 抓的，怎么转成 json？

Stream 里点开请求，把「请求头」全部抄下来，请求体一行抄下来，按上面模板填。7 个字段，两分钟就能填完。

### Q: 能不能不问账号、直接跑？

不能。所有接口都需要 `token` 和 `S-CID`，这是身份凭证，没有替代方案。

---

## 安全提醒

`session_sample.json` 里的 `token` **等价于账号密码**。

- 不要提交到 git（`.gitignore` 已排除）
- 不要发给别人
- 截图时打码
- 服务器上 `chmod 600 session_sample.json`
