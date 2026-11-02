# 身份样本（session_sample.json）

所有请求都依赖一份抓包导出的身份样本。本文说明它的字段含义与获取方式。

## 完整示例

见 [`examples/session.example.json`](../examples/session.example.json)。

## 字段说明

### headers（关键）

| 字段 | 含义 | 备注 |
|---|---|---|
| `S-CID` | 设备 ID | 21 位，格式 `01` + 19 位数字 |
| `S-PID` | 用户数字 ID | 业务接口用它 |
| `S-PPID` | passport | 形如 `xxx@sohu.com`，用户信息接口用它 |
| `S-VS` | App 版本 | `6.24.1` |
| `s-nonce` | 随机串 | **每次请求重新生成**，见 `gen_nonce()` |
| `token` | 登录凭证 | 会随客户端活跃刷新 |
| `gid` | 设备 gid | 44 字符 |
| `P-APPID` | 固定 `110501` | |
| `appid` | 固定 `330000` | |
| `S-DV` / `S-OS` | 机型 / 系统版本 | 可随意填 |

### body

表单参数模板，主要用到：

```
app_key_vs=6.24.1&appid=330000&extras=1&key_jegb=<64字符>&log_user_id=<用户数字ID>
```

- `key_jegb`：64 字符**设备级**密钥，不随账号变
- `log_user_id`：用户数字 ID

## 获取方法

### 方法 1：代理抓包（无需越狱）

1. 手机与电脑连同一 WiFi
2. 电脑上跑 mitmproxy / Charles
3. 手机设置代理指向电脑，装证书
4. 打开 App，抓任意 `cs-ol.sns.sohu.com` 请求
5. 导出请求头 + 请求体

### 方法 2：Frida（需越狱）

```javascript
// hook NSURLSessionTask resume，打印请求头和 body
```

完整脚本见项目 issue 或自写，核心是读 `currentRequest.allHTTPHeaderFields` 与 `HTTPBody`。

## 注意事项

1. **token 有时效**：App 每次活跃会换发新 token，旧 token 立即作废。手机上退出登录、只用服务器这份能延长有效期。
2. **不要提交到 git**：`.gitignore` 已排除 `session*.json`。
3. **`key_jegb` 是设备级的**：换账号不用换这个。
