"""Interactive terminal controller for AFK Minecraft bots."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"


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
  join <name> [location]             Join one bot; location is optional
  joinall                            Join all saved bots with a delay
  leave <name|all>                   Disconnect one or all bots
  locations add <name> <x> <y> <z>  Save a named location
  locations list                     List saved locations
  locations remove <name>            Remove a saved location
  assign <bot> <location>            Set a bot's preferred location
  unassign <bot>                     Clear a bot's preferred location
  exit                               Stop all bots and quit

Locations are saved coordinates for reference. By default, bots do not teleport or pathfind;
you can teleport them manually after joining. If you configure post_join_command in config.json,
the command is sent as bot chat after spawn. Only use a command your bot is allowed to run.
""")


def main() -> int:
    if not __import__("shutil").which("node"):
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
        text=True,
        encoding="utf-8",
    )
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
                    config["version"] = parts[2]
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
