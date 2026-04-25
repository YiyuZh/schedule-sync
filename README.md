# 日程安排云同步服务

这是“日程安排”的独立云同步服务端，负责账号、设备、Token、同步快照和变更日志。

云端不保存 AI Key，不代理 AI 请求，不承载本地业务逻辑。

## 生产域名与网关约定

本服务对齐 `D:\apps\gateway-portal\主页维护手册.md` 中记录的现有服务器网关体系。

- 正式同步域名：`https://schedule-sync.zenithy.art`
- 主站门户：`https://zenithy.art`
- 现有项目域名：`hiremate.zenithy.art`、`interview.zenithy.art`、`admin.interview.zenithy.art`、`blog.zenithy.art`
- 服务器部署目录：`/opt/apps/schedule-sync`
- 公网 Caddy 事实来源：`/opt/apps/hiremate/Caddyfile`
- 公网 Caddy 容器：`hiremate-caddy`
- 公共 Docker 网络：`shared_gateway`

`gateway-portal` 仓库里的 Caddyfile 只作为参考；线上实际要改 `/opt/apps/hiremate/Caddyfile`。

## 本地开发

```powershell
cd D:\apps\schedule_sync_server
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

默认本地地址：

```text
http://127.0.0.1:18130
```

健康检查：

```powershell
curl http://127.0.0.1:18130/api/health
```

测试：

```powershell
python -m pytest -q
```

## 生产部署

服务器目录固定：

```text
/opt/apps/schedule-sync
```

首次部署：

```bash
cd /opt/apps
git clone <你的仓库地址> schedule-sync
cd /opt/apps/schedule-sync
cp .env.example .env
nano .env
bash deploy/bootstrap-server.sh
```

`.env` 必须修改：

- `APP_BASE_URL=https://schedule-sync.zenithy.art`
- `SCHEDULE_SYNC_DOMAIN=schedule-sync.zenithy.art`
- `POSTGRES_USER=autsky`
- `POSTGRES_PASSWORD=<强密码>`
- `DATABASE_URL=postgresql+psycopg://autsky:<URL编码后的强密码>@postgres:5432/schedule_sync`
- `JWT_SECRET=<至少 32 位随机字符串>`
- `ALLOWED_ORIGINS=http://127.0.0.1:1420,http://localhost:1420,http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:5174,http://localhost:5174,http://localhost,tauri://localhost,capacitor://localhost,ionic://localhost,https://schedule-sync.zenithy.art`
- `PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`
- `PIP_TRUSTED_HOST=pypi.tuna.tsinghua.edu.cn`
- `APT_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian`
- `APT_SECURITY_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian-security`

生产环境会拒绝默认 JWT、SQLite、`replace-with-*`、`sync.example.com` 等占位配置。

### PostgreSQL 用户名统一规则

本项目生产环境统一使用：

```env
POSTGRES_USER=autsky
```

`DATABASE_URL` 使用同一个用户名 `autsky`，不需要再做邮箱 `@` 编码：

```env
DATABASE_URL=postgresql+psycopg://autsky:<URL编码后的强密码>@postgres:5432/schedule_sync
```

如果密码里包含 `@`、`#`、`:`、`/`、`?`、`&` 等特殊字符，密码也必须 URL 编码。

如果服务器已经启动过 PostgreSQL，单纯修改 `.env` 不会自动创建新角色。执行：

```bash
cd /opt/apps/schedule-sync
bash deploy/fix-postgres-user.sh
docker compose up -d api
curl http://127.0.0.1:18130/api/health
```

如果这里返回 `db=ok`，再测试公网：

```bash
curl -vk https://schedule-sync.zenithy.art/api/health
```

### 构建加速说明

云端 build 慢通常卡在基础镜像、Debian apt 或 Python pip 三处。当前 Dockerfile 已把 apt 源和 pip 源切到清华镜像，`.env.example` 也提供了对应变量。

如果仍然卡在：

