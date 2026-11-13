// 2D compositing: bloom, vignette, flashes, captions, end card. Coordinates are in 1080x1920 design units.
import { clamp, ease, prog } from './lib.js';

export const FONT = '"Lilita One", "Arial Black", sans-serif';
const CAP_CX = 520;         // caption center x (a bit left of center: away from the right-side buttons)
const CAP_CY = 1085;        // caption center y (middle third: 640..1280)
const CAP_MAXW = 820;

export class Overlay {
  constructor(W, H, timing) {
    this.W = W; this.H = H; this.S = W / 1080;
    this.c = document.createElement('canvas'); this.c.width = W; this.c.height = H;
    this.ctx = this.c.getContext('2d', { willReadFrequently: true });
    this.b1 = document.createElement('canvas'); this.b1.width = Math.round(W / 6); this.b1.height = Math.round(H / 6);
    this.b2 = document.createElement('canvas'); this.b2.width = this.b1.width; this.b2.height = this.b1.height;
    this.chunks = [];
    for (const L of timing.lines) for (const c of L.chunks) this.chunks.push({ ...c, line: L.id });
  }

  compose(glCanvas, t, fx) {
    const g = this.ctx, W = this.W, H = this.H;
    g.globalCompositeOperation = 'source-over'; g.globalAlpha = 1; g.filter = 'none';
    g.drawImage(glCanvas, 0, 0, W, H);
    if (fx.bloom > 0) {
      const b1 = this.b1.getContext('2d'), b2 = this.b2.getContext('2d');
      b1.filter = 'brightness(0.55) contrast(3.4) saturate(1.6)';
      b1.drawImage(glCanvas, 0, 0, this.b1.width, this.b1.height);
      b2.clearRect(0, 0, this.b2.width, this.b2.height);
      b2.filter = 'blur(7px)'; b2.drawImage(this.b1, 0, 0);
      g.globalCompositeOperation = 'screen'; g.globalAlpha = clamp(fx.bloom, 0, 1);
      g.drawImage(this.b2, 0, 0, W, H);
      g.globalAlpha = 1; g.globalCompositeOperation = 'source-over';
    }
    if (fx.tint) { g.fillStyle = fx.tint; g.fillRect(0, 0, W, H); }
    if (fx.vignette > 0) {
      const r = g.createRadialGradient(W / 2, H * 0.45, H * 0.28, W / 2, H * 0.5, H * 0.75);
      r.addColorStop(0, 'rgba(0,0,0,0)'); r.addColorStop(1, `rgba(0,0,0,${fx.vignette})`);
      g.fillStyle = r; g.fillRect(0, 0, W, H);
    }
    if (fx.black > 0) { g.fillStyle = `rgba(0,0,0,${clamp(fx.black)})`; g.fillRect(0, 0, W, H); }
    if (fx.flash > 0) { g.fillStyle = fx.flashColor || '#ffffff'; g.globalAlpha = clamp(fx.flash); g.fillRect(0, 0, W, H); g.globalAlpha = 1; }
    g.save(); g.scale(this.S, this.S);
    if (fx.endcard) this.endCard(g, t, fx.endcard);
    this.captions(g, t);
    g.restore();
    return this.c;
  }

  // ------------------------------------------------------------ captions
  captions(g, t) {
    for (const c of this.chunks) {
      if (t < c.start || t >= c.end) continue;
      this.drawChunk(g, c, t);
    }
  }

  layout(g, words, F) {
    g.font = `${F}px ${FONT}`;
    const space = g.measureText(' ').width;
    const lines = [[]]; let w = 0;
    for (const wd of words) {
      const ww = g.measureText(wd.w).width;
      if (lines[lines.length - 1].length && w + space + ww > CAP_MAXW) { lines.push([]); w = 0; }
      const L = lines[lines.length - 1];
      L.push({ ...wd, ww }); w += (L.length > 1 ? space : 0) + ww;
    }
    return { lines, space };
  }

  drawChunk(g, c, t) {
    const n = c.words.length;
    let F = n <= 1 ? 150 : n <= 2 ? 124 : n <= 4 ? 106 : 96;
    let lay = this.layout(g, c.words, F);
    while (lay.lines.length > 2 && F > 60) { F -= 6; lay = this.layout(g, c.words, F); }
    const age = t - c.start;
    // pop-in: quick scale bounce
    const k = clamp(age / 0.24);
    const pop = age < 0.24 ? 0.35 + 0.65 * ease.outBack(k) : 1;
    const lh = F * 1.08;
    const totalH = lay.lines.length * lh;
    g.save();
    g.translate(CAP_CX, CAP_CY);
    g.scale(pop, pop);
    g.textBaseline = 'middle'; g.lineJoin = 'round'; g.miterLimit = 2;
    lay.lines.forEach((L, li) => {
      const lw = L.reduce((s, w) => s + w.ww, 0) + lay.space * (L.length - 1);
      let x = -lw / 2;
      const y = -totalH / 2 + lh * (li + 0.5);
      for (const w of L) {
        const spoken = t - w.t;
        let s = 1;
        if (w.color && spoken > 0 && spoken < 0.35) s = 1 + 0.18 * Math.sin(spoken / 0.35 * Math.PI);
        g.save();
        g.translate(x + w.ww / 2, y);
        g.scale(s, s);
        g.font = `${F}px ${FONT}`;
        this.word(g, w.w, w.color, F, w.ww, t);
        g.restore();
        x += w.ww + lay.space;
      }
    });
    g.restore();
  }

