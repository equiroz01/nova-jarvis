// tasks.js — Background task monitoring via SSE

let API;
let _evtSource = null;

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
    const tasks = await r.json();
    const queued = await fetch(API + '/api/tasks?status=queued');
    const queuedTasks = await queued.json();
    updateBadge(tasks.length + queuedTasks.length);
  } catch (e) {
    // Silent fail
  }
}

function connectSSE() {
  if (_evtSource) _evtSource.close();
  _evtSource = new EventSource(API + '/api/tasks/stream');

  _evtSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === 'task_update' || data.type === 'task_created') {
        fetchActiveTasks();
      } else if (data.type === 'task_complete' || data.type === 'task_failed' || data.type === 'task_cancelled') {
        fetchActiveTasks();
      }
    } catch (err) {
      // ignore parse errors
    }
  };

  _evtSource.onerror = () => {
    // Reconnect after 5s
    _evtSource.close();
    setTimeout(connectSSE, 5000);
  };
}

export function init(config) {
  API = config.API;
  fetchActiveTasks();
  connectSSE();
}
