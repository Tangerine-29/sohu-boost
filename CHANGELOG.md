# 变更日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 计划
- 补充单元测试
- 支持更多接口（点赞接口尚未打通）

## [1.0.0] - 2026-11-03

首个公开版本。

### 新增

- **签名算法**（`sign.py`）：`MD5(sorted_params + KEY_MATERIAL)`，含 5 个签名字段
- **s-nonce 动态生成**：8 字节毫秒时间戳 + 40 字节安全随机数
- **埋点 protobuf 编解码**（`payload.py` + `schema.json`）：从二进制恢复 9 消息 / 128 字段
- **刷曝光**（`boost_protocol.py`）：分批 + 限速 + 失败重试
- **读接口**（`feed_reader.py`）：帖子详情、评论列表、楼中楼、圈子时间线分页
- **发/删评论**：顶层评论、楼中楼回复（`comment_type` + `tid` 联动）
- **自动监听**（`comment_watcher.py`）：
  - 双账号分工（读写号 / 刷量号）
  - 每帖顶层评论限 1 条（`__feed_marks__` 标记）
  - 评论时间窗口（只处理启动后产生的）
  - 每小时额度限制
  - 封禁自动停机
- **AI 自动回复**（`ai_reply.py`）：OpenAI 兼容接口，支持人设、字数限制、失败回落
- **Token 消耗统计**（`token_stats.py`）+ **定时写简介**（`profile_updater.py`）
- **监控面板**（`web_watcher.py`）：帖子列表、触发记录、配置编辑
- **部署脚本**（`install.sh` / `check.sh`）：一键安装 + 八项自检 + crontab 守护

### 修复

- 并发请求共享 `s-nonce` 导致 `400001 sig check fail`
- `comment_type=1` + `tid=0` 时 `reply_comment_id` 被服务端静默忽略
- `list_type=1`（热度排序）导致时间窗口数据不连续
- 服务端对未知字段静默忽略（`intro`/`brief`/`signature` 都不生效，实际字段是 `description`）
- `scan_circle` 跳过 0 评论帖子，导致无法给新帖发评论
- AI 返回 `reasoning_content` 被当成正文
- Cloudflare 拦截 Python 默认 UA（`403 error code: 1010`）

### 已知问题

- 点赞接口（`/gis/story/like/v20`）对普通图文帖返回「story已删除」，未打通
- token 会随客户端活跃刷新，需要手动更新 `session_sample.json`
- 封号后读接口全部失效（埋点仍计数）
