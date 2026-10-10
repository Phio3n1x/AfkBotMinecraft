"""Local web panel for the AFK Minecraft bot manager (standard library only)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"
WEB_PATH = ROOT / "web" / "index.html"
HOST = "127.0.0.1"
PORT = 8765
LOCK = threading.RLock()
WORKER_LOCK = threading.Lock()
RUNTIME: dict[str, Any] = {"type": "status", "timestamp": 0, "server": {}, "bots": []}
worker: subprocess.Popen[str] | None = None
http_server: ThreadingHTTPServer | None = None


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        CONFIG_PATH.write_text(json.dumps(example, indent=2) + "\n", encoding="utf-8")
        print("Created config.json from config.example.json.")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config.setdefault("bots", [])
    config.setdefault("locations", {})
    config.setdefault("assignments", {})
    return config


def save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def worker_reader(stream: Any) -> None:
    global RUNTIME
    for line in stream:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "status":
            with LOCK:
                RUNTIME = event


def send_worker(payload: dict[str, Any]) -> None:
    if worker is None or worker.poll() is not None or worker.stdin is None:
        raise RuntimeError("Bot worker is not running. Restart web_panel.py.")
    with WORKER_LOCK:
        worker.stdin.write(json.dumps(payload) + "\n")
        worker.stdin.flush()


def get_state() -> dict[str, Any]:
    config = load_config()
    with LOCK:
        runtime = json.loads(json.dumps(RUNTIME))
    runtime_bots = {item.get("name"): item for item in runtime.get("bots", [])}
    all_names = list(dict.fromkeys(config.get("bots", []) + list(runtime_bots)))
    bots = []
    for name in all_names:
        entry = runtime_bots.get(name, {})
        bots.append({
            "name": name,
            "status": entry.get("status", "not started"),
            "location": entry.get("location") or config.get("assignments", {}).get(name),
            "uptime_seconds": entry.get("uptime_seconds"),
            "ping": entry.get("ping"),
            "position": entry.get("position"),
            "disconnects": entry.get("disconnects", 0),
            "last_error": entry.get("last_error"),
            "saved": name in config.get("bots", []),
        })
    return {
        "server": {
            "host": config.get("host", "127.0.0.1"),
            "port": config.get("port", 25565),
            "version": config.get("version", "auto"),
            "reconnect": config.get("reconnect", True),
            "reconnect_delay_seconds": config.get("reconnect_delay_seconds", 10),
            "join_delay_seconds": config.get("join_delay_seconds", 3),
            "post_join_command": config.get("post_join_command", ""),
        },
        "bots": bots,
        "locations": config.get("locations", {}),
        "assignments": config.get("assignments", {}),
        "updated_at": runtime.get("timestamp", 0),
        "worker_running": worker is not None and worker.poll() is None,
    }


def do_action(data: dict[str, Any]) -> dict[str, Any]:
    action = str(data.get("action", ""))
    config = load_config()

    if action == "bot_add":
        name = str(data.get("name", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", name):
            raise ValueError("اسم بات باید ۱ تا ۱۶ کاراکتر و فقط شامل حروف انگلیسی، عدد یا _ باشد.")
        if name in config["bots"]:
            raise ValueError("این بات از قبل ثبت شده است.")
        config["bots"].append(name)
        save_config(config)
        send_worker({"action": "config", "config": config})

    elif action == "join":
        name = str(data.get("name", "")).strip()
        if name not in config["bots"]:
            raise ValueError("اول بات را به فهرست اضافه کن.")
        location = data.get("location") or config["assignments"].get(name)
        if location and location not in config["locations"]:
            raise ValueError("لوکیشن انتخاب‌شده وجود ندارد.")
        send_worker({"action": "join", "name": name, "location": location, "config": config})

    elif action == "join_all":
        send_worker({"action": "joinall", "config": config})

    elif action == "leave":
        name = str(data.get("name", ""))
        if name != "all" and name not in config["bots"]:
            raise ValueError("بات در فهرست ذخیره‌شده نیست.")
        send_worker({"action": "leave", "name": name})

    elif action == "location_add":
        name = str(data.get("name", "")).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", name):
            raise ValueError("نام لوکیشن فقط می‌تواند حروف انگلیسی، عدد، _ یا - داشته باشد.")
        try:
            coords = {axis: float(data[axis]) for axis in ("x", "y", "z")}
        except (KeyError, TypeError, ValueError):
            raise ValueError("مختصات x، y و z را به‌صورت عدد وارد کن.")
        if any(abs(v) > 30_000_000 for v in coords.values()):
            raise ValueError("یکی از مختصات خارج از محدودهٔ مجاز است.")
        config["locations"][name] = coords
        save_config(config)
        send_worker({"action": "config", "config": config})

    elif action == "location_remove":
        name = str(data.get("name", ""))
        if name not in config["locations"]:
            raise ValueError("لوکیشن پیدا نشد.")
        del config["locations"][name]
        config["assignments"] = {bot: loc for bot, loc in config["assignments"].items() if loc != name}
        save_config(config)
        send_worker({"action": "config", "config": config})

    elif action == "assign":
        bot_name, location = str(data.get("bot", "")), str(data.get("location", ""))
        if bot_name not in config["bots"]:
            raise ValueError("بات ابتدا باید ثبت شود.")
        if location not in config["locations"]:
            raise ValueError("لوکیشن پیدا نشد.")
        config["assignments"][bot_name] = location
        save_config(config)
        send_worker({"action": "config", "config": config})

    elif action == "unassign":
        bot_name = str(data.get("bot", ""))
        config["assignments"].pop(bot_name, None)
        save_config(config)
        send_worker({"action": "config", "config": config})

    elif action == "settings":
        host = str(data.get("host", "")).strip()
        try:
            port = int(data.get("port", 25565))
        except (TypeError, ValueError):
            raise ValueError("پورت باید عدد باشد.")
        version = str(data.get("version", "1.20.1")).strip()
        if not host or len(host) > 253 or any(ch.isspace() for ch in host):
            raise ValueError("آدرس سرور معتبر نیست.")
        if not 1 <= port <= 65535:
            raise ValueError("پورت باید بین 1 تا 65535 باشد.")
        if version.lower() != "auto" and not re.fullmatch(r"\d+\.\d+(?:\.\d+)?", version):
            raise ValueError("نسخه را مثل 1.20.1 یا auto وارد کن.")
        try:
            join_delay = max(0, min(60, int(data.get("join_delay_seconds", 3))))
            reconnect_delay = max(1, min(300, int(data.get("reconnect_delay_seconds", 10))))
        except (TypeError, ValueError):
            raise ValueError("زمان تأخیرها باید عدد صحیح باشد.")
        config.update({
            "host": host, "port": port, "version": version,
            "reconnect": bool(data.get("reconnect", True)),
            "join_delay_seconds": join_delay,
            "reconnect_delay_seconds": reconnect_delay,
            "post_join_command": str(data.get("post_join_command", config.get("post_join_command", ""))).strip(),
        })
        save_config(config)
        send_worker({"action": "config", "config": config})

    elif action == "refresh":
        send_worker({"action": "status"})
    else:
        raise ValueError("دستور ناشناخته است.")

    return {"ok": True, "state": get_state()}


class Handler(BaseHTTPRequestHandler):
    server_version = "AfkBotPanel/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep request noise out of the console; the UI is the primary interface.
        return

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == "/api/state":
            try:
                self.send_json(200, {"ok": True, "state": get_state()})
            except Exception as exc:
                self.send_json(500, {"ok": False, "error": str(exc)})
            return
        if route in ("/", "/index.html"):
            try:
                body = WEB_PATH.read_bytes()
            except OSError:
                self.send_error(500, "web/index.html is missing")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/action":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 32_000:
                raise ValueError("درخواست خالی یا بیش از حد بزرگ است.")
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("درخواست معتبر نیست.")
            result = do_action(data)
            self.send_json(200, result)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.send_json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self.send_json(500, {"ok": False, "error": str(exc)})


def main() -> int:
    global worker, http_server
    if not shutil.which("node"):
        print("Node.js 18+ is required. Install Node.js, then try again.", file=sys.stderr)
        return 1
    if not WEB_PATH.exists():
        print("web/index.html is missing.", file=sys.stderr)
        return 1
    try:
        config = load_config()
        if not 1 <= int(config.get("port", 25565)) <= 65535:
            raise ValueError("port must be between 1 and 65535")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print("Could not load config: " + str(exc), file=sys.stderr)
        return 1

    worker = subprocess.Popen(
        ["node", str(ROOT / "worker.js")], cwd=ROOT,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=None,
        text=True, encoding="utf-8", bufsize=1,
    )
    assert worker.stdout is not None
    threading.Thread(target=worker_reader, args=(worker.stdout,), daemon=True).start()

    try:
        http_server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        if worker.poll() is None:
            worker.terminate()
        print(f"Could not start web panel on http://{HOST}:{PORT}: {exc}", file=sys.stderr)
        return 1

    url = f"http://{HOST}:{PORT}"
    print("AFK Bot web panel is running at " + url)
    print("This panel only listens on this computer (127.0.0.1). Press Ctrl+C to stop.")
    try:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        http_server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping web panel and bots...")
    finally:
        http_server.server_close()
        if worker.poll() is None:
            try:
                send_worker({"action": "shutdown"})
                worker.wait(timeout=5)
            except Exception:
                worker.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
