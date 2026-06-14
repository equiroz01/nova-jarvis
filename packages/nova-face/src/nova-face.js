/**
 * nova-face.js — NOVA animated face, framework-agnostic ES module.
 *
 * Self-contained: it injects its own DOM (canvas + cinematic overlays) and CSS
 * into the container you give it. No build step, no dependencies.
 *
 * Usage (web):
 *   import { NovaFace } from './nova-face.js';
 *   const face = new NovaFace({ container: '#nova', assetBase: '/static/face/assets/' });
 *   face.setEmotion('happy');
 *   face.setMode('speaking');     // then push amplitude:
 *   face.setLevel(0.6);           // 0..1, call repeatedly while speaking
 *   face.idle();
 *   face.think(true);             // thinking / backend-busy animation
 *
 * The face is driven imperatively. The host app is responsible for *when*
 * to speak/think and (optionally) for pushing the audio amplitude via setLevel().
 * If you'd rather have the module read the audio itself, use connectAnalyser/
 * connectStream/connectAudioElement.
 *
 * Events: face.on('ready'|'modechange'|'emotionchange'|'status', cb)
 */

export const NAMES = ["angry","blink","cool","dizzy","happy","heartbeat","loading","love",
  "neutral","sad","sleepy","speaking_scan","speaking_soft","surprised","wide","wink"];
export const EMOTIONS = ["neutral","happy","love","cool","sad","angry","surprised","sleepy","dizzy"];
export const MODES = ["idle","speaking","listening","thinking"];

const TINT = {
  neutral:[54,214,255], happy:[80,224,255], love:[255,95,162], cool:[90,200,255],
  sad:[74,144,217], angry:[255,120,42], surprised:[120,230,255], sleepy:[60,110,150],
  dizzy:[170,120,255], thinking:[120,170,255]
};
const EYE  = [{x:0.330,y:0.510},{x:0.672,y:0.510}];
const DOTS = [{x:0.432,y:0.512},{x:0.500,y:0.512},{x:0.568,y:0.512}];
const THINK_TXT = ['PROCESANDO','CONSULTANDO BACKEND','RAZONANDO','BUSCANDO DATOS'];
const MSZ = 720; // resolución del recorte circular cacheado

let _styleInjected = false;
function injectStyle(){
  if (_styleInjected) return; _styleInjected = true;
  const css = `
  .nova-face-root{position:relative;width:100%;height:100%;overflow:hidden;
    --nova-cyan:#36d6ff;background:radial-gradient(120% 120% at 50% 12%,#0d1622 0%,#070a0f 58%,#03050a 100%)}
  .nova-face-root canvas{display:block;width:100%;height:100%;touch-action:none}
  .nova-fx{position:absolute;inset:0;pointer-events:none}
  .nova-fx.vig{background:radial-gradient(120% 100% at 50% 42%,transparent 52%,rgba(0,0,0,.28) 82%,rgba(0,0,0,.6) 100%)}
  .nova-fx.scan{background:repeating-linear-gradient(to bottom,rgba(255,255,255,.025) 0 1px,transparent 1px 3px);mix-blend-mode:overlay;opacity:.5}
  .nova-fx.grain{opacity:.05;mix-blend-mode:overlay;background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='120' height='120'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/></filter><rect width='100%25' height='100%25' filter='url(%23n)'/></svg>")}
  .nova-corner{position:absolute;width:26px;height:26px;border:1.5px solid rgba(54,214,255,.35);pointer-events:none}
  .nova-corner.tl{top:16px;left:16px;border-right:0;border-bottom:0}
  .nova-corner.tr{top:16px;right:16px;border-left:0;border-bottom:0}
  .nova-corner.bl{bottom:16px;left:16px;border-right:0;border-top:0}
  .nova-corner.br{bottom:16px;right:16px;border-left:0;border-top:0}
  .nova-status{position:absolute;top:14px;left:0;right:0;text-align:center;font:10.5px/1 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
    letter-spacing:.28em;color:#4d6678;text-transform:uppercase;pointer-events:none}
  @media (prefers-reduced-motion:reduce){.nova-fx.scan,.nova-fx.grain{display:none}}
  `;
  const s = document.createElement('style');
  s.setAttribute('data-nova-face','');
  s.textContent = css;
  document.head.appendChild(s);
}

