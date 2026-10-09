'use strict';

const fs = require('fs');
const path = require('path');
const readline = require('readline');
const mineflayer = require('mineflayer');

const configPath = path.join(__dirname, 'config.json');
if (!fs.existsSync(configPath)) {
  console.error('Missing config.json. Run main.py to create it from config.example.json.');
  process.exit(1);
}

let config;
try {
  config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
} catch (error) {
  console.error(`Could not read config.json: ${error.message}`);
  process.exit(1);
}

const bots = new Map();
const stopping = new Set();
let shuttingDown = false;

function currentConfig() {
  try { return JSON.parse(fs.readFileSync(configPath, 'utf8')); }
  catch { return config; }
}

function startBot(username, locationName, index = 0) {
  if (shuttingDown) return;
  const existing = bots.get(username);
  if (existing && existing.bot && ['connecting', 'online', 'leaving'].includes(existing.status)) {
    console.log(`[${username}] Already ${existing.status}.`);
    return;
  }
  stopping.delete(username);
  config = currentConfig();
  const host = String(config.host || '127.0.0.1');
  const port = Number(config.port || 25565);
  const version = config.version || 'auto';
  const loc = locationName && config.locations ? config.locations[locationName] : null;
  console.log(`[${username}] Connecting to ${host}:${port} (version: ${version})...`);
  if (locationName && loc) {
    console.log(`[${username}] Preferred location '${locationName}': x=${loc.x} y=${loc.y} z=${loc.z}`);
  }

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
    bots.set(username, { bot: null, status: 'error', location: locationName || null });
    return;
  }

  bots.set(username, { bot, status: 'connecting', location: locationName || null });
  bot.once('spawn', () => {
    const entry = bots.get(username);
    if (entry && entry.bot === bot) entry.status = 'online';
    console.log(`[${username}] Joined; standing idle. Teleport manually if needed.`);
    const template = String(config.post_join_command || '').trim();
    if (template) {
      const command = template
        .replaceAll('{name}', username)
        .replaceAll('{x}', loc ? String(loc.x) : '')
        .replaceAll('{y}', loc ? String(loc.y) : '')
        .replaceAll('{z}', loc ? String(loc.z) : '')
        .replaceAll('{location}', locationName || '');
      setTimeout(() => {
        if (bot.player && !stopping.has(username)) {
          console.log(`[${username}] Sending configured post-join command.`);
          bot.chat(command.startsWith('/') ? command : `/${command}`);
        }
      }, 1500);
    }
  });

  bot.on('kicked', reason => console.warn(`[${username}] Kicked: ${formatReason(reason)}`));
  bot.on('error', error => {
    console.error(`[${username}] Error: ${error.message}`);
    const entry = bots.get(username);
    if (entry && entry.bot === bot) entry.status = 'error';
  });
  bot.on('end', () => {
    console.log(`[${username}] Disconnected.`);
    const entry = bots.get(username);
    if (entry && entry.bot === bot) {
      entry.bot = null;
      entry.status = stopping.has(username) || shuttingDown ? 'offline' : 'disconnected';
    }
    if (!shuttingDown && !stopping.has(username) && config.reconnect !== false) {
      setTimeout(() => startBot(username, locationName, index), Math.max(1, Number(config.reconnect_delay_seconds ?? 10)) * 1000);
    }
  });
}

function leaveBot(username) {
  if (username === 'all') {
    for (const name of bots.keys()) leaveBot(name);
    return;
  }
  stopping.add(username);
  const entry = bots.get(username);
  if (entry && entry.bot) {
    entry.status = 'leaving';
    entry.bot.quit('Disconnected by terminal command');
  } else {
    bots.set(username, { bot: null, status: 'offline', location: null });
    console.log(`[${username}] Already offline.`);
  }
}

function printStatus() {
  if (!bots.size) {
    console.log('No bots started yet. Add names with "bot add <name>", then use join.');
    return;
  }
  for (const [name, entry] of bots.entries()) {
    console.log(`[${name}] ${entry.status || 'unknown'}${entry.location ? ` | location: ${entry.location}` : ''}`);
  }
}

function formatReason(reason) {
  if (typeof reason === 'string') return reason;
  try { return JSON.stringify(reason); } catch { return String(reason); }
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on('line', line => {
  let message;
  try { message = JSON.parse(line); }
  catch { console.error('Received invalid command from Python controller.'); return; }

  if (message.action === 'config') {
    config = message.config || currentConfig();
  } else if (message.action === 'join') {
    startBot(String(message.name), message.location || null);
  } else if (message.action === 'joinall') {
    config = message.config || currentConfig();
    const names = Array.isArray(config.bots) ? config.bots : [];
    const delay = Math.max(0, Number(config.join_delay_seconds ?? 3)) * 1000;
    names.forEach((name, index) => {
      const loc = config.assignments ? config.assignments[name] : null;
      setTimeout(() => startBot(String(name), loc || null, index), index * delay);
    });
  } else if (message.action === 'leave') {
    leaveBot(String(message.name));
  } else if (message.action === 'status') {
    printStatus();
  } else if (message.action === 'shutdown') {
    shuttingDown = true;
    for (const name of bots.keys()) {
      stopping.add(name);
      const entry = bots.get(name);
      if (entry && entry.bot) entry.bot.quit('Controller shutting down');
    }
    setTimeout(() => process.exit(0), 250);
  }
});

process.on('SIGINT', () => {
  shuttingDown = true;
  for (const [name, entry] of bots.entries()) {
    stopping.add(name);
    if (entry.bot) entry.bot.quit('Controller shutting down');
  }
  process.exit(0);
});
