# qBittorrent 自动汇报

这个脚本会监控 qBittorrent 中的种子，在种子添加满 5 分 15 秒（315 秒）后调用一次 `reannounce` API，强制向 tracker 汇报。

每个种子只处理一次，已处理的 torrent hash 会保存到持久化状态文件中。服务重启后不会重复汇报。

## 一键部署到服务器

服务器需要安装 Docker 和 Docker Compose Plugin。

### 1. 配置 qBittorrent

```bash
cp .env.example .env
nano .env
```

至少修改：

```dotenv
QBIT_URL=http://host.docker.internal:8080
QBIT_USERNAME=admin
QBIT_PASSWORD=你的密码
```

上面的地址适用于 qBittorrent 运行在 Docker 宿主机上的情况。Compose 已经配置了 `host.docker.internal` 到宿主机的映射。

如果 qBittorrent 运行在另一个 Docker Compose 服务中，把 `QBIT_URL` 改成对应的服务名和端口，例如：

```dotenv
QBIT_URL=http://qbittorrent:8080
```

### 2. 启动并设置持久常驻

```bash
chmod +x deploy.sh
./deploy.sh
```

底层执行的是：

```bash
docker compose up -d --build
```

容器设置了 `restart: unless-stopped`，服务器重启或容器异常退出后会自动恢复。

### 3. 查看、停止和更新

```bash
# 查看实时日志
docker compose logs -f qbit-auto-reannounce

# 查看运行状态
docker compose ps

# 停止服务
docker compose down

# 拉取新代码后重新构建
docker compose up -d --build
```

状态文件保存在 Docker volume `qbit-auto-reannounce-data` 中。

## 直接运行 Python

如果不使用 Docker：

```bash
export QBIT_URL=http://127.0.0.1:8080
export QBIT_USERNAME=admin
export QBIT_PASSWORD='你的密码'
python3 qbit_auto_reannounce.py
```

## 配置项

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `QBIT_URL` | `http://127.0.0.1:8080` | qBittorrent WebUI 地址 |
| `QBIT_USERNAME` | 无 | WebUI 用户名 |
| `QBIT_PASSWORD` | 无 | WebUI 密码 |
| `QBIT_DELAY` | `315` | 添加后等待秒数 |
| `QBIT_INTERVAL` | `5` | 轮询间隔秒数 |

## GitHub 发布

创建 GitHub 仓库后，在本地执行：

```bash
git init
git add .
git commit -m "Add qBittorrent auto reannounce service"
git branch -M main
git remote add origin git@github.com:你的用户名/你的仓库名.git
git push -u origin main
```

不要提交 `.env`，其中包含 qBittorrent 密码。