export class NovaFace {
  constructor(opts = {}){
    const {
      container,
      assetBase = './assets/',
      emotion = 'neutral',
      particles = true,
      hud = true,                 // esquinas + viñeta + scan + grain + texto estado
      status = true,              // texto de estado integrado
      reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches,
      autoStart = true,
      defaultStatus = 'SYSTEM ONLINE · NEURAL CORE STABLE',
    } = opts;

    const el = typeof container === 'string' ? document.querySelector(container) : container;
    if (!el) throw new Error('[NovaFace] container no encontrado');
    injectStyle();

    this.opts = { assetBase, particles, hud, status, reducedMotion, defaultStatus };
    this._listeners = {};
    this._destroyed = false;
    this.isCoarse = matchMedia('(pointer: coarse)').matches;

    // ---- DOM ----
    this.root = document.createElement('div');
    this.root.className = 'nova-face-root';
    this.cv = document.createElement('canvas');
    this.root.appendChild(this.cv);
    if (hud){
      for (const c of ['vig','scan','grain']){ const d=document.createElement('div'); d.className='nova-fx '+c; this.root.appendChild(d); }
      for (const c of ['tl','tr','bl','br']){ const d=document.createElement('span'); d.className='nova-corner '+c; this.root.appendChild(d); }
    }
    if (hud && status){
      this.statusEl = document.createElement('div'); this.statusEl.className='nova-status';
      this.statusEl.textContent = defaultStatus; this.root.appendChild(this.statusEl);
    }
    el.appendChild(this.root);
    this.ctx = this.cv.getContext('2d');

    // ---- estado ----
    this.S = {
      mode:'idle', emotion,
      level:0, targetLevel:0,
      blinkUntil:0, nextBlink:0,
      tilt:{x:0,y:0,tx:0,ty:0},
      tint:(TINT[emotion]||TINT.neutral).slice(), tintTo:(TINT[emotion]||TINT.neutral).slice(),
    };
    this._displayed='neutral'; this._incoming=null;
    this._lastStatus='';
    this.NBINS = this.isCoarse ? 40 : 56;
    this._spectrum = new Float32Array(this.NBINS);
    this._specPhase = 0;
    this._particles = [];

    // ---- audio (opcional, modo self-driven) ----
    this.AC=null; this.analyser=null; this._dataArr=null; this._freqArr=null;
    this._rafAudio=0; this._micStream=null; this._mediaSrc=null;

    // ---- assets ----
    this.imgs={}; this.masked={};
    this._loadAssets(assetBase);

    // ---- layout ----
    this._cssW=0; this._cssH=0; this._faceSize=0; this._cx=0; this._cy=0; this._dpr=1;
    this._ro = new ResizeObserver(()=>this._resize());
    this._ro.observe(this.root);
    this._onOrient = ()=>setTimeout(()=>this._resize(),150);
    window.addEventListener('orientationchange', this._onOrient);

    // parallax (solo puntero fino)
    if (!this.isCoarse){
      this._onMove = (e)=>{ const r=this.root.getBoundingClientRect();
        this.S.tilt.tx=((e.clientX-r.left)/r.width-0.5); this.S.tilt.ty=((e.clientY-r.top)/r.height-0.5); };
      this._onLeave = ()=>{ this.S.tilt.tx=0; this.S.tilt.ty=0; };
      this.root.addEventListener('pointermove', this._onMove);
      this.root.addEventListener('pointerleave', this._onLeave);
    }

    // pausa en pestaña oculta
    this._onVis = ()=>{ if (document.hidden) this.stop(); else this.start(); };
    document.addEventListener('visibilitychange', this._onVis);

    this._t0 = performance.now(); this._running=false;
    this._resize();
    if (autoStart) this.start();
  }

