'use strict';

const fs = require('fs');
const path = require('path');
const mineflayer = require('mineflayer');

const configPath = path.join(__dirname, 'config.json');
if (!fs.existsSync(configPath)) {
  console.error('Missing config.json. Copy config.example.json to config.json first.');
  process.exit(1);
}

let config;
try {
  config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
} catch (error) {
  console.error(`Could not read config.json: ${error.message}`);
  process.exit(1);
}

if (!Array.isArray(config.bots) || config.bots.length === 0) {
  console.error("Config field 'bots' must be a non-empty array.");
  process.exit(1);
}

const host = String(config.host || '127.0.0.1');
const port = Number(config.port || 25565);
const version = config.version || 'auto';
const joinDelay = Math.max(0, Number(config.join_delay_seconds ?? 3)) * 1000;
const reconnectDelay = Math.max(1, Number(config.reconnect_delay_seconds ?? 10)) * 1000;
const shouldReconnect = config.reconnect !== false;
const postJoinCommand = String(config.post_join_command || '').trim();
const stopping = new Set();

function startBot(username, index) {
  if (stopping.has(username)) return;
  console.log(`[${username}] Connecting to ${host}:${port} (version: ${version})...`);
  let bot;
  try {
    bot = mineflayer.createBot({
      host,
      port,
      username: String(username),
      version: version === 'auto' ? false : version,
      hideErrors: false
    });
  } catch (error) {
    console.error(`[${username}] Could not create bot: ${error.message}`);
    scheduleReconnect(username, index);
    return;
  }

  let joined = false;
  bot.once('spawn', () => {
    joined = true;
    console.log(`[${username}] Joined and standing AFK.`);
    if (postJoinCommand) {
      setTimeout(() => {
        if (bot.player) {
          console.log(`[${username}] Sending configured post-join command.`);
          bot.chat(postJoinCommand.startsWith('/') ? postJoinCommand : `/${postJoinCommand}`);
        }
      }, 1500);
    }
  });

  bot.on('kicked', (reason) => console.warn(`[${username}] Kicked: ${formatReason(reason)}`));
  bot.on('error', (error) => console.error(`[${username}] Error: ${error.message}`));
  bot.on('end', () => {
    console.log(`[${username}] Disconnected${joined ? '' : ' before joining'}.`);
    scheduleReconnect(username, index);
  });
}

function scheduleReconnect(username, index) {
  if (!shouldReconnect || stopping.has(username)) return;
  setTimeout(() => startBot(username, index), reconnectDelay + index * 250);
}

function formatReason(reason) {
  if (typeof reason === 'string') return reason;
  try { return JSON.stringify(reason); } catch { return String(reason); }
}

process.on('SIGINT', () => {
  console.log('\nStopping bot worker...');
  for (const name of config.bots) stopping.add(String(name));
  process.exit(0);
});

config.bots.forEach((username, index) => {
  setTimeout(() => startBot(String(username), index), index * joinDelay);
});
