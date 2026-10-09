# AfkBotMinecraft

A small local controller for running multiple Minecraft AFK client bots on a server you own or administer.

## Current status

Initial scaffold. The Python launcher reads `config.json` and starts a Mineflayer worker (Node.js) that connects bots, keeps them idle, and can optionally send a one-time chat command after joining (for example, a server-specific teleport command).

> Minecraft protocol support depends on the server version and server configuration. Mineflayer can usually auto-detect the protocol, but plugins, proxies, authentication mode, and server rules can affect connection.

## Requirements

- Python 3.10+
- Node.js 18+
- A Minecraft Java Edition server you own or are authorized to test

## Setup

1. Install Node.js 18 or newer.
2. Copy `config.example.json` to `config.json` and edit the server address, port, bot names, and optional post-join command.
3. In this directory, run `npm install`.
4. Run `python main.py`.

`config.json` is ignored by Git so local settings are not accidentally committed. Do not put passwords, access tokens, or other secrets in the repository.

## Notes

- Start with one bot and confirm it can join before increasing `bots`.
- `post_join_command` is optional and server-specific; leave it blank if you want to teleport the bot manually.
- This initial version targets Java Edition servers. Bedrock support is not included.