  // ---------------- API pública ----------------
  setEmotion(e){ if (!EMOTIONS.includes(e)) return this; this.S.emotion=e; this._emit('emotionchange', e); return this; }
  getEmotion(){ return this.S.emotion; }

  setMode(m){ if (!MODES.includes(m)) return this; this.S.mode=m; this._emit('modechange', m); return this; }
  getMode(){ return this.S.mode; }

  idle(){ return this.setMode('idle'); }
  speak(){ return this.setMode('speaking'); }
  listen(){ return this.setMode('listening'); }
  think(on=true){ return this.setMode(on?'thinking':'idle'); }

  /** Empuja amplitud 0..1 (lip-sync / reactividad). Llamar repetidamente mientras habla/escucha. */
  setLevel(v){ this.S.targetLevel = Math.max(0, Math.min(1, +v||0)); return this; }

  /** Estado textual del HUD (si status:true). null => restaura el por defecto. */
  setStatus(txt){ this._setStatus(txt==null ? this.opts.defaultStatus : txt); return this; }

  on(evt, cb){ (this._listeners[evt] ||= []).push(cb); return this; }
  off(evt, cb){ if (this._listeners[evt]) this._listeners[evt]=this._listeners[evt].filter(f=>f!==cb); return this; }
  _emit(evt, data){ (this._listeners[evt]||[]).forEach(f=>{ try{f(data);}catch(e){console.error('[NovaFace]',e);} }); }

  start(){ if (this._running||this._destroyed) return this; this._running=true; this._t0=performance.now(); requestAnimationFrame(this._frame); return this; }
  stop(){ this._running=false; return this; }

  // ---- audio self-driven (opcional) ----
  _ensureAC(){ if(!this.AC) this.AC=new (window.AudioContext||window.webkitAudioContext)(); if(this.AC.state==='suspended') this.AC.resume(); return this.AC; }
  _setAnalyser(a){ this.analyser=a; this._dataArr=new Uint8Array(a.fftSize); this._freqArr=new Uint8Array(a.frequencyBinCount); }
  _startAudioLoop(gain){
    cancelAnimationFrame(this._rafAudio);
    const loop=()=>{
      this.analyser.getByteTimeDomainData(this._dataArr);
      let s=0; for(let i=0;i<this._dataArr.length;i++){ const v=(this._dataArr[i]-128)/128; s+=v*v; }
      let l=Math.max(0,(Math.sqrt(s/this._dataArr.length)-0.012))*(gain||9);
      this.setLevel(Math.min(1, Math.pow(l,0.85)));
      this._rafAudio=requestAnimationFrame(loop);
    }; loop();
  }
  /** Conecta un AnalyserNode existente y deja que el módulo calcule la amplitud. */
  connectAnalyser(analyser, {gain=9, mode='speaking'}={}){ this._setAnalyser(analyser); this.setMode(mode); this._startAudioLoop(gain); return this; }
  /** Conecta un MediaStream (p.ej. micrófono). */
  connectStream(stream, {gain=13, mode='listening'}={}){ const ac=this._ensureAC(); const src=ac.createMediaStreamSource(stream); const a=ac.createAnalyser(); a.fftSize=1024; a.smoothingTimeConstant=0.45; src.connect(a); this._micStream=stream; return this.connectAnalyser(a,{gain,mode}); }
  /** Conecta un <audio>/<video> en reproducción. */
  connectAudioElement(elm, {gain=9, mode='speaking'}={}){ const ac=this._ensureAC(); const a=ac.createAnalyser(); a.fftSize=1024; a.smoothingTimeConstant=0.5; if(!this._mediaSrc){ this._mediaSrc=ac.createMediaElementSource(elm); } this._mediaSrc.connect(a); a.connect(ac.destination); return this.connectAnalyser(a,{gain,mode}); }
  disconnectAudio(){ cancelAnimationFrame(this._rafAudio); this.analyser=null; if(this._micStream){ this._micStream.getTracks().forEach(t=>t.stop()); this._micStream=null; } this.setLevel(0); return this; }

