"""Interactive terminal controller and live dashboard for AFK Minecraft bots."""
from __future__ import annotations

import json
import os
import select
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"
STATUS_LOCK = threading.Lock()
LATEST_STATUS: dict[str, Any] = {"bots": [], "server": {}}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        example = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        CONFIG_PATH.write_text(json.dumps(example, indent=2) + "\n", encoding="utf-8")
        print("Created config.json from the example. Edit host/port before joining a server.")
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    config.setdefault("bots", [])
    config.setdefault("locations", {})
    config.setdefault("assignments", {})
    return config


def save_config(config: dict[str, Any]) -> None:
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")


def read_worker_events(stream: Any) -> None:
    """Read the worker's JSON-only stdout without blocking the command prompt."""
    global LATEST_STATUS
    for line in stream:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "status":
            with STATUS_LOCK:
                LATEST_STATUS = event


def send(worker: subprocess.Popen[str], payload: dict[str, Any]) -> None:
    if worker.stdin is None or worker.poll() is not None:
        print("Bot worker is not running.")
        return
    worker.stdin.write(json.dumps(payload) + "\n")
    worker.stdin.flush()


def help_text() -> None:
    print("""
Commands:
  help                              Show this help
  config                            Show server/version configuration
  config version <auto|1.20.1>      Change protocol version (takes effect on next join)
  bot add <name>                    Save a bot username
  bots                              List saved bots and runtime status
  dashboard                         Open live dashboard (press q to return)
  join <name> [location]             Join one bot; location is optional
  joinall                            Join all saved bots with a delay
  leave <name|all>                   Disconnect one or all bots
  locations add <name> <x> <y> <z>  Save a named location
  locations list                     List saved locations
  locations remove <name>            Remove a saved location
  assign <bot> <location>            Set a bot's preferred location
  unassign <bot>                     Clear a bot's preferred location
  exit                               Stop all bots and quit

Locations are saved coordinates for reference. By default, bots do not teleport or pathfind.
""")


def format_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "—"
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02}:{minutes:02}:{secs:02}"


def snapshot() -> dict[str, Any]:
    with STATUS_LOCK:
        return json.loads(json.dumps(LATEST_STATUS))


def render_dashboard(config: dict[str, Any]) -> None:
    state = snapshot()
    server = state.get("server", {})
    bots = state.get("bots", [])
    os.system("cls" if os.name == "nt" else "clear")
    print("=" * 88)
    print(" AFK BOT MANAGER  |  LIVE DASHBOARD")
    print("=" * 88)
    print(f" Server: {server.get('host', config.get('host', '?'))}:{server.get('port', config.get('port', '?'))}"
          f"   Version: {server.get('version', config.get('version', 'auto'))}")
    print(f" Updated: {time.strftime('%H:%M:%S')}   Bots: {len(bots)}")
    print("-" * 88)
    print(f"{'BOT':<18} {'STATUS':<14} {'LOCATION':<16} {'UPTIME':<10} {'PING':>6}  {'POSITION':<20}")
    print("-" * 88)
    if not bots:
        print("No bot sessions yet. Exit dashboard and use 'bot add <name>' then 'join <name>'.")
    for bot in bots:
        pos = bot.get("position")
        position = "—" if not pos else f"{pos.get('x', 0):.1f}, {pos.get('y', 0):.1f}, {pos.get('z', 0):.1f}"
        ping = bot.get("ping")
        ping_text = f"{ping} ms" if isinstance(ping, (int, float)) and ping > 0 else "—"
        uptime = format_duration(bot.get("uptime_seconds"))
        print(f"{bot.get('name', '?')[:17]:<18} {bot.get('status', 'unknown')[:13]:<14} "
              f"{str(bot.get('location') or '—')[:15]:<16} {uptime:<10} {ping_text:>6}  {position:<20}")
        if bot.get("last_error"):
            print(f"  Last event/error: {str(bot['last_error'])[:160]}")
    print("-" * 88)
    print("Refreshes automatically. Press q to return to the command prompt (on non-Windows terminals, press q then Enter).")


def dashboard(config: dict[str, Any]) -> None:
    try:
        while True:
            render_dashboard(config)
            # A short polling loop keeps the display live while allowing q to exit.
            if os.name == "nt":
                import msvcrt
                deadline = time.monotonic() + 1.0
                pressed_q = False
                while time.monotonic() < deadline:
                    if msvcrt.kbhit():
                        key = msvcrt.getwch()
                        if key.lower() == "q":
                            pressed_q = True
                            break
                    time.sleep(0.05)
                if pressed_q:
                    break
            else:
                ready, _, _ = select.select([sys.stdin], [], [], 1.0)
                if ready and sys.stdin.readline().strip().lower() == "q":
                    break
    except (KeyboardInterrupt, OSError):
        pass
    print("\nReturned to command prompt.")


def print_status() -> None:
    bots = snapshot().get("bots", [])
    if not bots:
        print("No bot sessions yet. Add names with 'bot add <name>', then use join.")
        return
    for bot in bots:
        pos = bot.get("position")
        pos_text = "—" if not pos else f"x={pos['x']:.1f} y={pos['y']:.1f} z={pos['z']:.1f}"
        uptime = format_duration(bot.get("uptime_seconds"))
        print(f"[{bot.get('name')}] {bot.get('status')} | location: {bot.get('location') or '—'}"
              f" | uptime: {uptime} | pos: {pos_text}")


