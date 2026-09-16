#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "已创建 .env，请先填写 qBittorrent 地址、用户名和密码后重新运行此脚本。"
  exit 1
fi

docker compose up -d --build
docker compose ps
echo
echo "服务已启动。查看日志：docker compose logs -f qbit-auto-reannounce"