  destroy(){
    this._destroyed=true; this._running=false;
    cancelAnimationFrame(this._rafAudio);
    this._ro.disconnect();
    window.removeEventListener('orientationchange', this._onOrient);
    document.removeEventListener('visibilitychange', this._onVis);
    if (this._onMove){ this.root.removeEventListener('pointermove', this._onMove); this.root.removeEventListener('pointerleave', this._onLeave); }
    if (this._micStream) this._micStream.getTracks().forEach(t=>t.stop());
    this.root.remove();
  }

  // ---------------- interno ----------------
  _loadAssets(base){
    NAMES.forEach(n=>{
      const im=new Image(); im.decoding='async';
      const done=()=>{ try{ this.masked[n]=this._buildMask(im); }catch(e){} if(n==='neutral') this._emit('ready'); };
      im.onload=done; im.src=base+'NOVA_'+n+'.png';
      if (im.decode) im.decode().then(done).catch(()=>{});
      this.imgs[n]=im;
    });
  }
  _buildMask(im){
    const c=document.createElement('canvas'); c.width=c.height=MSZ; const x=c.getContext('2d');
    x.drawImage(im,0,0,MSZ,MSZ);
    const half=MSZ/2;
    const g=x.createRadialGradient(half,half,half*0.82, half,half,half*0.95);
    g.addColorStop(0,'rgba(0,0,0,1)'); g.addColorStop(1,'rgba(0,0,0,0)');
    x.globalCompositeOperation='destination-in'; x.fillStyle=g; x.fillRect(0,0,MSZ,MSZ);
    return c;
  }
  _getMasked(name){ if(this.masked[name]) return this.masked[name]; const im=this.imgs[name]; if(im&&im.complete&&im.naturalWidth){ this.masked[name]=this._buildMask(im); return this.masked[name]; } return null; }

  _resize(){
    const r=this.root.getBoundingClientRect();
    this._cssW=Math.max(1,r.width); this._cssH=Math.max(1,r.height);
    this._dpr=Math.min(window.devicePixelRatio||1,2);
    this.cv.width=Math.round(this._cssW*this._dpr); this.cv.height=Math.round(this._cssH*this._dpr);
    this.ctx.setTransform(this._dpr,0,0,this._dpr,0,0);
    this._faceSize=Math.min(Math.min(this._cssW,this._cssH)*(this.isCoarse?0.82:0.74),600);
    this._cx=this._cssW/2; this._cy=this._cssH/2;
    this._spawnParticles();
  }
  _spawnParticles(){
    const o=this.opts;
    const base = (o.reducedMotion||!o.particles) ? 0 : (this.isCoarse?26:54);
    const n=Math.round(base*Math.min(1.4,(this._cssW*this._cssH)/(900*600)));
    this._particles=new Array(n).fill(0).map(()=>({x:Math.random()*this._cssW,y:Math.random()*this._cssH,z:0.3+Math.random()*0.9,vx:(Math.random()-0.5)*0.12,vy:-0.05-Math.random()*0.18,r:0.6+Math.random()*1.8,a:0.2+Math.random()*0.5}));
  }
  _setStatus(txt){ if(this.statusEl && txt!==this._lastStatus){ this.statusEl.textContent=txt; this._lastStatus=txt; this._emit('status', txt); } else if(!this.statusEl && txt!==this._lastStatus){ this._lastStatus=txt; this._emit('status', txt); } }

