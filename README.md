# AfkBotMinecraft

A local web dashboard for managing multiple Minecraft Java Edition AFK clients, powered by Python and Mineflayer.

## Features

- Responsive dark web UI with live bot statuses, uptime, ping, and coordinates when available.
- Add bots, connect one or all, and disconnect one or all from the browser.
- Save locations, assign them to bots, and remove locations.
- Edit server host, port, Minecraft version, join delay, and reconnect settings.
- Status updates about once per second.
- Keeps `main.py` as the optional terminal controller.

## Target server

The starter configuration targets **Purpur 1.20.1** in offline-mode. Set `version` to `1.20.1` for that server. Other Mineflayer-supported Java versions may work, but compatibility should be tested against the target server, proxy, and plugins.

## Requirements

- Python 3.10+
- Node.js 18+
- A Minecraft Java server you own or are authorized to use

## Setup (Windows)

1. Download or clone this repository.
2. Install Node.js 18 or newer.
3. Open a terminal in the project folder and run `npm install`.
4. Run `python web_panel.py`.
5. The panel should open in your browser at `http://127.0.0.1:8765`. If it does not, open that address manually.
6. On first launch, `config.json` is created from `config.example.json`. Set your server `host`, `port`, and `version` in the settings page or edit the file and restart the app.

## Web panel

- **Overview:** live bot stats, current bot status, and saved locations.
- **Bot management:** add bot names, connect bots, connect all saved bots with a delay, disconnect individual bots, or disconnect all.
- **Farms and locations:** save X/Y/Z coordinates, assign a preferred location to a bot, unassign a bot, and remove locations.
- **Server settings:** change host, port, version, reconnect behavior, and connection delays.

The web server binds to `127.0.0.1` only by default. This is intentional: the panel has no login system, so do not change the bind address or expose it to a LAN/public network without adding authentication and appropriate access controls. Stop the app with `Ctrl+C` in its terminal.

## Optional terminal controller

Run `python main.py` if you prefer the terminal interface. Commands include `help`, `bot add AfkIron`, `join AfkIron`, `joinall`, `leave all`, `locations add iron 120 64 -35`, `assign AfkIron iron`, and `exit`.

## Locations and teleporting

Saved locations are labels and coordinate notes. Bots do **not** automatically teleport or pathfind to saved coordinates. If you configure `post_join_command` in `config.json`, a chat command can be sent after spawn, e.g. `/tp {name} {x} {y} {z}`, only if the bot is allowed to execute it. For actual autonomous movement, a pathfinding feature needs to be added and tested separately.

## Notes

- Test with one bot before increasing the count.
- Bot usernames must be unique and acceptable to the server.
- `config.json` and `node_modules/` are local and should not be committed.
- Offline-mode servers may accept arbitrary usernames; only connect to servers you own or are authorized to test.
- The web panel is a new feature and should be tested locally before relying on it for long sessions.
