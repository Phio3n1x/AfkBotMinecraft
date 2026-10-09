# AfkBotMinecraft

Interactive Python terminal controller for multiple Minecraft Java Edition AFK clients, using Mineflayer.

## Target server

The starter configuration targets **Purpur 1.20.1** in offline-mode. Set `version` to `1.20.1` for that server. The project can be configured for other Mineflayer-supported Java versions; compatibility is not universal and needs testing against the target server, proxy, and plugins.

## Requirements

- Python 3.10+
- Node.js 18+
- A Minecraft Java server you own or are authorized to use

## Setup (Windows)

1. Download or clone this repository.
2. Install Node.js 18 or newer.
3. Open a terminal in the project folder and run `npm install`.
4. Run `python main.py`. It creates a local `config.json` if one does not exist.
5. Edit `config.json` to set your server `host`, `port`, and `version` (use `1.20.1` for the target server).
6. Restart `python main.py` after editing server settings.

## Terminal commands

- `help` — show all commands
- `config` — show server settings
- `config version 1.20.1` — select protocol version for new connections
- `bot add AfkIron` — save a bot username
- `bots` — show runtime bot statuses
- `join AfkIron` — connect one bot
- `join AfkIron iron` — connect a bot and associate it with a saved location
- `joinall` — connect all saved bots, staggered by `join_delay_seconds`
- `leave AfkIron` or `leave all` — disconnect bot(s)
- `locations add iron 120 64 -35` — save coordinates
- `locations list` — list saved coordinates
- `locations remove iron` — remove a saved location
- `assign AfkIron iron` — remember a bot's preferred location
- `unassign AfkIron` — clear a bot's preferred location
- `exit` — stop the worker

## Locations and teleporting

Saved locations are labels and coordinate notes. The bot does **not** automatically teleport or pathfind to them; join it, then teleport it using your server's permitted method. If you want a bot chat command after spawn, set `post_join_command` in local `config.json`, e.g. `/tp {name} {x} {y} {z}` only if the bot is permitted to execute that command. Placeholders: `{name}`, `{x}`, `{y}`, `{z}`, `{location}`. Leave this blank by default.

## Notes

- Add and test one bot before increasing the count.
- Bot usernames must be unique and acceptable to the server.
- `config.json` is git-ignored. Do not commit passwords or tokens.
- Offline-mode servers may accept arbitrary usernames; only connect to servers you own or are authorized to test.
- This starter scaffold has not been integration-tested against your live server yet.