  _targetFrame(now){
    const S=this.S;
    if (now<S.blinkUntil) return 'blink';
    if (S.mode==='thinking') return 'loading';
    if (S.mode==='speaking'||S.mode==='listening') return 'neutral';
    return S.emotion;
  }
  _pushFrame(name, fast){
    if (name===this._displayed && !this._incoming) return;
    if (this._incoming && this._incoming.name===name) return;
    this._incoming={ name, alpha:0, step: fast?0.15:0.09 };
  }
  _readSpectrum(){
    const N=this.NBINS, sp=this._spectrum, S=this.S;
    if (this.analyser && this._freqArr){
      this.analyser.getByteFrequencyData(this._freqArr); const n=this._freqArr.length;
      for(let i=0;i<N;i++){ const lo=Math.floor(Math.pow(i/N,1.7)*n), hi=Math.max(lo+1,Math.floor(Math.pow((i+1)/N,1.7)*n));
        let s=0; for(let j=lo;j<hi;j++) s+=this._freqArr[j]; const v=s/((hi-lo)*255); sp[i]+=(v-sp[i])*0.5; }
    } else {
      this._specPhase+=0.18;
      for(let i=0;i<N;i++){ const env=Math.sin((i/N)*Math.PI), wob=0.5+0.5*Math.sin(this._specPhase+i*0.55);
        const v=S.level*env*(0.55+0.6*wob); sp[i]+=(v-sp[i])*0.35; }
    }
  }

