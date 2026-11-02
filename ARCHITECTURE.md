# 架构说明

## 模块依赖

```
                    ┌─────────────┐
                    │ sign.py     │  签名算法
                    └──────┬──────┘
                           │ sign(params, headers)
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼──────┐  ┌────────▼────────┐  ┌─────▼──────┐
│ payload.py   │  │ feed_reader.py  │  │ boost_     │
│ 埋点编解码    │  │ 读接口          │  │ protocol.py│
│ +schema.json │  │ (FeedReader)    │  │ (Session)  │
└───────┬──────┘  └────────┬────────┘  └─────┬──────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                  ┌────────▼─────────┐
                  │ comment_watcher  │  主逻辑
                  │  (Watcher)       │
                  └────────┬─────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼──────┐  ┌────────▼────────┐  ┌─────▼──────┐
│ ai_reply.py  │  │ token_stats.py  │  │ web_       │
│ AI 生成回复   │  │ Token 统计      │  │ watcher.py │
└───────┬──────┘  └────────┬────────┘  │ 监控面板    │
        │                  │            └────────────┘
        └──────────────────┴──────────┐
                                      │
                            ┌─────────▼────────┐
                            │ profile_updater  │  定时写简介
                            └──────────────────┘
```

## 身份与请求

所有请求都需要一份 **session 样本**（`session_sample.json`），它提供：

- `headers`：`S-CID`、`S-PID`、`S-PPID`、`token`、`key_jegb`…
- `body`：表单参数模板

`FeedReader` / `Session` 都从这里初始化。

**关键设计**：`s-nonce` 每次请求重新生成，且用**局部 headers 副本**签名，避免并发覆盖。

```python
def _request(self, path, params, method='GET'):
    headers = dict(self.s.headers)      # ① 复制
    headers['s-nonce'] = gen_nonce()    # ② 副本上生成
    p = dict(params)
    p['sig'] = sign(p, headers)         # ③ 同一副本签名
    conn.request(..., headers=headers)  # ④ 同一副本发送
```

## 双账号分工

```
session_sample.json  → 读帖子、读评论、发回复（需要能正常读写）
session_boost.json   → 只刷曝光（可以是已封禁的号）
```

`Watcher` 初始化时分别绑定：

```python
self.reader = FeedReader()                          # 读+回复
self.session = Session(boost_session or '...')      # 刷量
```

封禁号只能刷量（埋点仍计数），所以两件事解耦。

## 监听主循环

```
每 180 秒一轮：

scan_circle(circle_id)
  ├─ circle_feeds_since(days=7, list_type=2)      # 时间序列表
  │   └─ 每页间隔 1.5s（list_page_delay）
  │
  └─ 并发扫描每条帖子（8 线程）
      └─ scan_feed(feed_id)
          ├─ ① 帖子时间校验（feed_reply_only_after_start）
          ├─ ② 帖子内容触发（reply_all_feeds / 关键词）
          │      └─ post_feed_comment()  ← 每帖限一条（__feed_marks__）
          │
          └─ ③ 评论循环
              ├─ 时间窗口校验（reply_grace_minutes / reply_window_days）
              ├─ 命中 <exposure:N>？
              │   └─ handle_match()
              │       ├─ 查重 → 占位落盘
              │       ├─ can_boost()  频控 + 日上限
              │       ├─ boost()  分批发送
              │       └─ _maybe_reply()  楼中楼回复
              │
              └─ 普通评论 + ai_reply_mode=all？
                  └─ _maybe_reply()
```

## 状态文件

### watcher_state.json

```json
{
  "__meta__": {"started_at": 1793596177, "at": "13:09:37"},
  "__feed_marks__": {
    "<FEED_ID>": {
      "at": "12:54:37",
      "ts": 1793596477.5,
      "commentId": "<COMMENT_ID>",
      "content": "这不就在这嘛"
    }
  },
  "<COMMENT_ID>": {
    "feedId": "<FEED_ID>",
    "n": 300,
    "sent": 150,
    "at": "12:17:24",
    "status": "done"
  }
}
```

| 键 | 作用 |
|---|---|
| `__meta__` | 启动时刻（时间窗口基准），保留则不随重启重置 |
| `__feed_marks__` | 已发过顶层评论的帖子（每帖一条 + 小时额度统计）|
| 其他键 | 已处理的评论 ID → 处理记录（去重）|

**写入方式**：锁内查重+占位+原子写（临时文件 + `rename`），防并发重复、防崩溃损坏。

### token_stats.json

```json
{
  "total_tokens": 42000,
  "by_model": {"deepseek-v4.1-flash": 42000},
  "calls": 42,
  "first_at": "2026-11-02 22:00:00",
  "updated_at": "2026-11-03 01:00:00"
}
```

## 配置热加载

`Watcher.reload_config()` 在每轮 `scan_circle` 开头调用，所以：

**改 `watcher_config.json` → 下一轮自动生效，不用重启。**

只有改 `.py` 代码才需要重启。

## 限流设计

| 位置 | 参数 | 作用 |
|---|---|---|
| 刷量并发 | `boost_workers=4` | 4 条/秒量级 |
| 批间停顿 | `boost_batch_delay=3.0` | 每 20 条停 3 秒 |
| 任务间隔 | `boost_min_interval=120` | 两次刷量至少隔 2 分钟 |
| 翻页 | `list_page_delay=1.5` | 每页 1.5 秒 |
| 随机抖动 | `api_jitter=0.2` | 避免等间隔特征 |
| 顶层评论 | `feed_reply_hourly_cap=10` | 每小时最多 10 条 |
| 轮询 | `--interval 180` | 3 分钟一轮 |

## 失败处理

| 场景 | 行为 |
|---|---|
| 单次请求失败 | 重试 3 次（AI 调用）|
| 刷量部分失败 | 记录成功数，继续 |
| AI 调用失败 | 回落固定模板文案 |
| 检测到封禁 | `halt_reply_on_ban=true` 停回复；`halt_boost_on_ban=false` 继续刷 |
| 进程卡死 | `guard.sh` 日志 6 分钟不动则重启 |
| 进程崩溃 | crontab 每 2 分钟检查并拉起 |
