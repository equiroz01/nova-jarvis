// waveform.js — SVG arc reactor, waveform bars

let waveRAF;

export function buildReactorSVG() {
  const c = 120; // center
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 240 240');
  svg.setAttribute('class', 'reactor-svg');

  // Defs: glow filter
  const defs = document.createElementNS(ns, 'defs');
  const filter = document.createElementNS(ns, 'filter');
  filter.id = 'glow'; filter.setAttribute('x', '-50%'); filter.setAttribute('y', '-50%');
  filter.setAttribute('width', '200%'); filter.setAttribute('height', '200%');
  const blur = document.createElementNS(ns, 'feGaussianBlur'); blur.setAttribute('stdDeviation', '4'); blur.setAttribute('result', 'g');
  const merge = document.createElementNS(ns, 'feMerge');
  const m1 = document.createElementNS(ns, 'feMergeNode'); m1.setAttribute('in', 'g');
  const m2 = document.createElementNS(ns, 'feMergeNode'); m2.setAttribute('in', 'SourceGraphic');
  merge.append(m1, m2); filter.append(blur, merge); defs.append(filter);

  // Radial gradient for core
  const grad = document.createElementNS(ns, 'radialGradient'); grad.id = 'coreGrad';
  [{o:0,c:'rgba(200,240,255,0.95)'},{o:0.3,c:'rgba(0,180,255,0.8)'},{o:0.6,c:'rgba(0,120,255,0.4)'},{o:1,c:'rgba(0,60,180,0)'}]
    .forEach(s => { const st = document.createElementNS(ns, 'stop'); st.setAttribute('offset', s.o); st.setAttribute('stop-color', s.c); grad.append(st); });
  defs.append(grad);
  svg.append(defs);

  function circle(r, sw, cls, dash) {
    const el = document.createElementNS(ns, 'circle');
    el.setAttribute('cx', c); el.setAttribute('cy', c); el.setAttribute('r', r);
    el.setAttribute('fill', 'none'); el.setAttribute('stroke', '#0af');
    el.setAttribute('stroke-width', sw); el.setAttribute('filter', 'url(#glow)');
    if (cls) el.setAttribute('class', cls);
    if (dash) el.setAttribute('stroke-dasharray', dash);
    el.setAttribute('opacity', '0.7');
    return el;
  }

  // Ring 1: Outer dashed ring
  svg.append(circle(112, 2.5, 'ring-outer', '8 4'));

  // Gear segments
  const gearG = document.createElementNS(ns, 'g');
  gearG.setAttribute('class', 'ring-gears');
  for (let i = 0; i < 12; i++) {
    const rect = document.createElementNS(ns, 'rect');
    const angle = i * 30;
    rect.setAttribute('x', c - 7); rect.setAttribute('y', 3);
    rect.setAttribute('width', 14); rect.setAttribute('height', 10);
    rect.setAttribute('rx', 1);
    rect.setAttribute('fill', 'rgba(0,170,255,0.15)');
    rect.setAttribute('stroke', '#0af'); rect.setAttribute('stroke-width', 0.8);
    rect.setAttribute('transform', 'rotate(' + angle + ' ' + c + ' ' + c + ')');
    rect.setAttribute('filter', 'url(#glow)');
    gearG.append(rect);
  }
  svg.append(gearG);

  // Ring 2: Mid ring
  svg.append(circle(95, 2, 'ring-mid'));

  // Radial bars
  const barG = document.createElementNS(ns, 'g');
  barG.setAttribute('class', 'ring-bars');
  for (let i = 0; i < 24; i++) {
    const line = document.createElementNS(ns, 'line');
    const angle = i * 15;
    const len = (i % 3 === 0) ? 20 : (i % 2 === 0) ? 14 : 9;
    const r1 = 75; const r2 = r1 + len;
    const rad = angle * Math.PI / 180;
    line.setAttribute('x1', c + r1 * Math.sin(rad)); line.setAttribute('y1', c - r1 * Math.cos(rad));
    line.setAttribute('x2', c + r2 * Math.sin(rad)); line.setAttribute('y2', c - r2 * Math.cos(rad));
    line.setAttribute('stroke', '#0af'); line.setAttribute('stroke-width', (i % 3 === 0) ? 3 : 2);
    line.setAttribute('opacity', (i % 3 === 0) ? '0.8' : '0.4');
    line.setAttribute('stroke-linecap', 'round');
    line.setAttribute('filter', 'url(#glow)');
    barG.append(line);
  }
  svg.append(barG);

  // Ring 3: Inner ring
  svg.append(circle(70, 1.5, '', ''));

  // Ring 4: Core ring
  const coreRing = circle(52, 2, '');
  coreRing.setAttribute('opacity', '0.9');
  svg.append(coreRing);

  // Core glow circle
  const core = document.createElementNS(ns, 'circle');
  core.setAttribute('cx', c); core.setAttribute('cy', c); core.setAttribute('r', 42);
  core.setAttribute('fill', 'url(#coreGrad)');
  core.setAttribute('class', 'core-glow');
  svg.append(core);

  // Sweep line
  const sweepG = document.createElementNS(ns, 'g');
  sweepG.setAttribute('class', 'ring-sweep');
  const sweepLine = document.createElementNS(ns, 'line');
  sweepLine.setAttribute('x1', c); sweepLine.setAttribute('y1', c);
  sweepLine.setAttribute('x2', c + 105); sweepLine.setAttribute('y2', c);
  sweepLine.setAttribute('stroke', 'rgba(0,200,255,0.6)');
  sweepLine.setAttribute('stroke-width', 1.5);
  sweepLine.setAttribute('filter', 'url(#glow)');
  sweepG.append(sweepLine);
  svg.append(sweepG);

  return svg;
}

function initArcTicks() {
  document.querySelectorAll('.arc-reactor').forEach(container => {
    if (container.querySelector('.reactor-svg')) return;
    const svg = buildReactorSVG();
    container.insertBefore(svg, container.firstChild);
    if (!container.querySelector('.arc-core')) {
      const label = document.createElement('div');
      label.className = 'arc-core' + (container.classList.contains('arc-reactor-sm') ? ' arc-core-sm' : '');
      label.textContent = container.classList.contains('arc-reactor-sm') ? 'N' : 'NOVA';
      container.appendChild(label);
    }
  });
}

function initWaveform() {
  const wf = document.getElementById('waveform');
  if (wf) {
    for (let i = 0; i < 24; i++) {
      const bar = document.createElement('div');
      bar.className = 'waveform-bar';
      wf.appendChild(bar);
    }
  }
}

export function startLiveWaveform(analyserNode) {
  const wf = document.getElementById('waveform');
  if (!wf) return;
  wf.classList.add('active');
  const bars = wf.querySelectorAll('.waveform-bar');
  function draw() {
    if (!analyserNode) return;
    const data = new Uint8Array(analyserNode.frequencyBinCount);
    analyserNode.getByteFrequencyData(data);
    bars.forEach((b, i) => {
      const val = data[i] || 0;
      b.style.height = Math.max(4, (val / 255) * 28) + 'px';
    });
    waveRAF = requestAnimationFrame(draw);
  }
  draw();
}

export function stopLiveWaveform() {
  const wf = document.getElementById('waveform');
  if (!wf) return;
  wf.classList.remove('active');
  cancelAnimationFrame(waveRAF);
  wf.querySelectorAll('.waveform-bar').forEach(b => { b.style.height = '4px'; });
}

export function init() {
  initWaveform();
  initArcTicks();
}
