# 研究过程中的发现

本文记录逆向与实测中的一些细节，供同类研究参考。

## 1. 参数缺失时服务端会告诉你缺什么

大多数接口在缺参数时返回：

```json
{"status": 200003, "desc": "score,list_type,tpl,stpl"}
```

`desc` 直接列出缺少的字段名。这个技巧比抓包快得多：

```python
# 先发空请求，读 desc，再补参数
```

## 2. 列表接口的 list_type 有坑

`/v8/circle/feed/list`：

- `list_type=1` → 按**热度**排，时间不连续
- `list_type=2` → 按**时间**倒序（拉时间窗口数据必须用这个）
- `list_type=3` → 返回空

用错 `list_type` 的现象很隐蔽：接口返回 200、有数据，但时间跨度不对。

## 3. 评论接口的 comment_type 与 tid 联动

| 形态 | comment_type | tid | reply_comment_id |
|---|---|---|---|
| 顶层评论 | `comment` | 毫秒时间戳 | 不填 |
| 楼中楼 | `reply` | 毫秒时间戳 | 父评论 ID |

如果用 `comment_type=1` 或 `tid=0`，`reply_comment_id` 会被**静默忽略**，评论变成顶层的。

## 4. 服务端对未知字段静默忽略

往 `users/update` 传 `intro`、`signature`、`brief` 都会返回 `{"status":100000,"desc":"success"}`，但数据不变。

真正的字段是 **`description`**，还要带 `banned_word=1`。

判断方法：改完必须**读回验证**，不能只看返回码。

## 5. 并发会触发 sig check fail

`400001 n:sig check fail!` 的常见原因不是签名算法错，而是：

- 多线程共享 `s-nonce`，互相覆盖
- 同一进程内请求过于密集

解决：每次请求用**局部 headers 副本** + 生成新 nonce；必要时加全局请求间隔（`feed_reader.set_min_gap()`）。

## 6. 封禁的层级

实测：

| 操作 | 封号后 |
|---|---|
| 读帖子 / 评论 / 列表 | ❌ 全部失效（返回空或 None）|
| 发评论 | ❌ `320002 账户因违规已被狐友封禁` |
| **刷曝光埋点** | ✅ **仍然计数** |

另外：**设备级封禁**存在 —— 同一台设备上换新账号注册也会被封。

设备标识存在 Keychain（`cidKey` / `idfvKey`），可以改写，但实测**改写后新账号仍可能被封**，说明服务端还认别的（token 绑定、APNs token、IP 等）。

## 7. 每帖 0 评论时会被跳过

一个优化踩的坑：

```python
if post.comment_count == 0:
    continue    # 省一次请求
```

如果同时也做"给帖子发评论"的功能，0 评论的帖子恰恰是**最该处理**的（没有评论说明还没被回过），这个优化会把它们全过滤掉。

## 8. AI 网关的 reasoning_content

部分模型（如某些 flash 系列）响应里会带 `reasoning_content` 字段（思考链），且 `max_tokens` 会被思考消耗：

```json
{
  "content": "实际回复",
  "reasoning_content": "用户要针对...说一句..."
}
```

如果 `max_tokens` 给太小（如 160），content 可能只剩一两个字。建议 400+。

另外要用浏览器 UA 请求，否则 Cloudflare 会拦（`403 error code: 1010`）。