  _frame = (now) => {
    if (!this._running) return;
    const S=this.S, ctx=this.ctx, o=this.opts;
    const t=(now-this._t0)/1000;

    const k=(S.targetLevel>S.level)?0.50:0.16; S.level+=(S.targetLevel-S.level)*k;
    if (S.mode!=='speaking'&&S.mode!=='listening') S.targetLevel*=0.85;
    const L=S.level;

    S.tintTo = S.mode==='thinking'?TINT.thinking:(TINT[S.emotion]||TINT.neutral);
    for(let i=0;i<3;i++) S.tint[i]+=(S.tintTo[i]-S.tint[i])*0.06;
    const tint=S.tint;

    if (S.mode!=='thinking' && now>S.nextBlink){ S.blinkUntil=now+120; S.nextBlink=now+2600+Math.random()*4200; }

    const fast=(S.mode==='speaking'||S.mode==='listening');
    this._pushFrame(this._targetFrame(now), fast);
    if (this._incoming){ this._incoming.alpha+=this._incoming.step; if(this._incoming.alpha>=1){ this._displayed=this._incoming.name; this._incoming=null; } }

    this._readSpectrum();

    if (S.mode==='thinking') this._setStatus(THINK_TXT[Math.floor(now/1500)%THINK_TXT.length]+' '+'·'.repeat(1+Math.floor(now/350)%3));
    else this._setStatus(o.defaultStatus);

    S.tilt.x+=(S.tilt.tx-S.tilt.x)*0.06; S.tilt.y+=(S.tilt.ty-S.tilt.y)*0.06;

    const W=this._cssW, H=this._cssH, cx=this._cx, cy=this._cy, faceSize=this._faceSize;
    ctx.clearRect(0,0,W,H);

    // partículas
    if (this._particles.length){
      ctx.globalCompositeOperation='lighter';
      for(const p of this._particles){
        p.x+=p.vx*p.z*(1+L*2); p.y+=p.vy*p.z*(1+L*1.5);
        if(p.y<-4){p.y=H+4;p.x=Math.random()*W;} if(p.x<-4)p.x=W+4; else if(p.x>W+4)p.x=-4;
        const a=p.a*(0.5+L*0.8)*p.z;
        ctx.fillStyle=`rgba(${tint[0]},${tint[1]},${tint[2]},${Math.min(1,a)})`;
        ctx.beginPath(); ctx.arc(p.x,p.y,p.r*(1+L*0.6),0,7); ctx.fill();
      }
      ctx.globalCompositeOperation='source-over';
    }

    // glow de fondo
    const pulse=0.35+0.20*Math.sin(t*1.8)+L*0.5;
    const gR=faceSize*0.52*(0.92+0.10*Math.sin(t*1.8)+L*0.25);
    const bx=cx+S.tilt.x*24, by=cy-6+S.tilt.y*18;
    const g=ctx.createRadialGradient(bx,by,30,bx,by,gR);
    g.addColorStop(0,`rgba(${tint[0]},${tint[1]},${tint[2]},${0.16+pulse*0.10})`);
    g.addColorStop(0.55,`rgba(${tint[0]},${tint[1]},${tint[2]},0.05)`); g.addColorStop(1,'rgba(0,0,0,0)');
    ctx.fillStyle=g; ctx.fillRect(0,0,W,H);

    this._drawRing(t,tint,L);
    if (S.mode==='thinking') this._drawThinking(t,tint);

    // cabeza
    const breathe=o.reducedMotion?1:1+Math.sin(t*1.5)*0.012;
    const bob=o.reducedMotion?0:Math.sin(t*1.5)*2.2;
    const pop=fast?L*0.035:0; const scale=breathe+pop;
    const px=cx+S.tilt.x*30, py=cy+bob-pop*38+S.tilt.y*22;

    ctx.save(); ctx.translate(px,py); ctx.scale(scale,scale);
    const sz=faceSize, x=-sz/2, y=-sz/2;
    const sh=ctx.createRadialGradient(0,sz*0.30,sz*0.05,0,sz*0.30,sz*0.42);
    sh.addColorStop(0,'rgba(0,0,0,0.45)'); sh.addColorStop(1,'rgba(0,0,0,0)');
    ctx.fillStyle=sh; ctx.beginPath(); ctx.ellipse(0,sz*0.34,sz*0.40,sz*0.12,0,0,7); ctx.fill();

    const di=this._getMasked(this._displayed);
    if (di){ ctx.globalAlpha=1; ctx.drawImage(di,x,y,sz,sz); }
    if (this._incoming){ const ii=this._getMasked(this._incoming.name); if(ii){ ctx.globalAlpha=this._incoming.alpha; ctx.drawImage(ii,x,y,sz,sz); } }
    ctx.globalAlpha=1;

    // ojos al hablar/escuchar
    if (fast && now>=S.blinkUntil){
      ctx.globalCompositeOperation='lighter';
      for(const e of EYE){
        const ex=-sz/2+e.x*sz, ey=-sz/2+e.y*sz, rad=sz*0.043+L*sz*0.114, a=0.20+L*0.9;
        const gg=ctx.createRadialGradient(ex,ey,0,ex,ey,rad);
        gg.addColorStop(0,`rgba(${tint[0]},${tint[1]},${tint[2]},${Math.min(1,a)})`);
        gg.addColorStop(0.42,`rgba(${tint[0]},${tint[1]},${tint[2]},${Math.min(1,a*0.45)})`); gg.addColorStop(1,'rgba(0,0,0,0)');
        ctx.fillStyle=gg; ctx.beginPath(); ctx.arc(ex,ey,rad,0,7); ctx.fill();
        if(L>0.28){ const cr=sz*0.009+L*sz*0.021, ca=(L-0.28);
          const cg=ctx.createRadialGradient(ex,ey,0,ex,ey,cr);
          cg.addColorStop(0,`rgba(255,255,255,${Math.min(1,ca)})`); cg.addColorStop(1,'rgba(255,255,255,0)');
          ctx.fillStyle=cg; ctx.beginPath(); ctx.arc(ex,ey,cr,0,7); ctx.fill(); }
      }
      ctx.globalCompositeOperation='source-over';
    }

    // puntos del visor en secuencia (pensar)
    if (S.mode==='thinking' && now>=S.blinkUntil){
      ctx.globalCompositeOperation='lighter'; const ph=now/300;
      for(let i=0;i<3;i++){ const d=DOTS[i]; const ex=-sz/2+d.x*sz, ey=-sz/2+d.y*sz;
        const w=Math.max(0,Math.sin(ph-i*0.7)), p=0.30+0.70*w, rad=sz*0.018+p*sz*0.034, a=0.25+p*0.75;
        const gg=ctx.createRadialGradient(ex,ey,0,ex,ey,rad);
        gg.addColorStop(0,`rgba(${tint[0]},${tint[1]},${tint[2]},${Math.min(1,a)})`);
        gg.addColorStop(0.5,`rgba(${tint[0]},${tint[1]},${tint[2]},${Math.min(1,a*0.4)})`); gg.addColorStop(1,'rgba(0,0,0,0)');
        ctx.fillStyle=gg; ctx.beginPath(); ctx.arc(ex,ey,rad,0,7); ctx.fill();
        if(w>0.7){ const cr=sz*0.008+w*sz*0.01; const cg=ctx.createRadialGradient(ex,ey,0,ex,ey,cr);
          cg.addColorStop(0,`rgba(255,255,255,${(w-0.7)*2})`); cg.addColorStop(1,'rgba(255,255,255,0)');
          ctx.fillStyle=cg; ctx.beginPath(); ctx.arc(ex,ey,cr,0,7); ctx.fill(); } }
      ctx.globalCompositeOperation='source-over';
    }
    ctx.restore();

    requestAnimationFrame(this._frame);
  };

