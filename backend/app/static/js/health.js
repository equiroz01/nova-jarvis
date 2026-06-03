// health.js — Clock and server health check

let API;

function startClock() {
  const el = document.getElementById('clock');
  function tick() {
    const d = new Date();
    el.textContent = d.toTimeString().slice(0, 8);
  }
  tick();
  setInterval(tick, 1000);
}

async function checkHealth() {
  const dot = document.getElementById('statusDot');
  const txt = document.getElementById('statusText');
  try {
    const r = await fetch(API + '/health', { signal: AbortSignal.timeout(5000) });
    if (r.ok) { dot.className = 'status-dot online'; txt.textContent = 'CONNECTED'; }
    else throw 0;
  } catch {
    dot.className = 'status-dot offline'; txt.textContent = 'OFFLINE';
  }
}

export function init(config) {
  API = config.API;
  startClock();
  checkHealth();
  setInterval(checkHealth, 15000);
}
