# 私聊

拉会话、读消息、发消息、AI 自动回复。

## 接口

```
POST dm-ol.sns.sohu.com/dm/api/v2/message       发消息
GET  dm-ol.sns.sohu.com/dm/api/v3/message       拉消息（增量）
GET  dm-spc-ol.sns.sohu.com/dm-poll/api/v2/newmsgcount   未读数
```

### 发消息

```http
POST /dm/api/v2/message
  to_user_id=1455627722759020160
  message=你好
  type=0
```

`type=0` 是文本。响应：

```json
{"status": 100000, "data": {"msg_data": {
  "id": "p_2117496076964704349",
  "conversation_id": "p14556277227590201601492943737658212864",
  "from_user_id": "...", "to_user_id": "...",
  "msg": "你好", "send_time": 1793685380581
}}}
```

### 拉消息

```http
GET /dm/api/v3/message?last_grp_eid=&last_priv_eid=<游标>&limit=100
```

响应：

```json
{"data": {
  "priv_msgs": [{"conversation_id": "...", "from_user_id": "...", "msgs": [...]}],
  "priv_eid": "19"
}}
```

**`priv_eid` 是游标**，下次传这个值拉增量。

## 关键特性：一次性消费

```
第一次拉（游标=14）→ 返回消息，游标推到 19
第二次拉（游标=19）→ 空
第三次拉（游标=18，故意回退）→ 也是空
```

**拉到一次后服务端就删了**，无法重复拉取。所以代码里做了 `pending` 机制：

```
拉取 → 存进 pending（落盘）→ 推进游标
     → AI 处理 → 发送成功 → 清除 pending
```

处理失败的消息留在 pending 里，下轮重试。

## 什么时候能拉到

| 手机 App 状态 | 消息去哪 |
|---|---|
| 前台 / 后台运行 | MQTT 推给 App，HTTP 拉不到 |
| **完全关闭**（上滑杀掉） | 留在服务端队列，HTTP 能拉 |

所以服务器跑 `dm_watcher` 时，手机上必须杀掉 App。

## 用法

```bash
# 持续运行（自动回复）
python3 dm_watcher.py

# 只检测不发送
python3 dm_watcher.py --once --dry-run

# 只记录不回复
python3 dm_watcher.py --no-reply

# 手动发一条
python3 dm_client.py --send <用户ID> --text "你好"

# 拉消息看看
python3 dm_client.py --pull
```

## 配置

```json
{
  "dm_enabled": true,
  "dm_pull_limit": 100,
  "dm_daily_cap": 50,
  "dm_reply_template": "在的，稍等",
  "dm_skip_keywords": ""
}
```

| 项 | 说明 |
|---|---|
| `dm_daily_cap` | 每天最多自动回多少条（0 = 不限）|
| `dm_skip_keywords` | 命中这些词就不回，逗号分隔 |
| `dm_reply_template` | AI 失败时的兜底文案 |

## 实测日志

```
私聊监听启动 | 账号 xxx | 模式 自动回复 | 间隔 60s
[14:06:42] 待处理私聊 3 条（本轮新拉 0）
[14:06:46] [EXEC] 1455627722759020160: '在吗' → '在的，咋了哥们' (ai)
[14:06:46] ✅ 已回复 1455627722759020160
[14:06:52] [EXEC] 1455627722759020160: 'hi' → '哟，这么晚还不睡？' (ai)
[14:06:52] ✅ 已回复 1455627722759020160
```

## 延迟

```
对方发消息 → 最多 60 秒（下一轮）→ AI 生成 2~5 秒 → 发送
= 最坏 65 秒
```

想做秒级需要逆向 MQTT（`csmqtt-ol.sns.sohu.com`）。

## 会话里的小限制

系统会提示：

```
由于你未关注对方，你回复之前，ta 24小时内可发送1条消息
```

没互相关注时，对方 24 小时只能发 1 条。你回复后对方才能继续发。

自动回复正好能解这个限制。
