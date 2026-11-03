# 狐友（狐友校园社区）协议研究工具

[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/dependencies-zero-brightgreen.svg)](requirements.txt)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey.svg)](#)

> 某校园社区 App 的**协议层**分析与自动化工具集。纯 Python 实现，无需越狱设备运行。
>
> ⚠️ 本项目仅用于**协议研究、安全教学与自有账号的接口测试**。请勿用于他人账号、批量刷量或任何违反服务条款的场景。使用前请确认你拥有目标账号的完全控制权。

---

## 目录

- [能做什么](#能做什么)
- [核心研究点](#核心研究点)
  - [1. 接口签名算法](#1-接口签名算法)
  - [2. s-nonce 生成](#2-s-nonce-生成)
  - [3. 曝光埋点协议](#3-曝光埋点协议)
  - [4. 评论接口的三个形态](#4-评论接口的三个形态)
  - [5. 列表排序参数](#5-列表排序参数)
- [快速开始](#快速开始)
- [文件说明](#文件说明)
- [测试](#测试)
- [文档](#文档)
- [一些实测数据](#一些实测数据)
- [FAQ](#faq)
- [已知限制](#已知限制)
- [License](#license)

---

## 能做什么

| 能力 | 说明 | 接口 |
|---|---|---|
| **读帖子 / 评论 / 圈子** | 拉取帖子详情、评论列表（含楼中楼）、圈子时间线 | `v7/feeds/show`、`v8/comment/list`、`v8/circle/feed/list` |
| **刷曝光** | 构造曝光埋点上报，每条约 +2 曝光 | `openapi/pingback/log/report` |
| **发 / 删评论** | 顶层评论、楼中楼回复、删除 | `v8/comment/text`、`v6/feeds/comment/remove` |
| **转发** | 转发帖子 | `v6/feeds/repost` |
| **改简介** | 修改个人签名 | `v5/users/update` |
| **私聊** | 拉会话、读消息、发消息、AI 自动回复 | `dm/api/v2/message`、`dm/api/v3/message` |
| **自动监听** | 监控圈子，命中暗号自动刷量 + AI 回复 | 组合上述 |
| **知识库** | 一行一句话，全量注入 AI prompt，避免它乱编学校信息 | — |
| **监控面板** | Three.js 三维背景 + 玻璃拟态 UI（Vite + TypeScript）| `http.server` |

---

## 核心研究点

### 1. 接口签名算法

所有请求都带 `sig` 参数，算法：

```
sig = MD5( "".join(f"{k}={v}" for k in sorted(params + 签名字段)) + KEY_MATERIAL )
```

签名字段是 5 个 header：

```
S-CID  S-PID  S-PPID  S-VS  s-nonce
```

`KEY_MATERIAL` 是 16 字节固定串，从二进制中恢复。

实现见 [`sign.py`](sign.py)。

### 2. s-nonce 生成

```
s-nonce = base64url( 8字节大端毫秒时间戳 + 40字节安全随机数 )   # 去掉尾部 '='
```

服务端有时效校验，**每次请求必须新生成**。

实现见 [`boost_protocol.py`](boost_protocol.py) 的 `gen_nonce()`。

### 3. 曝光埋点协议

曝光不是直接"加数字"，而是客户端上报 `P_FEED_DETAIL` 事件：

```
POST https://opapi-ol.sns.sohu.com/openapi/pingback/log/report
Content-Type: multipart/form-data
body: 单 part，name="message" filename="message"
      内容 = varint 长度前缀 + Log(SwiftProtobuf) 消息
```

protobuf schema 从二进制静态恢复，见 [`schema.json`](schema.json)（9 消息 / 128 字段 / 20 枚举）。

关键结构：

```
Log {
  publicMeta = 1     // 设备/用户/时间
  basicMeta  = 2
  pageViewMeta = 3   // PageViewMeta.feedIdList = repeated string 字段 8
  elementViewMeta = 4
  clickMeta  = 5     // ClickMeta.repostFeedId = 字段 26
}
```

编解码实现见 [`payload.py`](payload.py)。

### 4. 评论接口的三个形态

| 形态 | `comment_type` | `tid` | `reply_comment_id` |
|---|---|---|---|
| 顶层评论 | `comment` | 毫秒时间戳 | 不填 |
| 楼中楼回复 | `reply` | 毫秒时间戳 | 父评论 ID |

`reply_comment_id` 只在 `comment_type=reply` 且 `tid` 是时间戳时才生效，否则被服务端忽略。

### 5. 列表排序参数

`/v8/circle/feed/list` 的 `list_type`：

| 值 | 排序 |
|---|---|
| `1` | 热度（时间不连续）|
| `2` | **时间倒序**（拉窗口数据要用这个）|
| `3` | 空 |

---

## 快速开始

> **第一次用？看 [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md)** —— 从零到跑通，含抓包步骤、字段对照表、验证方法。

### 1. 准备身份样本（必须有）

项目依赖一份 `session_sample.json`，本质是「一次成功请求的完整快照」。

**必须包含这 6 个字段**：

| 字段 | 位置 | 长什么样 |
|---|---|---|
| `token` | 请求头 | `eyJleHAiOjE3...`（JWT，200+ 字符）|
| `S-CID` | 请求头 | `01` + 19 位数字（共 21 位）|
| `S-PID` | 请求头 | 19 位数字|
| `S-PPID` | 请求头 | `2117080695704129536@sohu.com` |
| `key_jegb` | **请求体** | 64 字符设备密钥 |
| `gid` | 请求头 | `x011050110101...`（44 字符）|

**获取方式**（三选一，详见 GETTING-STARTED）：

| 方式 | 难度 | 需要什么 |
|---|---|---|
| mitmproxy | 中 | 电脑 + 同一 WiFi |
| Charles | 中 | 同上，图形界面 |
| Stream（手机 App）| **低** | 只要手机 |

抓到任意一个 `cs-ol.sns.sohu.com` 请求就够了，所有字段都在里面。

模板见 [`examples/session.example.json`](examples/session.example.json)。

### 2. 安装（零依赖）

```bash
# 只需要 Python 3.8+
python3 --version

# 可选：部署到服务器
bash install.sh
```

### 3. 基本用法

```python
import sys
sys.path.insert(0, '.')

from feed_reader import FeedReader
from boost_protocol import Session

# 读帖子
r = FeedReader('session_sample.json')
info = r.feed('<FEED_ID>')
print(info['content'], info['counts'])

# 读评论
comments, page = r.comments('<FEED_ID>', count=20)
for c in comments:
    print(c['user']['name'], c['content'])

# 刷 300 曝光
s = Session('session_sample.json')
codes = [s.report_once('<FEED_ID>', i) for i in range(150)]
print(sum(1 for c in codes if c == 200), '/150 成功')
```

### 4. 自动监听

```bash
# 监控圈子，命中 <exposure:N> 自动刷量
python3 comment_watcher.py --circle <CIRCLE_ID> --days 7 --interval 180

# 只跑一次
python3 comment_watcher.py --circle <CIRCLE_ID> --once --dry-run
```

### 5. 监控面板

```bash
python3 web_watcher.py --port 8790
# 打开 http://127.0.0.1:8790
```

---

## 文件说明

| 文件 | 作用 |
|---|---|
| `sign.py` | 签名算法 |
| `payload.py` + `schema.json` | 埋点 protobuf 编解码 |
| `boost_protocol.py` | 刷曝光核心（`Session` 类） |
| `feed_reader.py` | 读接口（`FeedReader` 类） |
| `comment_watcher.py` | 自动监听主逻辑 |
| `ai_reply.py` | AI 自动回复（OpenAI 兼容接口） |
| `token_stats.py` | Token 消耗统计 |
| `profile_updater.py` | 定时把统计写进个人简介 |
| `watcher_config.py` | 配置读写 |
| `knowledge.py` | 知识库（`knowledge.txt`，一行一句）|
| `web_watcher.py` | 监控面板（优先用 `web_dist/`，无则降级内置 HTML）|
| `web/` | 前端源码（Three.js + TypeScript + Vite）|
| `web_reader.py` | 帖子/圈子阅读器 |
| `web_boost.py` + `console.html` | 流量控制台 |
| `install.sh` | 一键部署（含守护） |
| `check.sh` | 环境自检 |

---

## 测试

零依赖，不需要 pytest：

```bash
python3 tests/run_all.py
# 或
make test
```

覆盖：签名稳定性、nonce 格式与时效、埋点编解码、配置读写与正则匹配。

CI（GitHub Actions）会在 Python 3.8 / 3.10 / 3.12 上跑一遍。

---

## 文档

| 文档 | 内容 |
|---|---|
| **[`docs/GETTING-STARTED.md`](docs/GETTING-STARTED.md)** | **从零开始：抓包、填配置、验证、跑通** |
| **[`DEPLOY.md`](DEPLOY.md)** | **部署到服务器（宝塔/裸机）+ 运维 + 卸载** |
| **[`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)** | **排错手册（按症状查）** |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | 模块依赖、数据流、状态文件格式 |
| [`KNOWLEDGE.md`](KNOWLEDGE.md) | 知识库用法（给 AI 补充学校信息）|
| [`WEB.md`](WEB.md) | 前端开发（Three.js + TS + Vite）|
| [`docs/SESSION.md`](docs/SESSION.md) | 身份样本字段说明与抓取方法 |
| [`docs/API.md`](docs/API.md) | 接口清单（路径/参数/返回） |
| [`docs/PROTOBUF.md`](docs/PROTOBUF.md) | 埋点协议与 schema 结构 |
| [`docs/FINDINGS.md`](docs/FINDINGS.md) | 研究过程中的一些发现（参数报错、风控行为等） |

---

## 一些实测数据

**刷曝光速率**（4 线程 / 每批 20 条 / 批间停 3 秒）：

```
50 条  → 12.0 秒   （4.2 条/秒）
150 条 → 约 25 秒
```

每条约 +2 曝光，服务端 30~100 秒批量落账。

**接口参数缺失时**，服务端会直接告诉你缺什么：

```json
{"status": 200003, "desc": "score,list_type,tpl,stpl"}
```

这个技巧比抓包快得多。

---

## FAQ

<details>
<summary><b>token 从哪来？能用多久？</b></summary>

**从哪来**：抓包。手机设代理（mitmproxy / Charles / Stream），打开 App 刷一下，抓任意 `cs-ol.sns.sohu.com` 请求，请求头里就有 `token`。

详细步骤见 [docs/GETTING-STARTED.md](docs/GETTING-STARTED.md)。

**能用多久**：JWT 的 `exp` 通常 400 天后，但 **App 每次活跃都会换发新 token，旧 token 立即作废**。

所以要让 token 长期有效，需要**在手机上退出该账号的登录**，让服务器这份独占。
</details>

<details>
<summary><b>报 200003 是什么问题？</b></summary>

参数缺失。`desc` 字段会直接列出缺少的参数名，例如：

```json
{"status": 200003, "desc": "score,list_type,tpl,stpl"}
```

按提示补齐即可，不用抓包。
</details>

<details>
<summary><b>报 400001 sig check fail 怎么办？</b></summary>

八成不是签名算法错，而是：

1. **多线程共享 `s-nonce`** —— 每次请求必须用局部 headers 副本
2. **请求过于密集** —— 加 `feed_reader.set_min_gap(1.5)` 或降并发

代码里 `FeedReader._request()` 已经是并发安全的写法，如果你改过它，检查这一点。
</details>

<details>
<summary><b>报 40110 登录失败？</b></summary>

token 失效了。App 每次活跃都会刷新 token，旧 token 立即作废。

处理：手机上退出该账号登录（让 token 不再刷新），然后重新抓一份 `session_sample.json`。
</details>

<details>
<summary><b>刷了曝光但数字没变？</b></summary>

三个检查点：

1. 服务端**批量落账**，要等 30~100 秒
2. 用 `Session.read_count(feed_id)` 直接读，别依赖列表接口（有缓存）
3. 用封号账号刷时，**读接口全废**，只能用另一台设备或 H5 页面确认
</details>

<details>
<summary><b>为什么给帖子发不出评论？</b></summary>

检查 `scan_circle` 是否跳过了 0 评论的帖子。

历史 bug：为了省请求，代码会跳过 `comment_count == 0` 的帖子，但"给新帖发评论"恰恰需要处理这些帖子。当前版本已修复（`reply_all_feeds` 开启时不跳过）。
</details>

<details>
<summary><b>AI 回复只输出一两个字？</b></summary>

`max_tokens` 太小，被思考链（`reasoning_content`）吃掉了。至少设 400。

另外某些模型会把思考过程写进 `content`，代码里有 `looks_like_reasoning()` 检测重试。
</details>

<details>
<summary><b>需要装什么依赖？</b></summary>

零依赖。只用 Python 标准库（`http.client`、`json`、`hashlib`、`base64`、`struct`、`concurrent.futures` 等）。

`schema.json` 是数据文件，`payload.py` 自带 protobuf 手写编解码，不需要 `protobuf` 包。
</details>

---

## 已知限制

- **token 会随客户端活跃而刷新**：手机端一操作，旧 token 立即失效
- **封号后读接口全部失效**，但埋点上报仍可能计数（实测过）
- **封号可能是设备级的**：同设备换账号注册也会被封
- **AI 网关**：不同厂商对 `max_tokens` 与 reasoning 字段处理差异较大
- **私聊消息是一次性消费的**：HTTP 拉到后服务端就删，App 在线时会走 MQTT 抢走
- **时间统一用 UTC+8**：服务器多为 UTC，代码里走 `tz.py` 固定北京时间

---

## License

MIT，见 [LICENSE](LICENSE)。

## 免责声明

本项目为协议分析的技术研究，作者不对使用者的行为负责。请遵守目标服务的使用条款，仅在你拥有完全控制权的账号与设备上使用。