  _drawRing(t,tint,L){
    const ctx=this.ctx, faceSize=this._faceSize, R=faceSize*0.50;
    const rx=this._cx+this.S.tilt.x*16, ry=this._cy-4+this.S.tilt.y*12;
    ctx.save(); ctx.translate(rx,ry); ctx.rotate(this.opts.reducedMotion?0:t*0.06);
    ctx.globalCompositeOperation='lighter';
    const n=this.NBINS, step=(Math.PI*2)/n;
    for(let i=0;i<n;i++){ const v=this._spectrum[i]||0, ang=i*step, inner=R, len=6+v*faceSize*0.22+(0.6+0.4*Math.sin(t*2+i))*3;
      const x1=Math.cos(ang)*inner,y1=Math.sin(ang)*inner,x2=Math.cos(ang)*(inner+len),y2=Math.sin(ang)*(inner+len), a=0.10+v*0.85;
      ctx.strokeStyle=`rgba(${tint[0]},${tint[1]},${tint[2]},${Math.min(1,a)})`; ctx.lineWidth=2;
      ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke(); }
    ctx.strokeStyle=`rgba(${tint[0]},${tint[1]},${tint[2]},${0.12+L*0.15})`; ctx.lineWidth=1;
    ctx.beginPath(); ctx.arc(0,0,R,0,Math.PI*2); ctx.stroke();
    if(!this.opts.reducedMotion){ const sw=(t*0.9)%(Math.PI*2);
      ctx.strokeStyle=`rgba(${tint[0]},${tint[1]},${tint[2]},${0.4+L*0.3})`; ctx.lineWidth=2;
      ctx.beginPath(); ctx.arc(0,0,R,sw,sw+0.6); ctx.stroke(); }
    ctx.restore(); ctx.globalCompositeOperation='source-over';
  }
  _drawThinking(t,tint){
    const ctx=this.ctx, faceSize=this._faceSize, R=faceSize*0.50;
    const rx=this._cx+this.S.tilt.x*16, ry=this._cy-4+this.S.tilt.y*12;
    ctx.save(); ctx.translate(rx,ry); ctx.globalCompositeOperation='lighter'; ctx.lineCap='round';
    for(let kk=0;kk<2;kk++){ const dir=kk?-1:1, rr=R*(1.10+kk*0.12), sp=this.opts.reducedMotion?0:t*(1.5+kk*0.8)*dir, a=0.55-kk*0.18;
      ctx.strokeStyle=`rgba(${tint[0]},${tint[1]},${tint[2]},${a})`; ctx.lineWidth=3-kk;
      for(let s=0;s<3;s++){ const off=s*(Math.PI*2/3); ctx.beginPath(); ctx.arc(0,0,rr,sp+off,sp+off+0.55); ctx.stroke(); } }
    if(!this.opts.reducedMotion){ const oa=t*2.2, orr=R*1.10, ox=Math.cos(oa)*orr, oy=Math.sin(oa)*orr;
      const og=ctx.createRadialGradient(ox,oy,0,ox,oy,10); og.addColorStop(0,'rgba(255,255,255,0.9)');
      og.addColorStop(0.4,`rgba(${tint[0]},${tint[1]},${tint[2]},0.7)`); og.addColorStop(1,'rgba(0,0,0,0)');
      ctx.fillStyle=og; ctx.beginPath(); ctx.arc(ox,oy,10,0,7); ctx.fill(); }
    ctx.restore(); ctx.globalCompositeOperation='source-over';
  }
}

export default NovaFace;
