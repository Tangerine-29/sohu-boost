# 安全策略

## 报告漏洞

如果你发现本项目的安全问题（例如凭证泄露路径、意外的数据外泄），请**不要**公开提交 Issue。

请通过以下方式私下联系维护者：

- 在 GitHub 上使用 **Security** 标签页的 "Report a vulnerability"
- 或直接邮件联系仓库所有者（见个人主页）

我们会在 48 小时内回复。

## 本项目涉及的安全边界

这是一个协议研究工具，本身会处理**高度敏感的数据**：

| 数据 | 风险 |
|---|---|
| `session_sample.json` 里的 `token` | 等价于账号登录凭证，泄露即等于账号被盗 |
| `watcher_config.json` 里的 `ai_api_key` | 会被盗刷 |
| `key_jegb` / `S-CID` | 设备级标识 |
| `watcher_state.json` | 含处理过的评论内容与帖子 ID |

## 使用者的责任

1. **不要提交含凭证的文件**（`.gitignore` 已覆盖，但请自行确认）
2. **不要分享你的 `session_sample.json`**（连截图都不行）
3. **服务器权限收紧**：
   ```bash
   chmod 600 session_sample.json watcher_config.json session_boost.json
   ```
4. **面板不要裸奔公网**（`web_watcher.py` 没有鉴权，建议加 Basic Auth 或 IP 白名单）

## 凭证泄露后的应急

```bash
# 1. 立即在 App 里退出目标账号（token 失效）
# 2. 重置 AI 网关的 API key
# 3. 检查是否有异常调用记录
```

## 已排除的风险

本项目已做的防护：

- 所有示例文件使用占位符
- `.gitignore` 排除全部运行时数据
- 签名与 nonce 每次请求重新计算，不复用
- 网络请求全部带超时