def main() -> int:
    if not shutil.which("node"):
        print("Node.js 18+ is required. Install Node.js, then try again.", file=sys.stderr)
        return 1
    if not (ROOT / "worker.js").exists():
        print("worker.js is missing.", file=sys.stderr)
        return 1
    try:
        config = load_config()
        if not (1 <= int(config.get("port", 25565)) <= 65535):
            raise ValueError("port must be between 1 and 65535")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Could not load config: {exc}", file=sys.stderr)
        return 1

    worker = subprocess.Popen(
        ["node", str(ROOT / "worker.js")],
        cwd=ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    assert worker.stdout is not None
    threading.Thread(target=read_worker_events, args=(worker.stdout,), daemon=True).start()
    print(f"AFK Bot controller ready for {config.get('host')}:{config.get('port')}. Type 'help'.")
    try:
        while worker.poll() is None:
            try:
                raw = input("afk> ").strip()
            except EOFError:
                raw = "exit"
            if not raw:
                continue
            parts = raw.split()
            command = parts[0].lower()

            if command in {"help", "?"}:
                help_text()
            elif command == "config":
                if len(parts) == 3 and parts[1].lower() == "version":
                    version = parts[2]
                    if version.lower() not in {"auto", "1.20.1"} and not version[0].isdigit():
                        print("Version must be 'auto' or a Minecraft version such as '1.20.1'.")
                        continue
                    config["version"] = version
                    save_config(config)
                    send(worker, {"action": "config", "config": config})
                    print(f"Version set to {config['version']}; it applies to newly joined bots.")
                else:
                    print(f"Host: {config.get('host')}  Port: {config.get('port')}  Version: {config.get('version', 'auto')}")
                    print(f"Join delay: {config.get('join_delay_seconds', 3)} seconds")
            elif command == "bot" and len(parts) == 3 and parts[1].lower() == "add":
                name = parts[2]
                if name in config["bots"]:
                    print(f"Bot '{name}' is already saved.")
                else:
                    config["bots"].append(name)
                    save_config(config)
                    send(worker, {"action": "config", "config": config})
                    print(f"Saved bot '{name}'. Use: join {name}")
            elif command == "bots":
                send(worker, {"action": "status"})
                time.sleep(0.15)
                print_status()
            elif command == "dashboard":
                send(worker, {"action": "status"})
                dashboard(config)
            elif command == "join" and len(parts) in (2, 3):
                name = parts[1]
                location = parts[2] if len(parts) == 3 else config["assignments"].get(name)
                if name not in config["bots"]:
                    print(f"Unknown bot '{name}'. Add it first with: bot add {name}")
                elif location and location not in config["locations"]:
                    print(f"Unknown location '{location}'. Use: locations list")
                else:
                    send(worker, {"action": "join", "name": name, "location": location, "config": config})
            elif command == "joinall" and len(parts) == 1:
                send(worker, {"action": "joinall", "config": config})
            elif command == "leave" and len(parts) == 2:
                send(worker, {"action": "leave", "name": parts[1]})
            elif command == "locations" and len(parts) == 2 and parts[1].lower() == "list":
                if not config["locations"]:
                    print("No locations saved.")
                for name, loc in config["locations"].items():
                    print(f"{name}: x={loc['x']} y={loc['y']} z={loc['z']}")
            elif command == "locations" and len(parts) == 6 and parts[1].lower() == "add":
                name = parts[2]
                try:
                    loc = {"x": float(parts[3]), "y": float(parts[4]), "z": float(parts[5])}
                except ValueError:
                    print("Coordinates must be numbers.")
                    continue
                config["locations"][name] = loc
                save_config(config)
                send(worker, {"action": "config", "config": config})
                print(f"Saved location '{name}': {loc}")
            elif command == "locations" and len(parts) == 3 and parts[1].lower() == "remove":
                name = parts[2]
                if name not in config["locations"]:
                    print(f"Unknown location '{name}'.")
                else:
                    del config["locations"][name]
                    for bot, assigned in list(config["assignments"].items()):
                        if assigned == name:
                            del config["assignments"][bot]
                    save_config(config)
                    send(worker, {"action": "config", "config": config})
                    print(f"Removed location '{name}'.")
            elif command == "assign" and len(parts) == 3:
                bot, location = parts[1], parts[2]
                if bot not in config["bots"]:
                    print(f"Unknown bot '{bot}'. Add it first.")
                elif location not in config["locations"]:
                    print(f"Unknown location '{location}'.")
                else:
                    config["assignments"][bot] = location
                    save_config(config)
                    send(worker, {"action": "config", "config": config})
                    print(f"{bot} is assigned to {location}. Use 'join {bot}' to connect it.")
            elif command == "unassign" and len(parts) == 2:
                config["assignments"].pop(parts[1], None)
                save_config(config)
                send(worker, {"action": "config", "config": config})
                print(f"Cleared preferred location for {parts[1]}.")
            elif command in {"exit", "quit"}:
                send(worker, {"action": "shutdown"})
                break
            else:
                print("Unknown command. Type 'help' for the command list.")
    except KeyboardInterrupt:
        print("\nStopping...")
        send(worker, {"action": "shutdown"})
    finally:
        if worker.poll() is None:
            try:
                worker.wait(timeout=8)
            except subprocess.TimeoutExpired:
                worker.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