- `FROM python:3.11-slim`：这是 Docker Hub 拉基础镜像慢，需要配置服务器 Docker registry mirror，或先执行 `docker pull python:3.11-slim`。
- `apt-get update`：检查 `.env` 中的 `APT_MIRROR` 和 `APT_SECURITY_MIRROR`。
- `pip install`：检查 `.env` 中的 `PIP_INDEX_URL` 和 `PIP_TRUSTED_HOST`。

## Caddy 接入

继续复用已有网关：

```text
/opt/apps/hiremate/Caddyfile
```

示例：

```caddy
schedule-sync.zenithy.art {
    import common_site

    reverse_proxy schedule-sync-api:8000
}
```

`schedule-sync-api:8000` 是容器网络内的服务地址；宿主机 `18130` 只用于本机预览和冒烟测试，不要作为 Caddy 反代目标。

确认服务接入 `shared_gateway` 网络后执行：

```bash
docker exec hiremate-caddy caddy reload --config /etc/caddy/Caddyfile
curl https://schedule-sync.zenithy.art/api/health
```

### TLS 握手失败排查

如果电脑端登录时报：

```text
[SSL: TLSV1_ALERT_INTERNAL_ERROR] tlsv1 alert internal error
```

这代表 HTTPS 在 Caddy 证书握手阶段失败，请求还没有到达 FastAPI，也不是电脑客户端业务代码问题。先在服务器执行：

```bash
cd /opt/apps/schedule-sync
bash deploy/diagnose-gateway.sh
```

重点检查：

- `/opt/apps/hiremate/Caddyfile` 是否已经包含 `schedule-sync.zenithy.art` 站点块。
- `hiremate-caddy` 是否 reload 成功。
- `schedule-sync-api` 和 `hiremate-caddy` 是否都在 `shared_gateway` 网络。
- `docker logs hiremate-caddy` 是否有 ACME/certificate 错误。

常用修复命令：

```bash
docker network connect shared_gateway schedule-sync-api || true
docker exec hiremate-caddy caddy validate --config /etc/caddy/Caddyfile
docker exec hiremate-caddy caddy reload --config /etc/caddy/Caddyfile
docker logs hiremate-caddy --tail=200
curl -vkI https://schedule-sync.zenithy.art/api/health
```

## API

- `GET /api/health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/devices`
- `POST /api/devices/register`
- `PUT /api/devices/{device_id}`
- `DELETE /api/devices/{device_id}`
- `POST /api/sync/push`
- `POST /api/sync/pull`
- `GET /api/sync/bootstrap`

## 同步协议

推荐 payload 使用 envelope v1：

```json
{
  "entity_type": "daily_task",
  "sync_id": "uuid",
  "sync_version": 1,
  "sync_deleted": false,
  "relation_sync_ids": {},
  "data": {
    "sync_id": "uuid",
    "title": "学习 Python"
  }
}
```

云端仍兼容旧的扁平 payload。

## 安全边界

- 所有同步数据按 Token 中的 `user_id` 隔离。
- 客户端上传的 `user_id` 会被忽略。
- `ai_api_key`、`api_key`、`secret_key` 等敏感字段会被清洗。
- 登录、注册、刷新 Token 有内存限速。

## 冒烟测试

```bash
cd /opt/apps/schedule-sync
bash deploy/smoke-test.sh http://127.0.0.1:18130
```

冒烟测试覆盖：

- 账号 A/B 注册登录。
- A 设备 push，A 另一设备 pull。
- B 账号无法看到 A 数据。
- 删除变更同步。
- AI Key 不入库。

## 更新与备份

更新：

```bash
cd /opt/apps/schedule-sync
bash deploy/update-server.sh
```

备份：

```bash
cd /opt/apps/schedule-sync
bash deploy/backup-postgres.sh
```

## 维护文档

- `任务记忆文档.md`：当前状态、关键决策、维护边界。
- `项目文件索引.md`：人类可读文件索引。
- `项目文件索引.json`：机器可读文件索引。
