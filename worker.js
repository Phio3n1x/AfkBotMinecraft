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
  console.error('Could not read config.json: ' + error.message);
  process.exit(1);
}

const bots = new Map();
const stopping = new Set();
let shuttingDown = false;

// stdout is reserved for JSON events consumed by main.py; human logs go to stderr.
function emit(event) {
  process.stdout.write(JSON.stringify(event) + '\n');
}

function currentConfig() {
  try { return JSON.parse(fs.readFileSync(configPath, 'utf8')); }
  catch { return config; }
}

function formatReason(reason) {
  if (typeof reason === 'string') return reason;
  try { return JSON.stringify(reason); } catch { return String(reason); }
}

function publishStatus() {
  const now = Date.now();
  const snapshot = [];
  for (const [name, entry] of bots.entries()) {
    let position = null;
    if (entry.bot && entry.bot.entity && entry.bot.entity.position) {
      const p = entry.bot.entity.position;
      position = { x: p.x, y: p.y, z: p.z };
    }
    snapshot.push({
      name,
      status: entry.status || 'unknown',
      location: entry.location || null,
      joined_at: entry.joinedAt || null,
      uptime_seconds: entry.joinedAt && entry.status === 'online'
        ? Math.max(0, (now - entry.joinedAt) / 1000) : null,
      disconnects: entry.disconnects || 0,
      last_error: entry.lastError || null,
      position,
      ping: entry.bot && entry.bot.player ? entry.bot.player.ping : null
    });
  }
  emit({
    type: 'status',
    timestamp: now,
    server: {
      host: config.host || '127.0.0.1',
      port: Number(config.port || 25565),
      version: config.version || 'auto'
    },
    bots: snapshot
  });
}

function startBot(username, locationName, index = 0) {
  if (shuttingDown) return;
  const existing = bots.get(username);
  if (existing && existing.bot && ['connecting', 'online', 'leaving'].includes(existing.status)) {
    console.error('[' + username + '] Already ' + existing.status + '.');
    return;
  }
  stopping.delete(username);
  config = currentConfig();
  const host = String(config.host || '127.0.0.1');
  const port = Number(config.port || 25565);
  const version = config.version || 'auto';
  const loc = locationName && config.locations ? config.locations[locationName] : null;
  console.error('[' + username + '] Connecting to ' + host + ':' + port + ' (version: ' + version + ')...');
  if (locationName && loc) {
    console.error('[' + username + '] Preferred location ' + locationName + ': x=' + loc.x + ' y=' + loc.y + ' z=' + loc.z);
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
    console.error('[' + username + '] Could not create bot: ' + error.message);
    bots.set(username, {
      bot: null, status: 'error', location: locationName || null,
      disconnects: existing ? existing.disconnects || 0 : 0, lastError: error.message
    });
    publishStatus();
    return;
  }

  bots.set(username, {
    bot, status: 'connecting', location: locationName || null,
    disconnects: existing ? existing.disconnects || 0 : 0,
    lastError: null, joinedAt: null
  });
  publishStatus();

  bot.once('spawn', () => {
    const entry = bots.get(username);
    if (entry && entry.bot === bot) {
      entry.status = 'online';
      entry.joinedAt = Date.now();
      entry.lastError = null;
    }
    console.error('[' + username + '] Joined; standing idle. Teleport manually if needed.');
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
          console.error('[' + username + '] Sending configured post-join command.');
          bot.chat(command.startsWith('/') ? command : '/' + command);
        }
      }, 1500);
    }
    publishStatus();
  });

  bot.on('kicked', reason => {
    const formatted = formatReason(reason);
    console.error('[' + username + '] Kicked: ' + formatted);
    const entry = bots.get(username);
    if (entry && entry.bot === bot) entry.lastError = 'Kicked: ' + formatted;
    publishStatus();
  });
  bot.on('error', error => {
    console.error('[' + username + '] Error: ' + error.message);
    const entry = bots.get(username);
    if (entry && entry.bot === bot) {
      entry.status = 'error';
      entry.lastError = error.message;
    }
    publishStatus();
  });
  bot.on('end', reason => {
    const entry = bots.get(username);
    const formatted = formatReason(reason || 'Disconnected');
    console.error('[' + username + '] Disconnected: ' + formatted);
    if (entry && entry.bot === bot) {
      entry.bot = null;
      entry.status = stopping.has(username) || shuttingDown ? 'offline' : 'disconnected';
      entry.disconnects = (entry.disconnects || 0) + 1;
      entry.lastError = formatted;
      entry.joinedAt = null;
    }
    publishStatus();
    if (!shuttingDown && !stopping.has(username) && config.reconnect !== false) {
      setTimeout(() => startBot(username, locationName, index),
        Math.max(1, Number(config.reconnect_delay_seconds ?? 10)) * 1000);
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
    publishStatus();
  } else {
    bots.set(username, {
      bot: null, status: 'offline', location: entry ? entry.location : null,
      disconnects: entry ? entry.disconnects || 0 : 0,
      lastError: entry ? entry.lastError || null : null
    });
    console.error('[' + username + '] Already offline.');
    publishStatus();
  }
}

function printStatus() {
  publishStatus();
}

const input = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
input.on('line', line => {
  let message;
  try { message = JSON.parse(line); }
  catch { console.error('Received invalid command from Python controller.'); return; }

  if (message.action === 'config') {
    config = message.config || currentConfig();
    publishStatus();
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

setInterval(publishStatus, 1000);
publishStatus();

process.on('SIGINT', () => {
  shuttingDown = true;
  for (const [name, entry] of bots.entries()) {
    stopping.add(name);
    if (entry.bot) entry.bot.quit('Controller shutting down');
  }
  process.exit(0);
});
