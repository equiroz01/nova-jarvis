// messages.js — Message display, typing indicator, welcome screen

import { renderMarkdown } from './markdown.js';

export function addMessage(text, who) {
  const container = document.getElementById('chatContainer');
  const group = document.createElement('div');
  group.className = 'msg-group ' + who;

  const label = document.createElement('div');
  label.className = 'msg-label';
  label.textContent = who === 'user' ? 'YOU' : 'N.O.V.A.';

  const bubble = document.createElement('div');
  bubble.className = 'msg ' + (who === 'user' ? 'user-msg' : 'jarvis-msg');
  if (who === 'jarvis') {
    bubble.appendChild(renderMarkdown(text));
  } else {
    bubble.textContent = text;
  }

  const time = document.createElement('div');
  time.className = 'msg-time';
  time.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  group.appendChild(label);
  group.appendChild(bubble);
  group.appendChild(time);

  // Insert before typing indicator
  const typing = document.getElementById('typingIndicator');
  container.insertBefore(group, typing);
  container.scrollTop = container.scrollHeight;
}

export function addStreamMessage() {
  const container = document.getElementById('chatContainer');
  const group = document.createElement('div');
  group.className = 'msg-group jarvis';

  const label = document.createElement('div');
  label.className = 'msg-label';
  label.textContent = 'N.O.V.A.';

  const bubble = document.createElement('div');
  bubble.className = 'msg jarvis-msg';
  bubble.id = 'stream-bubble';

  const time_el = document.createElement('div');
  time_el.className = 'msg-time';
  time_el.textContent = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

  group.appendChild(label);
  group.appendChild(bubble);
  group.appendChild(time_el);

  const typing = document.getElementById('typingIndicator');
  container.insertBefore(group, typing);
  return bubble;
}

export function updateStreamMessage(bubble, text) {
  if (!bubble) return;
  while (bubble.firstChild) bubble.removeChild(bubble.firstChild);
  bubble.appendChild(renderMarkdown(text));
  const container = document.getElementById('chatContainer');
  container.scrollTop = container.scrollHeight;
}

export function showTyping() {
  document.getElementById('typingIndicator').classList.add('active');
  document.getElementById('chatContainer').scrollTop =
    document.getElementById('chatContainer').scrollHeight;
}

export function hideTyping() {
  document.getElementById('typingIndicator').classList.remove('active');
}

export function hideWelcome() {
  const w = document.getElementById('welcome');
  if (w) w.style.display = 'none';
}

export function init() {
  // No initialization needed — all functions are called by other modules
}
