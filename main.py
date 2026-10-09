"""Python launcher for the Mineflayer AFK bot worker."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"


def main() -> int:
    if not shutil.which("node"):
        print("Node.js 18+ is required. Install Node.js, then try again.", file=sys.stderr)
        return 1
    if not CONFIG_PATH.exists():
        print("Missing config.json. Copy config.example.json to config.json and edit it first.", file=sys.stderr)
        return 1
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not read config.json: {exc}", file=sys.stderr)
        return 1

    if not isinstance(config.get("bots"), list) or not config["bots"]:
        print("config.json must contain a non-empty 'bots' list.", file=sys.stderr)
        return 1
    if not (1 <= int(config.get("port", 25565)) <= 65535):
        print("Port must be between 1 and 65535.", file=sys.stderr)
        return 1

    worker = ROOT / "worker.js"
    if not worker.exists():
        print("worker.js is missing from the project.", file=sys.stderr)
        return 1
    try:
        result = subprocess.run(["node", str(worker)], cwd=ROOT, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