  word(g, text, color, F, ww, t) {
    g.textAlign = 'center';
    const sw = Math.max(10, F * 0.2);
    // drop shadow
    g.fillStyle = 'rgba(0,0,0,0.45)';
    g.lineWidth = sw; g.strokeStyle = 'rgba(0,0,0,0.45)';
    g.strokeText(text, 0, F * 0.07); g.fillText(text, 0, F * 0.07);
    if (color === 'black') {
      g.shadowColor = 'rgba(255,255,255,0.95)'; g.shadowBlur = F * 0.45;
      g.strokeStyle = '#ffffff'; g.lineWidth = sw * 0.75; g.strokeText(text, 0, 0);
      g.shadowBlur = F * 0.2; g.strokeText(text, 0, 0);
      g.shadowBlur = 0;
      g.fillStyle = '#0a0a0f'; g.fillText(text, 0, 0);
      return;
    }
    g.strokeStyle = '#000000'; g.lineWidth = sw; g.strokeText(text, 0, 0);
    let fill = '#ffffff';
    if (color === 'purple') fill = '#c35cff';
    else if (color === 'yellow') fill = '#ffe83a';
    else if (color === 'gold') {
      const gr = g.createLinearGradient(0, -F * 0.42, 0, F * 0.42);
      gr.addColorStop(0, '#fff7b0'); gr.addColorStop(0.45, '#ffd02a'); gr.addColorStop(0.55, '#f2b000'); gr.addColorStop(1, '#c98700');
      fill = gr;
    } else if (color === 'rainbow') {
      const gr = g.createLinearGradient(-ww / 2, 0, ww / 2, 0);
      for (let i = 0; i <= 6; i++) gr.addColorStop(i / 6, `hsl(${(i / 6 * 300 + t * 140) % 360}, 100%, 62%)`);
      fill = gr;
    }
    g.fillStyle = fill; g.fillText(text, 0, 0);
    if (color === 'gold' || color === 'rainbow') {   // glossy highlight
      g.save(); g.globalAlpha = 0.35; g.fillStyle = '#ffffff';
      g.beginPath(); g.rect(-ww, -F * 0.5, ww * 2, F * 0.32); g.clip(); g.fillText(text, 0, 0); g.restore();
    }
  }

  // ------------------------------------------------------------ end card
  endCard(g, t, t0) {
    const a = t - t0;
    if (a < 0) return;
    // darken top for the title
    const gr = g.createLinearGradient(0, 120, 0, 760);
    gr.addColorStop(0, `rgba(10,6,30,${0.55 * clamp(a / 0.3)})`); gr.addColorStop(1, 'rgba(10,6,30,0)');
    g.fillStyle = gr; g.fillRect(0, 120, 1080, 640);
    const pop = (d) => { const k = clamp((a - d) / 0.3); return k <= 0 ? 0 : 0.3 + 0.7 * ease.outBack(k); };
    g.textAlign = 'center'; g.textBaseline = 'middle'; g.lineJoin = 'round';
    const draw = (txt, y, F, fill, s) => {
      if (s <= 0) return;
      g.save(); g.translate(520, y); g.scale(s, s); g.font = `${F}px ${FONT}`;
      g.fillStyle = 'rgba(0,0,0,0.5)'; g.lineWidth = F * 0.22; g.strokeStyle = 'rgba(0,0,0,0.5)'; g.strokeText(txt, 0, F * 0.08);
      g.strokeStyle = '#000'; g.lineWidth = F * 0.2; g.strokeText(txt, 0, 0);
      g.fillStyle = fill(g, F, txt); g.fillText(txt, 0, 0); g.restore();
    };
    const rainbow = (g2, F, txt) => {
      g2.font = `${F}px ${FONT}`; const w = g2.measureText(txt).width;
      const r = g2.createLinearGradient(-w / 2, 0, w / 2, 0);
      for (let i = 0; i <= 6; i++) r.addColorStop(i / 6, `hsl(${(i / 6 * 300 + t * 160) % 360},100%,62%)`);
      return r;
    };
    draw('RAINBOW', 400, 160, rainbow, pop(0));
    draw('AWAKENING', 545, 112, () => '#ffffff', pop(0.12));
    // "part 2" pill
    const s = pop(0.3);
    if (s > 0) {
      g.save(); g.translate(520, 1330); g.scale(s, s);
      g.fillStyle = 'rgba(0,0,0,0.35)'; g.beginPath(); g.roundRect(-300, -52 + 8, 600, 104, 52); g.fill();
      const pg = g.createLinearGradient(-300, 0, 300, 0); pg.addColorStop(0, '#ff3d7f'); pg.addColorStop(1, '#ff7a3d');
      g.fillStyle = pg; g.beginPath(); g.roundRect(-300, -52, 600, 104, 52); g.fill();
      g.lineWidth = 6; g.strokeStyle = '#ffffff'; g.stroke();
      g.font = `58px ${FONT}`; g.fillStyle = '#ffffff'; g.fillText('PART 2 COMING SOON', 0, 4);
      g.restore();
    }
  }
}
