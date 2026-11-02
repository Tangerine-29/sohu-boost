# 部署到服务器

面向宝塔面板用户，也适用于裸 Linux。

---

## 一、服务器要求

| 项 | 要求 |
|---|---|
| 系统 | Linux（CentOS / Ubuntu / Debian 都行）|
| Python | 3.8+（3.10 最稳）|
| 内存 | 512 MB 以上 |
| 出网 | 能访问 `cs-ol.sns.sohu.com`、`opapi-ol.sns.sohu.com`、你的 AI 网关 |
| 依赖 | **无**，不需要 pip install |

---

## 二、上传文件

### 方式 A：宝塔文件管理器

1. 宝塔 → 文件 → 进入 `/www/wwwroot/`
2. 新建目录 `sohu-boost`
3. 上传项目文件（或上传压缩包后右键解压）
4. 确认目录内有 `install.sh`、`comment_watcher.py`、`session_sample.json`

### 方式 B：命令行

```bash
cd /www/wwwroot
mkdir -p sohu-boost
cd sohu-boost
# 用 scp / rsync 把本地文件传上来
```

---

## 三、准备身份样本（必须先做）

项目需要 `session_sample.json`（见 [GETTING-STARTED.md](docs/GETTING-STARTED.md)）。

**在本地抓好、填好、验证通过后，再上传到服务器。**

验证方法（本地跑）：

```bash
python3 -c "
from feed_reader import FeedReader
r = FeedReader('session_sample.json')
print('身份:', r.s.user_id)
f = r.feed('<随便一个帖子ID>')
print('读帖子:', f.get('ok'), f.get('content'))
"
```

`内容` 有值才说明 token 有效。

---

## 四、配置权限（重要）

```bash
cd /www/wwwroot/sohu-boost

# 凭证文件收紧
chmod 600 session_sample.json
chmod 600 watcher_config.json
[ -f session_boost.json ] && chmod 600 session_boost.json

# 脚本可执行
chmod +x install.sh check.sh
```

---

## 五、运行安装脚本

```bash
bash install.sh
```

它会依次做：

```
[OK] 语法检查通过
[OK] 接口自检通过（OK feeds=20 total=xxxx）
[OK] 守护脚本：/www/wwwroot/sohu-boost/guard.sh
[OK] 监听器已启动 pid=xxxxx（圈子 xxx / 窗口 7 天 / 间隔 180s）
[OK] 简介更新器已启动（每 3 小时刷新 Token 消耗）
[OK] 已加入 crontab 守护（每 2 分钟检查）
[OK] 面板已在监听 8790
```

### install.sh 的几个参数

```bash
bash install.sh                  # 正常启动（保留去重记录）
bash install.sh --stop           # 停止并移除守护
bash install.sh --reset          # 清空去重记录后启动
CIRCLE=<圈子ID> INTERVAL=60 bash install.sh   # 自定义
```

⚠️ **`--reset` 会让所有历史评论被重新处理**，除非确实需要，否则不要加。

---

## 六、放行端口（如果要用面板）

### 宝塔防火墙

宝塔 → 安全 → 添加端口规则：

```
端口：8790
协议：TCP
放行：所有 IP（或只填你的出口 IP）
```

### 云厂商安全组

如果服务器在阿里云/腾讯云/华为云，还要去控制台放行 `TCP:8790`。

漏了这一步会出现「本地 curl 通、外网打不开」。

---

## 七、面板访问

```
http://<服务器IP>:8790
```

⚠️ **面板没有登录鉴权**。公网暴露前至少做一件事：

- 宝塔 → 网站 → 访问限制 → 加 Basic Auth
- 或者只允许你自己 IP 访问

---

## 八、验证部署

```bash
cd /www/wwwroot/sohu-boost
bash check.sh
```

八项检查，全部通过才算正常：

| # | 检查 | 正常表现 |
|---|---|---|
| 1 | 进程 | 监听器 + 面板都在跑 |
| 2 | 双账号 | 刷量号 / 回复号不同 |
| 3 | 配置 | 参数符合预期 |
| 4 | 日志 | 400 秒内有更新 |
| 5 | 接口 | 能读到内容 |
| 6 | 刷量通道 | 3/3 成功 |
| 7 | 面板 | API 响应 |
| 8 | 状态文件 | 有 `__meta__` 时间 |

---

## 九、日常运维

### 看日志

```bash
tail -f /www/wwwroot/sohu-boost/watcher.log
```

正常每 3 分钟一行：

```
[13:xx:xx] 圈子 xxx: 窗口内 82 条（5 页），检查 43 条有评论的帖子，命中 0
```

### 看简介更新

```bash
tail -f /www/wwwroot/sohu-boost/profile.log
```

### 看守护状态

```bash
tail -5 /www/wwwroot/sohu-boost/guard_status.log
```

### 重启

```bash
cd /www/wwwroot/sohu-boost
bash install.sh
```

### 停止

```bash
bash install.sh --stop
```

---

## 十、常见部署问题

| 现象 | 原因 | 处理 |
|---|---|---|
| `接口自检未通过` | token 失效 | 重新抓 `session_sample.json` |
| `面板未起来` | 8790 被占用 | `lsof -i:8790` 查占用，或换端口 |
| 外网打不开面板 | 防火墙 / 安全组 | 见第六节 |
| 日志 6 分钟不动 | 进程卡死 | `guard.sh` 会自动重启，也可手动 `bash install.sh` |
| `Permission denied` | 文件权限 | `chmod +x install.sh` |
| `ModuleNotFoundError` | 文件不全 | 重新完整解压项目 |

---

## 十一、让服务更稳

### 1. 手机上退出目标账号登录

否则 App 一活跃就刷新 token，服务器上这份立刻失效（表现 `40110`）。

### 2. 定期检查

加到 crontab，每天早上看一眼：

```bash
0 9 * * * cd /www/wwwroot/sohu-boost && bash check.sh >> check.log 2>&1
```

### 3. 日志轮转

```bash
# 加 logrotate 配置，避免日志占满磁盘
cat > /etc/logrotate.d/sohu-boost <<'EOF'
/www/wwwroot/sohu-boost/*.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
EOF
```

---

## 十二、卸载

```bash
cd /www/wwwroot/sohu-boost
bash install.sh --stop
cd ..
rm -rf sohu-boost
```

`--stop` 会自动移除 crontab 里的守护任务。
