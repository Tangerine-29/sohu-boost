# 接口清单

所有接口走 `https://cs-ol.sns.sohu.com`（业务）或 `https://opapi-ol.sns.sohu.com`（埋点）。

统一参数：`app_key_vs`（版本）、`appid=330000`、`flyer`（毫秒时间戳）、`key_jegb`、`log_user_id`、`sig`。

## 读接口

### 帖子详情

```
POST /330000/v7/feeds/show
body: feed_id=<ID>&extras=1
```

返回 `data.sourceFeed`：`content`、`feedId`、`exposureCount`、`commentCount`、`repostCount`、`userName`、`userId`、`avatar`、`score`（发布时间）、`circle`、`picFeed.pics[]`

### 评论列表

```
GET /330000/v8/comment/list
query: feed_id, count, score, jump_comment_id, stpl=1,4,8
```

返回 `data.pageInfo`（`hasMore`/`totalCount`/`score`）与 `data.list[]`

单条评论字段（**扁平结构**）：

```json
{
  "commentId": "...", "content": "...",
  "userId": "...", "userName": "...", "avatar": "...",
  "timeId": 1793552111095, "likeCount": 0, "replyCount": 0,
  "sourceRegion": "贵州", "anonymous": false
}
```

### 楼中楼子回复

```
GET /330000/v8/comment/replylist
query: comment_id=<父评论ID>, feed_id, count, score, stpl
```

**注意**：上层评论列表不返回子回复，只给 `replyCount`。

### 圈子帖子列表

```
GET /330000/v8/circle/feed/list
query: circle_id, count, score, list_type, tpl=1, stpl=1,2,4,8
```

`list_type`：`1`=热度、`2`=时间倒序（拉窗口用这个）、`3`=空

返回 `data.feedList[]`（每项是 `{tpl, sourceFeed, fastComment}`）+ `data.pageInfo`

### 用户资料

```
GET /330000/v6/users/show_reduced
query: user_id
```

返回 `userName`、`userId`、`passportId`、`avatar`、`followCount` 等。

**注意**：这个接口**不返回简介**（`description`）。

## 写接口

### 发评论 / 楼中楼

```
POST /330000/v8/comment/text
body: comment_type, tid, feed_id, content[, reply_comment_id]
```

| 形态 | comment_type | tid | reply_comment_id |
|---|---|---|---|
| 顶层 | `comment` | 毫秒时间戳 | 不填 |
| 楼中楼 | `reply` | 毫秒时间戳 | 父评论 ID |

### 删评论

```
POST /330000/v6/feeds/comment/remove
body: comment_id, feed_id
```

返回 `100000` 或 `310005`（都已删除）。

### 转发

```
POST /330000/v6/feeds/repost
body: user_id, repost_feed_id, type
```

成功返回 `newFeedId` + `addCount`。按 (账号, 原帖) 去重，重复转发 `addCount: 0`。

### 改简介

```
POST /330000/v5/users/update
body: user_id, description, banned_word=1
```

**注意**：
- 字段是 `description`，不是 `brief`/`intro`/`signature`
- **不要带 `extras`**（那是 feeds/show 的参数）
- `banned_word=1` 触发敏感词检查

### 刷曝光（埋点）

```
POST https://opapi-ol.sns.sohu.com/openapi/pingback/log/report
Content-Type: multipart/form-data
query: app_key_vs, appid, flyer, sig
body: 单 part（name="message" filename="message"），内容是 protobuf
```

每条约 +2 曝光，服务端 30~100 秒批量落账。

## 错误码

| status | desc | 含义 |
|---|---|---|
| `100000` | success | 成功 |
| `200002` | Request api not found | 路径错 |
| `200003` | 字段列表 | **参数缺失**（desc 列出缺的字段）|
| `200006` | Http post is not supported | GET/POST 用错 |
| `310003` | 内容已删除，无法操作 | 目标帖/评论不存在 |
| `310005` | — | 评论已删除 |
| `320002` | 账户因违规已被狐友封禁 | 封号 |
| `400001` | n:sig check fail! | 签名失败（并发/参数不一致）|
| `40110` | 登录失败，请重新登录 | token 失效 |
| `411000` | 访问过于频繁 | 限流 |
