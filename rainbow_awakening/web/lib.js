// Shared helpers: deterministic RNG, easing, keyframes, procedural canvas textures.
import * as THREE from 'three';

export function rng(seed) {             // mulberry32
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
export const lerp = (a, b, k) => a + (b - a) * k;
export const smooth = (a, b, x) => { const k = clamp((x - a) / (b - a)); return k * k * (3 - 2 * k); };
export const ease = {
  inOut: k => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2),
  out: k => 1 - Math.pow(1 - k, 3),
  in: k => k * k * k,
  outBack: k => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); },
  outExpo: k => (k >= 1 ? 1 : 1 - Math.pow(2, -10 * k)),
};
// progress of t inside [a,b] with easing
export const prog = (t, a, b, e = ease.inOut) => e(clamp((t - a) / (b - a)));

// smooth value noise 1D (deterministic) for flicker / shake
export function noise1(x, seed = 0) {
  const h = n => { const s = Math.sin(n * 127.1 + seed * 311.7) * 43758.5453; return s - Math.floor(s); };
  const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f);
  return lerp(h(i), h(i + 1), u) * 2 - 1;
}

// keyframe track: [[t, value(s)...], ...] with easing between keys
export function track(keys, t, e = ease.inOut) {
  if (t <= keys[0][0]) return keys[0][1];
  for (let i = 0; i < keys.length - 1; i++) {
    const [t0, v0] = keys[i], [t1, v1] = keys[i + 1];
    if (t <= t1) {
      const k = e((t - t0) / (t1 - t0));
      if (Array.isArray(v0)) return v0.map((x, j) => lerp(x, v1[j], k));
      return lerp(v0, v1, k);
    }
  }
  return keys[keys.length - 1][1];
}

export function hsl(h, s, l) { return new THREE.Color().setHSL(((h % 1) + 1) % 1, s, l); }

function canvasTex(w, h, draw, srgb = true) {
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 4;
  return t;
}

// soft radial glow for sprites / fake bloom
export const glowTex = (() => {
  let t; return () => t || (t = canvasTex(128, 128, (g, w) => {
    const r = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(0.18, 'rgba(255,255,255,0.75)');
    r.addColorStop(0.45, 'rgba(255,255,255,0.22)'); r.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = r; g.fillRect(0, 0, w, w);
  }, false));
})();

// 4-point star sparkle
export const sparkleTex = (() => {
  let t; return () => t || (t = canvasTex(128, 128, (g) => {
    const r = g.createRadialGradient(64, 64, 0, 64, 64, 22);
    r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = r; g.fillRect(0, 0, 128, 128);
    g.globalCompositeOperation = 'lighter';
    for (const [w, h] of [[60, 5], [5, 60]]) {
      const lg = g.createRadialGradient(64, 64, 0, 64, 64, 60);
      lg.addColorStop(0, 'rgba(255,255,255,1)'); lg.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = lg; g.beginPath(); g.ellipse(64, 64, w, h, 0, 0, Math.PI * 2); g.fill();
    }
  }, false));
})();

// soft smoke puff (grey, alpha)
export const smokeTex = (() => {
  let t; return () => t || (t = canvasTex(128, 128, (g) => {
    const R = rng(99);
    for (let i = 0; i < 26; i++) {
      const x = 64 + (R() - 0.5) * 50, y = 64 + (R() - 0.5) * 50, rr = 14 + R() * 30;
      const r = g.createRadialGradient(x, y, 0, x, y, rr);
      r.addColorStop(0, 'rgba(255,255,255,0.22)'); r.addColorStop(1, 'rgba(255,255,255,0)');
      g.fillStyle = r; g.beginPath(); g.arc(x, y, rr, 0, Math.PI * 2); g.fill();
    }
    const m = g.createRadialGradient(64, 64, 20, 64, 64, 64);
    m.addColorStop(0, 'rgba(0,0,0,0)'); m.addColorStop(1, 'rgba(0,0,0,1)');
    g.globalCompositeOperation = 'destination-out'; g.fillStyle = m; g.fillRect(0, 0, 128, 128);
  }, false));
})();

