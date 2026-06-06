// tasks.js — Background task badge monitoring via SSE

let API;
let _evtSource = null;
let _debounce = null;

function updateBadge(count) {
  const badge = document.getElementById('taskBadge');
  if (!badge) return;
  if (count > 0) {
    badge.textContent = count;
    badge.style.display = 'block';
  } else {
    badge.style.display = 'none';
  }
}

async function fetchActiveTasks() {
  try {
    const r = await fetch(API + '/api/tasks?status=running');
    const running = await r.json();
    const q = await fetch(API + '/api/tasks?status=queued');
    const queued = await q.json();
    updateBadge(running.length + queued.length);
  } catch (e) {
    // Silent fail
  }
}

function debouncedFetch() {
  if (_debounce) clearTimeout(_debounce);
  _debounce = setTimeout(fetchActiveTasks, 300);
}

function connectSSE() {
  if (_evtSource) _evtSource.close();
  _evtSource = new EventSource(API + '/api/tasks/stream');
  _evtSource.onmessage = () => debouncedFetch();
  _evtSource.onerror = () => {
    _evtSource.close();
    setTimeout(connectSSE, 5000);
  };
}

export function init(config) {
  API = config.API;
  fetchActiveTasks();
  connectSSE();
}
