#!/usr/bin/env python3
"""
Reannounce qBittorrent torrents once, 5 minutes and 15 seconds after adding.

Configuration is read from environment variables:
  QBIT_URL       qBittorrent WebUI URL, default: http://127.0.0.1:8080
  QBIT_USERNAME  WebUI username
  QBIT_PASSWORD  WebUI password
  QBIT_DELAY     Delay in seconds, default: 315
  QBIT_INTERVAL  Poll interval in seconds, default: 5
  QBIT_STATE     State file path, default: ./qbit_reannounce_state.json

Example:
  QBIT_USERNAME=admin QBIT_PASSWORD=secret python qbit_auto_reannounce.py
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener


DEFAULT_URL = "http://127.0.0.1:8080"
DEFAULT_DELAY = 5 * 60 + 15
DEFAULT_INTERVAL = 5


class QbitClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.opener = build_opener()
        self.logged_in = False

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        data: dict[str, str] | None = None,
    ) -> tuple[int, bytes]:
        body = urlencode(data).encode() if data is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"User-Agent": "qbit-auto-reannounce/1.0"},
        )
        with self.opener.open(request, timeout=15) as response:
            return response.status, response.read()

    def login(self) -> None:
        status, body = self._request(
            "/api/v2/auth/login",
            method="POST",
            data={"username": self.username, "password": self.password},
        )
        if status != 200 or body.decode(errors="replace").strip() != "Ok.":
            raise RuntimeError(
                f"qBittorrent 登录失败，HTTP {status}: "
                f"{body.decode(errors='replace').strip()}"
            )
        self.logged_in = True
        logging.info("已登录 qBittorrent: %s", self.base_url)

    def _call_authenticated(
        self,
        path: str,
        *,
        method: str = "GET",
        data: dict[str, str] | None = None,
    ) -> bytes:
        if not self.logged_in:
            self.login()

        try:
            _, body = self._request(path, method=method, data=data)
            return body
        except HTTPError as error:
            if error.code not in (401, 403):
                raise
            logging.warning("登录状态已失效，尝试重新登录")
            self.logged_in = False
            self.login()
            _, body = self._request(path, method=method, data=data)
            return body

    def torrents(self) -> list[dict[str, Any]]:
        body = self._call_authenticated("/api/v2/torrents/info")
        value = json.loads(body.decode("utf-8"))
        if not isinstance(value, list):
            raise RuntimeError("qBittorrent 返回的种子列表格式不正确")
        return value

    def reannounce(self, torrent_hash: str) -> None:
        self._call_authenticated(
            "/api/v2/torrents/reannounce",
            method="POST",
            data={"hashes": torrent_hash},
        )


def load_state(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, list):
            raise ValueError("state must be a list")
        return {str(item) for item in value}
    except (OSError, json.JSONDecodeError, ValueError) as error:
        logging.warning("无法读取状态文件 %s，将从空状态开始: %s", path, error)
        return set()


def save_state(path: Path, processed: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(sorted(processed), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def get_config() -> tuple[str, str, str, int, float, Path]:
    url = os.environ.get("QBIT_URL", DEFAULT_URL)
    username = os.environ.get("QBIT_USERNAME", "")
    password = os.environ.get("QBIT_PASSWORD", "")
    delay = int(os.environ.get("QBIT_DELAY", str(DEFAULT_DELAY)))
    interval = float(os.environ.get("QBIT_INTERVAL", str(DEFAULT_INTERVAL)))
    state_path = Path(
        os.environ.get("QBIT_STATE", "qbit_reannounce_state.json")
    ).expanduser()

    if not username or not password:
        raise ValueError("请设置 QBIT_USERNAME 和 QBIT_PASSWORD")
    if delay < 0:
        raise ValueError("QBIT_DELAY 不能小于 0")
    if interval <= 0:
        raise ValueError("QBIT_INTERVAL 必须大于 0")
    return url, username, password, delay, interval, state_path


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        url, username, password, delay, interval, state_path = get_config()
    except ValueError as error:
        logging.error("%s", error)
        return 2

    client = QbitClient(url, username, password)
    processed = load_state(state_path)
    stopping = False

    def stop_handler(signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True
        logging.info("收到停止信号，准备退出")

    signal.signal(signal.SIGINT, stop_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop_handler)

    logging.info(
        "开始监控，延迟 %s 秒，轮询间隔 %s 秒，状态文件: %s",
        delay,
        interval,
        state_path,
    )

    while not stopping:
        try:
            now = time.time()
            for torrent in client.torrents():
                torrent_hash = str(torrent.get("hash", "")).strip()
                added_on = torrent.get("added_on")
                name = str(torrent.get("name", torrent_hash))

                if not torrent_hash or torrent_hash in processed:
                    continue
                if not isinstance(added_on, (int, float)) or added_on <= 0:
                    logging.warning("跳过缺少 added_on 的种子: %s", name)
                    continue
                if now - added_on < delay:
                    continue

                logging.info("强制汇报: %s [%s]", name, torrent_hash)
                client.reannounce(torrent_hash)
                processed.add(torrent_hash)
                save_state(state_path, processed)
                logging.info("强制汇报完成: %s", name)

        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError, ValueError) as error:
            logging.error("本轮处理失败: %s", error)

        for _ in range(max(1, int(interval * 10))):
            if stopping:
                break
            time.sleep(0.1)

    save_state(state_path, processed)
    logging.info("已退出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