// soft ring (shockwaves)
export const ringTex = (() => {
  let t; return () => t || (t = canvasTex(256, 256, (g) => {
    const r = g.createRadialGradient(128, 128, 60, 128, 128, 128);
    r.addColorStop(0, 'rgba(255,255,255,0)'); r.addColorStop(0.7, 'rgba(255,255,255,0.9)');
    r.addColorStop(0.82, 'rgba(255,255,255,0.6)'); r.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = r; g.fillRect(0, 0, 256, 256);
  }, false));
})();

// baseplate-style ground: grass with soft grid seams and faint studs
export function baseplateTex(base = '#5fbf4a', line = 'rgba(0,0,0,0.10)', hi = 'rgba(255,255,255,0.07)') {
  const t = canvasTex(256, 256, (g, w) => {
    g.fillStyle = base; g.fillRect(0, 0, w, w);
    const R = rng(5);
    for (let i = 0; i < 900; i++) {             // subtle speckle
      g.fillStyle = `rgba(${R() < 0.5 ? '0,0,0' : '255,255,255'},${0.025 + R() * 0.03})`;
      g.fillRect(R() * w, R() * w, 2 + R() * 3, 2 + R() * 3);
    }
    g.fillStyle = line; g.fillRect(0, 0, w, 3); g.fillRect(0, 0, 3, w);
    g.fillStyle = hi; g.fillRect(0, 3, w, 2); g.fillRect(3, 0, 2, w);
    for (const x of [64, 192]) for (const y of [64, 192]) {   // studs
      g.fillStyle = 'rgba(255,255,255,0.08)'; g.beginPath(); g.arc(x - 2, y - 2, 22, 0, 7); g.fill();
      g.fillStyle = 'rgba(0,0,0,0.07)'; g.beginPath(); g.arc(x + 3, y + 3, 22, 0, 7); g.fill();
      g.fillStyle = base; g.beginPath(); g.arc(x, y, 21, 0, 7); g.fill();
    }
  });
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

export function tileTex(base = '#b9b2a6') {
  const t = canvasTex(256, 256, (g, w) => {
    g.fillStyle = base; g.fillRect(0, 0, w, w);
    const R = rng(11);
    for (let y = 0; y < 4; y++) for (let x = 0; x < 4; x++) {
      const v = 0.92 + R() * 0.12;
      g.fillStyle = `rgba(${v > 1 ? '255,255,255' : '0,0,0'},${Math.abs(v - 1) * 1.2})`;
      g.fillRect(x * 64 + 2, y * 64 + 2, 60, 60);
    }
    g.strokeStyle = 'rgba(0,0,0,0.18)'; g.lineWidth = 3;
    for (let i = 0; i <= 4; i++) { g.beginPath(); g.moveTo(i * 64, 0); g.lineTo(i * 64, w); g.stroke(); g.beginPath(); g.moveTo(0, i * 64); g.lineTo(w, i * 64); g.stroke(); }
  });
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

// crack map: R = reveal order (0 near origin .. 1 far), A = crack mask
export function crackTex() {
  return canvasTex(512, 512, (g) => {
    g.clearRect(0, 0, 512, 512);
    const R = rng(1234);
    const seg = (x, y, ang, len, depth, d0) => {
      let px = x, py = y, d = d0;
      const steps = 6 + Math.floor(R() * 5);
      for (let i = 0; i < steps; i++) {
        ang += (R() - 0.5) * 0.9;
        const l = len / steps;
        const nx = px + Math.cos(ang) * l, ny = py + Math.sin(ang) * l;
        const nd = d + l / 700;
        const grad = g.createLinearGradient(px, py, nx, ny);
        grad.addColorStop(0, `rgb(${Math.round(clamp(d) * 255)},0,0)`);
        grad.addColorStop(1, `rgb(${Math.round(clamp(nd) * 255)},0,0)`);
        g.strokeStyle = grad; g.lineWidth = Math.max(2, 9 - depth * 2.5 - i * 0.5); g.lineCap = 'round';
        g.beginPath(); g.moveTo(px, py); g.lineTo(nx, ny); g.stroke();
        if (depth < 2 && R() < 0.35) seg(nx, ny, ang + (R() < 0.5 ? 1 : -1) * (0.6 + R() * 0.6), len * 0.5, depth + 1, nd);
        px = nx; py = ny; d = nd;
      }
    };
    for (let k = 0; k < 7; k++) seg(256 + (R() - 0.5) * 60, 300 + (R() - 0.5) * 60, R() * Math.PI * 2, 260 + R() * 120, 0, 0);
  }, false);
}

// ---------------------------------------------------------------- faces
// expression: smile | grin | nervous | sad | shock | joy | laugh | smirk | determined | glow (white eyes)
export function faceTex(expr, opts = {}) {
  const skin = opts.skin || null;
  return canvasTex(256, 256, (g) => {
    g.clearRect(0, 0, 256, 256);
    if (skin) { g.fillStyle = skin; g.fillRect(0, 0, 256, 256); }
    const ink = opts.ink || '#1b1b22';
    const eyeY = 108, ex = 52;
    const eye = (x, h = 46, w = 26, look = 0) => {
      g.fillStyle = ink; g.beginPath(); g.ellipse(x + look, eyeY, w / 2, h / 2, 0, 0, 7); g.fill();
      g.fillStyle = '#fff'; g.beginPath(); g.ellipse(x + look - 4, eyeY - h * 0.22, w * 0.2, w * 0.24, 0, 0, 7); g.fill();
    };
    const brow = (x, tilt, y = 66, w = 34) => {
      g.save(); g.translate(128 + x, y); g.rotate(tilt); g.fillStyle = ink;
      g.beginPath(); g.roundRect(-w / 2, -5, w, 10, 5); g.fill(); g.restore();
    };
    const closedEye = (x, up = true) => {
      g.strokeStyle = ink; g.lineWidth = 9; g.lineCap = 'round'; g.beginPath();
      if (up) g.arc(128 + x, eyeY + 10, 17, Math.PI * 1.15, Math.PI * 1.85); else g.arc(128 + x, eyeY - 12, 17, Math.PI * 0.15, Math.PI * 0.85);
      g.stroke();
    };
    const blush = () => { g.fillStyle = 'rgba(255,110,110,0.35)'; for (const s of [-1, 1]) { g.beginPath(); g.ellipse(128 + s * 78, 150, 18, 10, 0, 0, 7); g.fill(); } };
    const look = opts.look || 0;
    g.lineCap = 'round'; g.lineJoin = 'round';
    switch (expr) {
      case 'grin': case 'joy': {
        if (expr === 'joy') { closedEye(-ex); closedEye(ex); } else { eye(128 - ex, 48, 26, look); eye(128 + ex, 48, 26, look); }
        brow(-ex, -0.12, 62); brow(ex, 0.12, 62);
        g.fillStyle = ink; g.beginPath(); g.moveTo(84, 158); g.quadraticCurveTo(128, 222, 172, 158); g.closePath(); g.fill();
        g.fillStyle = '#ff6f7d'; g.beginPath(); g.ellipse(128, 186, 20, 10, 0, 0, 7); g.fill();
        g.fillStyle = '#fff'; g.fillRect(96, 158, 64, 9);
        blush(); break;
      }
      case 'nervous': {
        eye(128 - ex, 40, 24, look); eye(128 + ex, 40, 24, look);
        brow(-ex, -0.3, 62); brow(ex, 0.3, 62);
        g.strokeStyle = ink; g.lineWidth = 8; g.beginPath(); g.moveTo(92, 176);
        for (let i = 1; i <= 6; i++) g.lineTo(92 + i * 12, 176 + (i % 2 ? -7 : 5));
        g.stroke();
        g.fillStyle = 'rgba(120,200,255,0.95)'; g.beginPath(); g.moveTo(206, 60); g.quadraticCurveTo(220, 86, 206, 92); g.quadraticCurveTo(192, 86, 206, 60); g.fill();
        break;
      }
      case 'sad': {
        eye(128 - ex, 36, 24, look); eye(128 + ex, 36, 24, look);
        brow(-ex, -0.4, 70); brow(ex, 0.4, 70);
        g.strokeStyle = ink; g.lineWidth = 9; g.beginPath(); g.arc(128, 200, 30, Math.PI * 1.2, Math.PI * 1.8); g.stroke();
        if (opts.tear) { g.fillStyle = 'rgba(120,200,255,0.9)'; g.beginPath(); g.ellipse(128 - ex - 6, 146, 7, 12, 0, 0, 7); g.fill(); }
        break;
      }
      case 'shock': {
        eye(128 - ex, 54, 30, look); eye(128 + ex, 54, 30, look);
        brow(-ex, -0.1, 52); brow(ex, 0.1, 52);
        g.fillStyle = ink; g.beginPath(); g.ellipse(128, 180, 22, opts.wide ? 34 : 26, 0, 0, 7); g.fill();
        g.fillStyle = '#ff6f7d'; g.beginPath(); g.ellipse(128, 194, 13, 8, 0, 0, 7); g.fill();
        break;
      }
      case 'laugh': {
        closedEye(-ex); closedEye(ex);
        brow(-ex, -0.2, 64); brow(ex, 0.2, 64);
        g.fillStyle = ink; g.beginPath(); g.moveTo(80, 150); g.quadraticCurveTo(128, 232, 176, 150); g.closePath(); g.fill();
        g.fillStyle = '#ff6f7d'; g.beginPath(); g.ellipse(128, 185, 22, 12, 0, 0, 7); g.fill();
        g.fillStyle = '#fff'; g.fillRect(92, 150, 72, 9);
        break;
      }
      case 'smirk': {
        eye(128 - ex, 40, 26, look); eye(128 + ex, 40, 26, look);
        brow(-ex, 0.0, 66); brow(ex, -0.2, 60);
        g.strokeStyle = ink; g.lineWidth = 9; g.beginPath(); g.moveTo(96, 172); g.quadraticCurveTo(140, 186, 168, 160); g.stroke();
        break;
      }
      case 'determined': {
        eye(128 - ex, 42, 26, look); eye(128 + ex, 42, 26, look);
        brow(-ex, 0.3, 70); brow(ex, -0.3, 70);
        g.strokeStyle = ink; g.lineWidth = 9; g.beginPath(); g.moveTo(100, 176); g.quadraticCurveTo(128, 186, 156, 176); g.stroke();
        break;
      }
      case 'glow': {     // black-aura kid: glowing white eyes, flat mouth
        g.shadowColor = '#fff'; g.shadowBlur = 24;
        g.fillStyle = '#ffffff';
        for (const s of [-1, 1]) { g.save(); g.translate(128 + s * ex, eyeY); g.rotate(s * 0.25); g.beginPath(); g.ellipse(0, 0, 20, 11, 0, 0, 7); g.fill(); g.restore(); }
        g.shadowBlur = 0;
        g.strokeStyle = '#d9d9ff'; g.lineWidth = 7; g.beginPath(); g.moveTo(104, 178); g.lineTo(152, 174); g.stroke();
        break;
      }
      case 'blink': {
        closedEye(-ex, false); closedEye(ex, false);
        brow(-ex, -0.08, 64); brow(ex, 0.08, 64);
        g.strokeStyle = ink; g.lineWidth = 9; g.beginPath(); g.arc(128, 150, 36, Math.PI * 0.2, Math.PI * 0.8); g.stroke();
        break;
      }
      default: { // smile
        eye(128 - ex, 46, 26, look); eye(128 + ex, 46, 26, look);
        brow(-ex, -0.08, 64); brow(ex, 0.08, 64);
        g.strokeStyle = ink; g.lineWidth = 9; g.beginPath(); g.arc(128, 146, 40, Math.PI * 0.2, Math.PI * 0.8); g.stroke();
        if (opts.blush) blush();
      }
    }
  });
}
