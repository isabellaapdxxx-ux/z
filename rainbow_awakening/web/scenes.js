// The Director stages every scene. update(t) poses everything for time t and returns 2D overlay params.
import * as THREE from 'three';
import { Character, makeMax, plastic, rbox, mesh } from './character.js';
import { Aura, Particles, Trail, Shockwave, Beam, Confetti, glowSprite } from './fx.js';
import { rng, clamp, lerp, smooth, ease, prog, track, noise1, hsl, sparkleTex, glowTex, smokeTex } from './lib.js';

const V = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
const PLAZA_Y = 0.24;

const CROWD_LOOKS = (() => {
  const R = rng(2024);
  const shirts = ['#e63946', '#f4a261', '#2a9d8f', '#e9c46a', '#ff006e', '#3a86ff', '#06d6a0', '#ffbe0b', '#fb5607', '#8ac926', '#ff595e', '#1982c4', '#9b5de5', '#00bbf9'];
  const skins = ['#f3c29b', '#e0ac69', '#c68642', '#8d5524', '#ffdbac', '#d4a373'];
  const hair = ['#2b1d14', '#4a2c17', '#f4d35e', '#a0522d', '#111111', '#d9480f', '#7b3f00'];
  const styles = ['cap', 'spiky', 'long', 'puff', 'buns', 'beanie', 'cap', 'long'];
  const pants = ['#264653', '#2b2d42', '#3d405b', '#1d3557', '#5c4d7d', '#6b705c'];
  return shirts.map((s, i) => ({
    shirt: s, skin: skins[Math.floor(R() * skins.length)], hair: hair[Math.floor(R() * hair.length)],
    hairStyle: styles[i % styles.length], pants: pants[Math.floor(R() * pants.length)],
    shoes: ['#ffffff', '#222222', '#ff4d6d', '#4cc9f0'][i % 4], shoeAccent: ['#3a86ff', '#ffbe0b', '#ffffff', '#ff006e'][i % 4],
    beanie: ['#ff006e', '#3a86ff', '#ffbe0b'][i % 3], seed: i * 1.7, scale: 0.92 + R() * 0.14,
  }));
})();

function ringMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uA: { value: 1 } },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.0);} `,
    fragmentShader: `uniform float uTime, uA; varying vec2 vUv;
      vec3 hsv2rgb(vec3 c){ vec3 p=abs(fract(c.xxx+vec3(0.,2./3.,1./3.))*6.-3.); return c.z*mix(vec3(1.),clamp(p-1.,0.,1.),c.y); }
      void main(){ vec3 c = hsv2rgb(vec3(fract(vUv.x*2.0 - uTime*0.8), 0.85, 1.0)); float e = 0.55+0.45*sin(vUv.y*6.2831);
        gl_FragColor = vec4(c*uA*e*1.3, 1.0);} `,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
  });
}

function bullseyeTex() {
  const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d');
  for (let i = 0; i < 5; i++) { g.fillStyle = i % 2 ? '#ffffff' : '#e63946'; g.beginPath(); g.arc(64, 64, 64 - i * 12.5, 0, 7); g.fill(); }
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

export class Director {
  constructor(scene, camera, world, timing, renderer) {
    this.scene = scene; this.cam = camera; this.world = world; this.timing = timing; this.renderer = renderer;
    this.lines = Object.fromEntries(timing.lines.map(l => [l.id, l]));
    const add = (o) => { o.userData.dynamic = true; scene.add(o); return o; };
    this.add = add;
    // ---- characters
    this.max = makeMax(); add(this.max.root);
    this.kp = new Character({ name: 'violet', shirt: '#ff8fab', skin: '#e0ac69', hair: '#2b1d14', hairStyle: 'long', pants: '#5c4d7d', shoes: '#ffffff', shoeAccent: '#b44dff', seed: 1 });
    this.ky = new Character({ name: 'zed', shirt: '#ff7f11', skin: '#c68642', hair: '#f4d35e', hairStyle: 'spiky', pants: '#1d3557', shoes: '#ffe13a', shoeAccent: '#222222', emblem: '#ffe13a', seed: 2 });
    this.kg = new Character({ name: 'leo', shirt: '#fdfdfd', skin: '#8d5524', hair: '#111111', hairStyle: 'puff', pants: '#c99700', shoes: '#ffd166', shoeAccent: '#c1121f', emblem: '#ffb81c', cape: '#d62828', belt: '#ffb81c', seed: 3 });
    this.kb = new Character({ name: 'nyx', shirt: '#24212e', skin: '#d1a37a', hair: '#111111', hairStyle: 'beanie', beanie: '#15131c', beanieBand: '#2e2a3d', pants: '#121018', shoes: '#2b2b33', shoeAccent: '#8f7cff', hoodie: true, hoodieDark: '#15131c', seed: 4 });
    this.kb.setFace('glow');
    for (const k of [this.kp, this.ky, this.kg, this.kb]) add(k.root);
    this.crowd = CROWD_LOOKS.map(o => { const c = new Character(o); add(c.root); return c; });
    // ---- auras (attached to hips so they tilt with the body)
    const attach = (ch, aura) => { aura.group.position.y = -2; aura.group.userData.dynamic = true; ch.hips.add(aura.group); return aura; };
    this.aP = attach(this.kp, new Aura('purple', { seed: 11 }));
    this.aY = attach(this.ky, new Aura('yellow', { seed: 12 }));
    this.aG = attach(this.kg, new Aura('gold', { seed: 13 }));
    this.aB = attach(this.kb, new Aura('black', { seed: 14 }));
    this.aM = attach(this.max, new Aura('rainbow', { seed: 15, particles: 320 }));
    this.aC0 = attach(this.crowd[0], new Aura('purple', { seed: 16, particles: 50, light: false }));
    this.aC1 = attach(this.crowd[1], new Aura('gold', { seed: 17, particles: 50, light: false }));
    this.aC2 = attach(this.crowd[5], new Aura('yellow', { seed: 18, particles: 50, light: false }));
    this.auras = [this.aP, this.aY, this.aG, this.aB, this.aM, this.aC0, this.aC1, this.aC2];
    // ---- effects
    this.fx = [];
    const fxo = (o) => { add(o); this.fx.push(o); return o; };
    this.dust = new Particles(90, sparkleTex()); fxo(this.dust.obj);
    this.trails = [0, 1, 2, 3].map(i => { const tr = new Trail(['#b44dff', '#ffe13a', '#ffb81c', '#ffe13a'][i], i === 3 ? 1.0 : 0.9, 40); fxo(tr.mesh); return tr; });
    this.rTrail = new Trail('#ffffff', 1.3, 60, true); fxo(this.rTrail.mesh);
    // toy blocks + crate
    const toyCols = ['#ff595e', '#1982c4', '#8ac926', '#ffca3a', '#ff924c', '#ff70a6', '#4cc9f0'];
    this.blocks = toyCols.map((c, i) => {
      const g = new THREE.Group();
      mesh(rbox(0.85, 0.85, 0.85, 0.1), plastic(c), 0, 0, 0, g);
      const sh = new THREE.Mesh(new THREE.BoxGeometry(1.05, 1.05, 1.05), new THREE.MeshBasicMaterial({ color: '#b44dff', transparent: true, opacity: 0.35, blending: THREE.AdditiveBlending, depthWrite: false }));
      g.add(sh); g.userData.shell = sh;
      const gl = glowSprite(new THREE.Color('#c77dff'), 2.6, 0.6); g.add(gl); g.userData.glow = gl;
      return fxo(g);
    });
    this.crate = new THREE.Group();
    mesh(rbox(2.3, 2.3, 2.3, 0.08), plastic('#b5762f', { roughness: 0.75 }), 0, 1.15, 0, this.crate);
    const plank = plastic('#7f4f24', { roughness: 0.8 });
    for (const s of [-1, 1]) { mesh(new THREE.BoxGeometry(2.36, 0.3, 2.36), plank, 0, 1.15 + s * 0.95, 0, this.crate); }
    for (const s of [-1, 1]) mesh(new THREE.BoxGeometry(0.3, 2.36, 2.36), plank, s * 0.95, 1.15, 0, this.crate);
    fxo(this.crate);
    this.ySparks = new Particles(120, sparkleTex()); fxo(this.ySparks.obj);
    this.puffs = new Particles(40, smokeTex(), false); fxo(this.puffs.obj);
    this.stars = new Particles(36, sparkleTex()); fxo(this.stars.obj);
    // gold scene
    const bt = bullseyeTex();
    this.targets = [V(-8, 12, 40), V(0, 15, 44), V(8, 12, 40)].map(p => {
      const g = new THREE.Group(); g.position.copy(p);
      const disc = new THREE.Mesh(new THREE.CylinderGeometry(1.8, 1.8, 0.4, 24), [plastic('#ffffff'), new THREE.MeshStandardMaterial({ map: bt, roughness: 0.5 }), new THREE.MeshStandardMaterial({ map: bt, roughness: 0.5 })]);
      disc.rotation.x = Math.PI / 2; g.add(disc);
      g.userData.home = p.clone();
      return fxo(g);
    });
    this.blasts = [0, 1, 2, 3].map(() => {
      const g = new THREE.Group();
      g.add(new THREE.Mesh(new THREE.SphereGeometry(0.45, 16, 12), new THREE.MeshBasicMaterial({ color: '#fff6c8', toneMapped: false })));
      g.add(glowSprite(new THREE.Color('#ffc21a'), 4.2, 0.95));
      return fxo(g);
    });
    this.goldBurst = new Particles(420, sparkleTex()); fxo(this.goldBurst.obj);
    this.goldRain = new Particles(220, sparkleTex()); fxo(this.goldRain.obj);
    this.frags = new Confetti(48, 31); fxo(this.frags.mesh);
    this.frags.p.forEach((p, i) => this.frags.mesh.setColorAt(i, new THREE.Color(i % 2 ? '#ffffff' : '#e63946')));
    this.goldLight = new THREE.PointLight('#ffc21a', 0, 40, 1.5); fxo(this.goldLight);
    // quake / rainbow
    this.debris = new Confetti(60, 41);
    this.debris.p.forEach((p, i) => this.debris.mesh.setColorAt(i, new THREE.Color(['#9aa3b5', '#d8d2c4', '#6b705c', '#c9cfdb'][i % 4])));
    this.debris.mesh.material = new THREE.MeshStandardMaterial({ roughness: 0.8 });
    fxo(this.debris.mesh);
    this.streams = new Particles(220, sparkleTex()); fxo(this.streams.obj);
    this.swirl = new Particles(320, sparkleTex()); fxo(this.swirl.obj);
    this.fizzle = new Particles(30, smokeTex(), false); fxo(this.fizzle.obj);
    this.shock1 = new Shockwave(); fxo(this.shock1.mesh);
    this.shock2 = new Shockwave(); fxo(this.shock2.mesh);
    this.confetti = new Confetti(260, 9); fxo(this.confetti.mesh);
    this.rings = [0, 1, 2].map(i => { const m = new THREE.Mesh(new THREE.TorusGeometry(3.2 + i * 0.5, 0.12, 8, 64), ringMaterial()); return fxo(m); });
    this.pillar = new Beam(120, 5.5); fxo(this.pillar.group);
    this.maxGlow = glowSprite(new THREE.Color('#ffffff'), 24, 0); fxo(this.maxGlow);
    this.rimLight = new THREE.PointLight('#ffffff', 0, 30, 1.2); fxo(this.rimLight);
    this.fill = new THREE.PointLight('#ffffff', 0, 40, 1.0); fxo(this.fill);
  }

  // ------------------------------------------------------------ timing helpers
  wt(id, word, fallback = null) {
    const L = this.lines[id];
    if (!L) return fallback;
    for (const c of L.chunks) for (const w of c.words) if (w.w.toLowerCase().replace(/[^a-z0-9']/g, '').startsWith(word.toLowerCase())) return w.t;
    return fallback ?? L.start;
  }
  ls(id) { return this.lines[id].start; }
  le(id) { return this.lines[id].end; }

  setCam(pos, look, fov = 40, shake = 0, t = 0, scale = 1.45) {
    const c = this.cam;
    c.position.copy(look).add(pos.clone().sub(look).multiplyScalar(scale));
    if (shake > 0) c.position.add(V(noise1(t * 14, 1), noise1(t * 14, 2), noise1(t * 14, 3)).multiplyScalar(shake));
    const l = look.clone();
    if (shake > 0) l.add(V(noise1(t * 11, 4), noise1(t * 11, 5), 0).multiplyScalar(shake * 0.6));
    c.lookAt(l);
    if (c.fov !== fov) { c.fov = fov; c.updateProjectionMatrix(); }
  }

  hideAll() {
    for (const ch of [this.max, this.kp, this.ky, this.kg, this.kb, ...this.crowd]) { ch.reset(); ch.root.visible = false; ch.root.position.set(0, 0, 0); ch.root.rotation.set(0, 0, 0); }
    for (const a of this.auras) { a.update(0, 0); a.group.rotation.set(0, 0, 0); a.ground.visible = true; }
    for (const o of this.fx) o.visible = false;
    this.goldLight.intensity = 0; this.rimLight.intensity = 0; this.fill.intensity = 0;
    this.world.crystal.update(0, { visible: true });
  }

  place(ch, p, rotY = 0) { ch.root.visible = true; ch.root.position.copy(p); ch.root.rotation.y = rotY; return ch; }
  face(ch, target) { const p = ch.root.position; ch.root.rotation.y = Math.atan2(target.x - p.x, target.z - p.z); return ch; }

  // crowd standing on an arc around `center`, facing `look`
  crowdArc(list, center, r0, a0, a1, look, rows = 2, y = PLAZA_Y) {
    const n = list.length;
    list.forEach((c, i) => {
      const row = i % rows, k = Math.floor(i / rows) / Math.max(1, Math.ceil(n / rows) - 1);
      const a = lerp(a0, a1, k) + row * 0.08;
      const r = r0 + row * 2.3;
      this.place(c, V(center.x + Math.cos(a) * r, y, center.z + Math.sin(a) * r));
      this.face(c, look);
    });
  }

  // ------------------------------------------------------------ main
  update(t) {
    this.hideAll();
    const S = [
      [0, 5, this.sHook], [5, 12, this.sTown], [12, 20, this.sPurple], [20, 28, this.sYellow], [28, 36, this.sGold],
      [36, 46, this.sBlack], [46, 54, this.sWalk], [54, 62, this.sTouch], [62, 70, this.sSunset], [70, 78, this.sQuake],
      [78, 86, this.sRainbow], [86, 90.1, this.sEnd],
    ];
    for (const [a, b, fn] of S) if (t >= a && t < b) {
      const fx = Object.assign({ bloom: 0.25, vignette: 0.35, flash: 0, black: 0, exposure: 1.0 }, fn.call(this, t, t - a));
      // generic cut flashes
      for (const [tc, amt] of [[5, 0.9], [12, 0.35], [20, 0.35], [28, 0.35], [86, 0.5]]) {
        const d = t - tc;
        if (d >= 0 && d < 0.3) fx.flash = Math.max(fx.flash, amt * (1 - d / 0.3));
        if (d < 0 && d > -0.12) fx.flash = Math.max(fx.flash, amt * 0.6 * (1 + d / 0.12));
      }
      return fx;
    }
    return {};
  }

  // ============================================================ 0-5 HOOK
  sHook(t, lt) {
    const W = this.world, M = this.max;
    const P = V(0, PLAZA_Y, 10.5);
    W.setLighting(t, 'dusk', null, 0, P, 20);
    this.place(M, P, 0).idle(t);
    const tColor = this.wt('L01', 'color', 2.1);
    const blink = (lt > 1.35 && lt < 1.47) || (lt > 3.9 && lt < 4.02);
    M.setFace(blink ? 'blink' : (t > tColor - 0.15 ? 'grin' : 'smile'), t > tColor - 0.15 ? {} : { look: lt < 0.9 ? 0 : lt < 1.8 ? -8 : 0, blush: true });
    M.headPivot.rotation.z = 0.06 * Math.sin(lt * 1.3);
    M.headPivot.rotation.y = lt < 1.8 ? lerp(0, -0.18, smooth(0.8, 1.4, lt)) : lerp(-0.18, 0.05, smooth(1.8, 2.4, lt));
    // rainbow flicker behind him: the crystal + a big glow
    const fl = 0.75 + 0.25 * noise1(t * 9, 7) + 0.25 * Math.max(0, noise1(t * 23, 9));
    const hue = (t * 0.22) % 1;
    W.crystal.update(t, { color: hsl(hue, 0.95, 0.6), glow: 1.4 * fl + (t > tColor ? 0.4 : 0), beams: 0.7 * fl });
    this.maxGlow.visible = true; this.maxGlow.position.set(0, 5.2, 6.5);
    this.maxGlow.material.color.copy(hsl(hue + 0.15, 1, 0.6)); this.maxGlow.material.opacity = 0.55 * fl; this.maxGlow.scale.setScalar(14);
    this.rimLight.position.set(0, 6.5, 8.5); this.rimLight.color.copy(hsl(hue + 0.3, 1, 0.6)); this.rimLight.intensity = 50 * fl;
    this.fill.position.set(2, 6, 17); this.fill.color.set('#ffe9d6'); this.fill.intensity = 50;
    this.bokeh(t, P.clone().add(V(0, 4.5, 2.5)), 6);
    this.aM.update(t, 0.32 * Math.max(0, noise1(t * 6, 21) + 0.35) * (1 + 0.6 * smooth(tColor - 0.2, tColor + 0.2, t)), 1.0);
    this.aM.ground.visible = false;
    // camera: punchy zoom-in, then slow push
    const k = ease.outExpo(clamp(lt / 0.5));
    const d = lt < 0.5 ? lerp(12, 5.4, k) : lerp(5.4, 4.3, prog(lt, 0.5, 5, ease.inOut));
    const ang = 0.12 - 0.1 * prog(lt, 0, 5);
    this.setCam(V(P.x + Math.sin(ang) * d, P.y + 4.9, P.z + Math.cos(ang) * d), V(P.x, P.y + 3.95, P.z), 40);
    let flash = lt < 0.25 ? 0.7 * (1 - lt / 0.25) : 0;
    if (t > tColor - 0.05 && t < tColor + 0.3) flash = Math.max(flash, 0.25 * (1 - (t - tColor) / 0.35));
    return { bloom: 0.5, vignette: 0.5, flash };
  }

  bokeh(t, center, spread) {
    this.dust.obj.visible = true;
    const R = rng(5);
    const seeds = Array.from({ length: 90 }, () => [R(), R(), R(), R()]);
    this.dust.fill((i, o) => {
      const [a, b, c, d] = seeds[i];
      o.x = center.x + (a - 0.5) * spread * 2 + Math.sin(t * 0.5 + d * 6) * 0.4;
      o.y = center.y + (b - 0.5) * spread * 1.6 + ((t * 0.3 + c) % 1) * 1.2;
      o.z = center.z + (c - 0.5) * spread;
      const cc = hsl(a + t * 0.1, 1, 0.65); o.r = cc.r; o.g = cc.g; o.b = cc.b;
      o.a = 0.5 + 0.5 * Math.sin(t * 3 + d * 20); o.size = 0.12 + d * 0.15; o.rot = t;
    });
  }

  // ============================================================ 5-12 TOWN
  sTown(t, lt) {
    const W = this.world;
    if (t < 8.2) {
      W.setLighting(t, 'day', null, 0, V(0, 0, 0), 70);
      const k = prog(t, 5, 8.2, ease.inOut);
      const pos = V(lerp(-46, -30, k), lerp(42, 24, k), lerp(60, 42, k));
      this.setCam(pos, V(lerp(0, 2, k), lerp(6, 9, k), lerp(0, 5, k)), 46);
      // flyers
      const fly = [
        [this.kp, this.aP, V(-2, 20, 8), 15, 0.55, 0.3, 0],
        [this.ky, this.aY, V(-8, 25, 14), 20, 0.75, 2.2, 1],
        [this.kg, this.aG, V(6, 16, 2), 11, -0.6, 4.0, 2],
      ];
      for (const [ch, au, c, r, w, ph, i] of fly) {
        const path = (tt) => V(c.x + Math.cos(ph + w * tt) * r, c.y + Math.sin(tt * 1.7 + ph) * 1.2, c.z + Math.sin(ph + w * tt) * r);
        const p = path(t), q = path(t + 0.05);
        this.place(ch, p.clone().add(V(0, -2, 0)), Math.atan2(q.x - p.x, q.z - p.z));
        ch.fly(t);
        au.update(t, 0.85, 0.8); au.ground.visible = false; au.light.intensity = 0;
        this.trails[i].update(t, (tt) => path(tt).add(V(0, 0.2, 0)), 1.6, this.cam, 0.9);
      }
      // runners on the ring road
      const run = [[this.crowd[0], this.aC0, 0.32, 0.4], [this.crowd[1], this.aC1, 0.36, 3.4]];
      for (const [ch, au, w, ph] of run) {
        const a = ph + w * t, r = 18.25;
        this.place(ch, V(Math.cos(a) * r, 0, Math.sin(a) * r), Math.atan2(-Math.sin(a), Math.cos(a)));
        ch.run(t, 0.9); au.update(t, 0.8, 0.85);
      }
      // townsfolk on the plaza
      const spots = [[-7, 7], [-5, 8.5], [8, -6], [9, -4], [-9, -7], [4, 9], [6, 10], [-10, 3], [10, 5], [-3, -10]];
      spots.forEach(([x, z], i) => {
        const c = this.crowd[2 + i]; if (!c) return;
        this.place(c, V(x, PLAZA_Y, z)); this.face(c, V(spots[i ^ 1][0], 0, spots[i ^ 1][1])); c.idle(t);
        if (i % 3 === 0) c.arms(0, -2.6 - 0.3 * Math.sin(t * 6 + i), 0, 0.1);  // waving
      });
      this.aC2.update(t, 0.7, 0.8);
      W.crystal.update(t, { color: hsl(0.52 + 0.05 * Math.sin(t), 0.9, 0.62), glow: 1 });
      return { bloom: 0.3, vignette: 0.25 };
    }
    // line-up of the four tiers
    W.setLighting(t, 'day', null, 0, V(0, 0, 8), 18);
    const kids = [[this.kp, this.aP], [this.ky, this.aY], [this.kg, this.aG], [this.kb, this.aB]];
    const xs = [-6.6, -2.2, 2.2, 6.6];
    kids.forEach(([ch, au], i) => {
      this.place(ch, V(xs[i], PLAZA_Y, 8), 0).idle(t + i);
      au.update(t, 0.95, 0.95);
      if (i === 0) ch.arms(0, -2.5 - 0.25 * Math.sin(t * 7), 0, 0.1);
      if (i === 1) { ch.hips.position.y = 2 + Math.abs(Math.sin(t * 5)) * 0.25; }
      if (i === 2) ch.arms(-0.2, -0.9, -0.2, 0.9);
      if (i === 3) ch.arms(-1.25, 0.65, -1.25, -0.65);
    });
    this.kp.setFace('grin'); this.ky.setFace('grin'); this.kg.setFace('determined');
    const k = prog(t, 8.2, 12, ease.inOut);
    const cx = lerp(-8.8, 8.6, k);
    this.setCam(V(cx, 4.3, 18.5), V(cx + 1.2, 3.5, 8), 36);
    W.crystal.update(t, { color: hsl(0.52, 0.9, 0.62), glow: 1 });
    return { bloom: 0.35, vignette: 0.3 };
  }

  // ============================================================ 12-20 PURPLE
  sPurple(t, lt) {
    const W = this.world, K = this.kp, A = this.aP;
    const P = V(-8.5, PLAZA_Y, -4.5);
    W.setLighting(t, 'day', null, 0, P, 16);
    const camDir = V(0.62, 0, 0.78).normalize();
    const look = P.clone().add(camDir.clone().multiplyScalar(10));
    this.place(K, P); this.face(K, look); K.idle(t);
    const tThat = this.wt('L05', 'that', 16.0);
    const tLift0 = 12.25, tCrate = tThat - 1.25, tDrop = tThat + 0.15;
    // pose
    const cast = prog(t, 12.0, 12.5, ease.out);
    K.arms(-1.5 * cast, -0.25 * cast, -1.5 * cast, 0.25 * cast);
    K.armL.rotation.x += 0.12 * Math.sin(t * 3) * cast; K.armR.rotation.x += 0.12 * Math.sin(t * 3 + 1) * cast;
    let face = 'determined';
    if (t > 13.0 && t < tCrate) face = 'grin';
    A.update(t, 0.35 + 0.65 * cast + (t > tCrate && t < tDrop ? 0.35 : 0), 1);
    // blocks
    const fwd = look.clone().sub(P).setY(0).normalize(), side = V(fwd.z, 0, -fwd.x);
    const crateP = P.clone().add(fwd.clone().multiplyScalar(3.2)).add(side.clone().multiplyScalar(-2.6));
    crateP.y = PLAZA_Y;
    this.blocks.forEach((b, i) => {
      b.visible = true;
      const home = P.clone().add(fwd.clone().multiplyScalar(2.2 + (i % 3) * 0.9)).add(side.clone().multiplyScalar((i - 3) * 0.75));
      home.y = PLAZA_Y + 0.43;
      const lift = prog(t, tLift0 + i * 0.1, tLift0 + 0.9 + i * 0.1, ease.out);
      const a = i / 7 * Math.PI * 2 + t * 1.15;
      const orbit = P.clone().add(V(Math.cos(a) * (2.7 + (i % 2) * 0.6), 2.6 + (i % 3) * 0.9 + Math.sin(t * 2 + i) * 0.3, Math.sin(a) * (2.7 + (i % 2) * 0.6)));
      let pos = home.clone().lerp(orbit, lift);
      // drop when she gives up on the crate
      const fall = clamp((t - tDrop - i * 0.04) / 0.45);
      if (t > tDrop) {
        const from = (() => { const aa = i / 7 * Math.PI * 2 + (tDrop) * 1.15; return P.clone().add(V(Math.cos(aa) * (2.7 + (i % 2) * 0.6), 2.6 + (i % 3) * 0.9 + Math.sin(tDrop * 2 + i) * 0.3, Math.sin(aa) * (2.7 + (i % 2) * 0.6))); })();
        const land = from.clone(); land.y = PLAZA_Y + 0.43;
        pos = from.clone().lerp(land, ease.in(fall));
        const bounce = t - tDrop - i * 0.04 - 0.45;
        if (bounce > 0) pos.y = PLAZA_Y + 0.43 + Math.abs(Math.sin(bounce * 9)) * 0.35 * Math.exp(-bounce * 6);
      }
      b.position.copy(pos);
      b.rotation.set(t * 0.8 * lift + i, t * 1.1 * lift + i * 2, 0);
      if (t > tDrop) b.rotation.set(i, i * 2, 0);
      const glow = t > tDrop ? 1 - clamp((t - tDrop) / 0.3) : lift;
      b.userData.shell.material.opacity = 0.3 * glow; b.userData.glow.material.opacity = 0.55 * glow;
      b.userData.shell.visible = b.userData.glow.visible = glow > 0.01;
    });
    // crate attempt
    this.crate.visible = true; this.crate.position.copy(crateP); this.crate.rotation.set(0, 0.3, 0);
    if (t > tCrate && t < tDrop + 0.5) {
      const s = clamp((t - tCrate) / 0.4);
      const up = t < tDrop ? 0.18 * s + 0.06 * Math.sin(t * 40) : Math.max(0, 0.2 - (t - tDrop) * 2);
      this.crate.position.y += up;
      this.crate.rotation.z = (t < tDrop ? 0.05 * Math.sin(t * 33) : 0);
      this.face(K, crateP);
      K.arms(-1.7 + 0.08 * Math.sin(t * 45), -0.15, -1.7 + 0.08 * Math.sin(t * 47), 0.15);
      face = t < tDrop ? 'nervous' : face;
    }
    if (t >= tDrop) {      // shrug
      const s = prog(t, tDrop + 0.25, tDrop + 0.6, ease.outBack);
      this.face(K, look);
      K.arms(-0.6 * s, -1.0 * s, -0.6 * s, 1.0 * s);
      K.headPivot.rotation.z = 0.18 * s;
      face = 'smirk';
    }
    K.setFace(face);
    // camera
    let pos, tgt, fov = 38;
    if (t < tCrate - 0.1) {
      const k = prog(t, 12, tCrate - 0.1);
      const d = lerp(15, 10.5, k), a = lerp(-0.25, 0.08, k);
      const dir = camDir.clone().applyAxisAngle(V(0, 1, 0), a);
      pos = P.clone().add(dir.multiplyScalar(d)).add(V(0, lerp(5.5, 4.6, k), 0));
      tgt = P.clone().add(V(0, 3.0, 0));
    } else if (t < tDrop + 1.6) {
      const mid = P.clone().lerp(crateP, 0.5);
      const k = prog(t, tCrate - 0.1, tCrate + 0.25, ease.outExpo);
      const dir = camDir.clone().applyAxisAngle(V(0, 1, 0), -0.35);
      pos = mid.clone().add(dir.multiplyScalar(lerp(13, 9.5, k))).add(V(0, 3.8, 0));
      tgt = mid.clone().add(V(0, 2.2, 0));
    } else {
      const k = prog(t, tDrop + 1.6, 20);
      const dir = camDir.clone().applyAxisAngle(V(0, 1, 0), lerp(0.2, 0.45, k));
      pos = P.clone().add(dir.multiplyScalar(lerp(9.5, 11.5, k))).add(V(0, 4.2, 0));
      tgt = P.clone().add(V(0, 3.2, 0));
    }
    const shake = t > tDrop + 0.3 && t < tDrop + 0.6 ? 0.12 : 0;
    this.setCam(pos, tgt, fov, shake, t);
    W.crystal.update(t, { color: hsl(0.52, 0.9, 0.62), glow: 1 });
    // a couple of kids in the background
    this.place(this.crowd[3], V(-15, 0, -11)).idle(t); this.face(this.crowd[3], P);
    this.place(this.crowd[8], V(-13.5, PLAZA_Y, -12.5)).idle(t + 2); this.face(this.crowd[8], P);
    return { bloom: 0.4, vignette: 0.3 };
  }

  // ============================================================ 20-28 YELLOW
  sYellow(t, lt) {
    const W = this.world, K = this.ky, A = this.aY;
    const a0 = 0.62, r = 18.25;
    const Y0 = V(Math.cos(a0) * r, 0, Math.sin(a0) * r);
    const T = V(6.5, PLAZA_Y, 6.5);              // tag group center
    const tDash = 21.9, tTag0 = 22.55, tTag1 = 24.15;
    W.setLighting(t, 'day', null, 0, t < tTag0 ? Y0 : T, 22);
    W.crystal.update(t, { color: hsl(0.52, 0.9, 0.62), glow: 1 });
    const tangent = (a) => Math.atan2(-Math.sin(a), Math.cos(a));
    const taggers = [this.crowd[4], this.crowd[6], this.crowd[9]];
    taggers.forEach((c, i) => {
      const a = i / 3 * Math.PI * 2 + 0.4;
      this.place(c, T.clone().add(V(Math.cos(a) * 1.6, 0, Math.sin(a) * 1.6))); this.face(c, V(20, 0, 20)); c.idle(t + i);
      c.setFace('smile');
      const tg = tTag0 + 0.35 + i * 0.42;
      if (t > tg) {
        const s = t - tg;
        c.root.rotation.y += Math.min(s, 0.6) * 18 * Math.exp(-s * 1.2);
        c.root.rotation.z = 0.12 * Math.sin(t * 6 + i) * Math.exp(-s * 0.4);
        c.setFace('shock');
        if (s > 1.4) c.setFace('nervous');
      }
    });
    // yellow kid path
    let p, heading, mode;
    if (t < tDash) { p = Y0.clone(); heading = tangent(a0) + 0.0; mode = 'ready'; }
    else if (t < tTag0) {
      const s = t - tDash, a = a0 + 0.6 * s + 5.5 * s * s;
      p = V(Math.cos(a) * r, 0, Math.sin(a) * r); heading = tangent(a); mode = 'dash';
    } else if (t < tTag1) {
      const s = t - tTag0, a = s * 9.5;
      p = T.clone().add(V(Math.cos(a) * 3.4, 0, Math.sin(a) * 3.4)); heading = Math.atan2(-Math.sin(a), Math.cos(a)); mode = 'dash';
    } else { p = T.clone().add(V(3.6, 0, 1.4)); heading = 0; mode = 'pose'; }
    this.place(K, p, heading);
    if (mode === 'ready') {
      K.hips.position.y = 1.75; K.legL.rotation.x = -0.6; K.legR.rotation.x = 0.45; K.hips.rotation.x = 0.35;
      K.arms(0.9, -0.2, 0.9, 0.2); K.headPivot.rotation.x = -0.25;
      K.setFace(t < 21.0 ? 'determined' : 'grin');
      this.face(K, V(Y0.x - 3, 0, Y0.z + 6));
      K.root.rotation.y = lerp(K.root.rotation.y, tangent(a0), smooth(21.4, 21.9, t));
    } else if (mode === 'dash') { K.run(t, 2.2); K.hips.rotation.x = 0.55; K.setFace('grin'); }
    else { this.face(K, T.clone().add(V(14, 0, 12))); K.idle(t); K.arms(-0.3, -0.9, -0.3, 0.9); K.setFace('grin'); }
    A.update(t, mode === 'dash' ? 1.2 : 1.0, 1);
    // trail (dash + circles)
    const pathFn = (tt) => {
      if (tt < tDash) return Y0.clone().add(V(0, 2.6, 0));
      if (tt < tTag0) { const s = tt - tDash, a = a0 + 0.6 * s + 5.5 * s * s; return V(Math.cos(a) * r, 2.6, Math.sin(a) * r); }
      const s = Math.min(tt, tTag1) - tTag0, a = s * 9.5; return T.clone().add(V(Math.cos(a) * 3.4, 2.4, Math.sin(a) * 3.4));
    };
    if (t > tDash) {
      const alpha = t < tTag1 ? 1 : 1 - clamp((t - tTag1) / 0.6);
      if (alpha > 0) this.trails[3].update(Math.min(t, tTag1 + 0.6), pathFn, t < tTag0 ? 0.45 : 0.75, this.cam, alpha, tDash);
      this.trails[3].mesh.visible = alpha > 0;
    }
    // sparks crackling around him
    this.ySparks.obj.visible = true;
    const R = rng(8); const sd = Array.from({ length: 120 }, () => [R(), R(), R(), R()]);
    this.ySparks.fill((i, o) => {
      const [a, b, c, d] = sd[i];
      const ph = (t * 2.5 + a) % 1;
      if (mode === 'dash' && i > 60) return false;
      const ang = b * 6.28 + t * 3, rr = 1.2 + c * 1.6 + ph;
      o.x = p.x + Math.cos(ang) * rr; o.y = 0.4 + d * 5.5 + ph * 1.5; o.z = p.z + Math.sin(ang) * rr;
      o.r = 1; o.g = 0.92; o.b = 0.4; o.a = Math.sin(ph * Math.PI) * (Math.sin(t * 30 + i) > 0.2 ? 1 : 0.2); o.size = 0.25 + d * 0.35; o.rot = t * 4 + a;
    });
    // dust puffs where he started / along the dash
    this.puffs.obj.visible = t > tDash;
    if (t > tDash) this.puffs.fill((i, o) => {
      const t0 = tDash + i * 0.016, s = t - t0;
      if (s < 0 || s > 1.4) return false;
      const q = pathFn(Math.min(t0, tTag1));
      o.x = q.x + Math.sin(i * 7) * 0.6; o.y = 0.5 + s * 1.2; o.z = q.z + Math.cos(i * 5) * 0.6;
      o.r = 0.92; o.g = 0.85; o.b = 0.72; o.a = 0.55 * (1 - s / 1.4); o.size = 1.5 + s * 3; o.rot = i;
    });
    // dizzy stars over tagged kids
    this.stars.obj.visible = t > tTag0 + 0.5;
    this.stars.fill((i, o) => {
      const c = taggers[Math.floor(i / 12)], k = i % 12;
      const tg = tTag0 + 0.35 + Math.floor(i / 12) * 0.42;
      if (t < tg + 0.3) return false;
      const head = c.root.position.clone().add(V(0, 6.0, 0));
      const a = k / 12 * 6.283 + t * 4;
      o.x = head.x + Math.cos(a) * 0.9; o.y = head.y + Math.sin(t * 5 + k) * 0.1; o.z = head.z + Math.sin(a) * 0.9;
      o.r = 1; o.g = 0.95; o.b = 0.5; o.a = k % 3 === 0 ? 1 : 0; o.size = 0.5; o.rot = t;
    });
    // camera
    if (t < tDash) {
      const k = prog(t, 20, tDash);
      const dir = V(-0.25, 0, 1).normalize();
      this.setCam(Y0.clone().add(dir.multiplyScalar(lerp(9, 6, k))).add(V(0.5, lerp(1.6, 2.2, k), 0)), Y0.clone().add(V(0, 3.4, 0)), 40);
    } else if (t < tTag0) {
      const k = prog(t, tDash, tTag0, ease.in);
      const camP = V(-2, 8, 14);
      this.setCam(camP, p.clone().add(V(0, 2.5, 0)).lerp(T.clone().add(V(0, 2.5, 0)), k * 0.4), 46, 0.06, t, 1);
    } else {
      const k = prog(t, tTag0, 28);
      const a = lerp(0.9, 1.9, k), d = lerp(13, 10, k);
      this.setCam(T.clone().add(V(Math.cos(a) * d, lerp(8.5, 5.5, k), Math.sin(a) * d)), T.clone().add(V(1, 2.6, 0.4)), 40);
    }
    return { bloom: 0.45, vignette: 0.3 };
  }

  // ============================================================ 28-36 GOLD
  sGold(t, lt) {
    const W = this.world, K = this.kg, A = this.aG;
    const G = V(0, 0, 23.5);
    W.setLighting(t, 'day', null, 0, G.clone().add(V(0, 0, 8)), 26);
    W.crystal.update(t, { color: hsl(0.12, 0.9, 0.62), glow: 1.1 });
    this.place(K, G, 0).idle(t);
    A.update(t, 1.05, 1.05);
    const shots = [29.45, 30.05, 30.65];
    const tUp = 32.7;
    const handOf = (side) => K.root.position.clone().add(V(side * 1.5, 3.9, 1.8));
    // punches
    let punch = 0, side = 1;
    shots.forEach((ts, i) => { const s = t - ts; if (s > -0.15 && s < 0.35) { punch = Math.max(punch, s < 0 ? 1 + s / 0.15 : 1 - s / 0.35); side = i % 2 ? -1 : 1; } });
    if (side > 0) K.arms(-0.2, -0.3, -1.57 * punch - 0.1, 0.2); else K.arms(-1.57 * punch - 0.1, -0.2, -0.2, 0.3);
    K.setFace('determined');
    // cheering crowd behind/around him
    const crowd = this.crowd.slice(0, 10);
    crowd.forEach((c, i) => {
      const sgn = i % 2 ? 1 : -1, j = Math.floor(i / 2);
      this.place(c, V(G.x + sgn * (5.2 + (j % 2) * 1.8), 0, G.z + 1 + j * 2.2)); this.face(c, V(0, 4, 42));
      const cheer = t > 31.0 ? 1 : 0.3;
      c.root.position.y += Math.abs(Math.sin(t * 7 + i)) * 0.6 * cheer;
      c.arms(-0.4, -2.7 + 0.3 * Math.sin(t * 9 + i), -0.4, 2.7 - 0.3 * Math.sin(t * 9 + i));
      c.setFace(t > 30.0 ? 'grin' : 'smile');
    });
    // hero pose at the end
    if (t > tUp - 0.4) {
      const s = prog(t, tUp - 0.4, tUp, ease.outBack);
      K.arms(-0.2, -0.5, -3.0 * s, 0.1); K.setFace('grin');
    }
    // blasts
    const targets = this.targets;
    targets.forEach((g, i) => { g.visible = t < shots[i] + 0.5; g.position.copy(g.userData.home); g.position.y += Math.sin(t * 1.5 + i) * 0.4; g.rotation.y = Math.sin(t + i) * 0.3; });
    const allShots = [...shots.map((ts, i) => [ts, targets[i].userData.home.clone(), i]), [tUp, G.clone().add(V(0, 30, 6)), 3]];
    let lightI = 0; const lightP = V();
    allShots.forEach(([ts, dest, i]) => {
      const b = this.blasts[i], tr = this.trails[i < 3 ? i : 2];
      const s = (t - ts) / (i === 3 ? 0.75 : 0.5);
      const from = i === 3 ? K.root.position.clone().add(V(1.5, 6.5, 0.3)) : handOf(i % 2 ? -1 : 1);
      const path = (tt) => { const k = clamp((tt - ts) / (i === 3 ? 0.75 : 0.5)); const q = from.clone().lerp(dest, k); q.y += Math.sin(k * Math.PI) * 1.2; return q; };
      if (s >= 0 && s <= 1) {
        b.visible = true; b.position.copy(path(t));
        tr.update(t, path, 0.25, this.cam, 1, ts); tr.mesh.visible = true; tr.color.set('#ffc21a');
        lightI = Math.max(lightI, 40); lightP.copy(b.position);
      }
      const e = t - (ts + (i === 3 ? 0.75 : 0.5));
      if (e > 0 && e < 0.4) { lightI = Math.max(lightI, 120 * (1 - e / 0.4)); lightP.copy(dest); }
    });
    this.goldLight.intensity = lightI; this.goldLight.position.copy(lightP);
    // explosion sparkles
    this.goldBurst.obj.visible = true;
    const R = rng(21); const sd = Array.from({ length: 420 }, () => [R(), R(), R(), R()]);
    this.goldBurst.fill((j, o) => {
      const which = Math.floor(j / 105);
      const [ts, dest] = allShots[which];
      const te = ts + (which === 3 ? 0.75 : 0.5), s = t - te;
      const life = which === 3 ? 2.6 : 1.3;
      if (s < 0 || s > life) return false;
      const [a, b, c, d] = sd[j];
      const th = a * 6.283, ph = Math.acos(2 * b - 1);
      const dir = V(Math.sin(ph) * Math.cos(th), Math.cos(ph), Math.sin(ph) * Math.sin(th));
      const sp = (which === 3 ? 13 : 7) * (0.4 + c * 0.6);
      const dist = sp * (1 - Math.exp(-s * 2.2)) / 2.2;
      o.x = dest.x + dir.x * dist; o.y = dest.y + dir.y * dist - 2.2 * s * s; o.z = dest.z + dir.z * dist;
      o.r = 1; o.g = 0.78 + d * 0.2; o.b = 0.25 + d * 0.3; o.a = (1 - s / life) * (0.7 + 0.3 * Math.sin(t * 25 + j)); o.size = 0.5 + d * 0.6; o.rot = t * 3 + a * 6;
    });
    // target fragments
    shots.forEach((ts, i) => { if (t > ts + 0.5 && t < ts + 2.2 && i === Math.floor((t - 29.95) / 0.6 + 0.0001) + 0) {} });
    const lastHit = shots.filter(ts => t > ts + 0.5).pop();
    if (lastHit !== undefined) { const i = shots.indexOf(lastHit); this.frags.update(t, lastHit + 0.5, targets[i].userData.home, 1.8); }
    // golden rain after the final burst
    this.goldRain.obj.visible = t > tUp + 0.75;
    const R2 = rng(22); const sd2 = Array.from({ length: 220 }, () => [R2(), R2(), R2(), R2()]);
    this.goldRain.fill((j, o) => {
      const [a, b, c, d] = sd2[j];
      const s = t - (tUp + 0.75) - a * 0.8;
      if (s < 0) return false;
      o.x = G.x + (b - 0.5) * 34; o.z = G.z + 6 + (c - 0.5) * 30; o.y = 26 - s * (3 + d * 3) + Math.sin(s * 3 + j) * 0.3;
      if (o.y < 0.3) return false;
      o.r = 1; o.g = 0.85; o.b = 0.35; o.a = 0.6 + 0.4 * Math.sin(t * 12 + j); o.size = 0.35 + d * 0.35; o.rot = t * 2 + j;
    });
    // camera
    if (t < 29.25) {
      const k = prog(t, 28, 29.25);
      this.setCam(G.clone().add(V(lerp(2.5, 1.4, k), 1.3, lerp(8.5, 6.2, k))), G.clone().add(V(0, 4.3, 0)), 42);
    } else if (t < 31.3) {
      const k = prog(t, 29.25, 31.3);
      this.setCam(G.clone().add(V(lerp(2.4, 3.0, k), 4.2, -8.5)), V(lerp(-1, 1, k), 8.5, G.z + 15), 46, 0, t, 1);
    } else {
      const k = prog(t, 31.3, 36);
      const a = lerp(1.05, 1.9, k), d = lerp(10.5, 12.5, k);
      const up = prog(t, tUp + 0.4, tUp + 1.2) * (1 - prog(t, tUp + 1.6, 35.6));
      this.setCam(G.clone().add(V(Math.cos(a) * d, lerp(2.2, 3.5, k), Math.sin(a) * d)), G.clone().add(V(0, 4.2 + up * 7, 0)), 44);
    }
    return { bloom: 0.5, vignette: 0.3 };
  }

  // ============================================================ 36-46 BLACK
  sBlack(t, lt) {
    const W = this.world, K = this.kb, A = this.aB;
    const kz = lerp(44, 35.5, prog(t, 36, 46, x => x));
    const P = V(0, 0, kz);
    const light = 0.0 + 0.8 * Math.max(0, 1 - Math.abs(t - 36.05) / 0.12) + 0.6 * Math.max(0, 1 - Math.abs(t - 41.6) / 0.1) + 0.4 * Math.max(0, 1 - Math.abs(t - 41.85) / 0.08);
    W.setLighting(t, 'dark', null, 0, V(0, 0, 32), 22);
    W.sky.material.uniforms.flash.value = light * 0.6;
    W.crystal.update(t, { color: hsl(0.75, 0.6, 0.35), glow: 0.4 });
    this.place(K, P, Math.PI).walk(t, 0.55, 0.35);
    K.arms(K.armL.rotation.x * 0.5, -0.12, K.armR.rotation.x * 0.5, 0.12);
    K.headPivot.rotation.x = 0.12;
    A.update(t, 1.1, 1.08);
    this.rimLight.position.set(0, 7, kz + 3); this.rimLight.color.set('#b8a8ff'); this.rimLight.intensity = 60;
    // crowd on the road, stepping back + gasp
    const tGasp = 38.1;
    const crowd = this.crowd.slice(0, 11);
    crowd.forEach((c, i) => {
      const x = (i - 5) * 1.9 + (i % 2) * 0.4, z0 = 28.5 - (i % 3) * 1.6;
      const back = prog(t, tGasp - 0.1 + (i % 3) * 0.06, tGasp + 0.6, ease.out) * 2.4;
      this.place(c, V(x * 1.0, 0, z0 - back)); this.face(c, P);
      c.idle(t + i);
      const g = prog(t, tGasp - 0.1, tGasp + 0.2, ease.out);
      c.arms(-1.0 * g, -0.4 * g, -1.0 * g, 0.4 * g);
      if (t > tGasp - 0.1 && t < tGasp + 0.6) c.walk(t, -1.2, 0.35);
      c.setFace(t > tGasp - 0.15 ? (i % 2 ? 'shock' : 'nervous') : 'smile', t > tGasp ? { wide: true } : {});
      c.root.rotation.z = t > tGasp ? 0.04 * Math.sin(t * 20 + i) : 0;   // trembling
    });
    // camera
    let fx = { bloom: 0.45, vignette: 0.55, flash: light * 0.35, flashColor: '#d9d0ff' };
    if (t < 38.0) {
      const k = prog(t, 36, 38);
      this.setCam(P.clone().add(V(1.1, 0.9, -lerp(8, 6, k))), P.clone().add(V(0, 4.0, 0)), 44);
    } else if (t < 40.6) {
      const k = prog(t, 38, 40.6);
      this.setCam(P.clone().add(V(-2.6, 5.8, 6.5 - k * 0.8)), V(0, 3.2, 27.5), 44, 0, t, 1);
    } else if (t < 43.2) {
      const k = prog(t, 40.6, 43.2);
      this.setCam(P.clone().add(V(0.5, 5.0, -lerp(4.6, 3.4, k))), P.clone().add(V(0, 4.55, 0)), 40);
    } else {
      const k = prog(t, 43.2, 46);
      this.setCam(V(lerp(1.5, 0.5, k), lerp(14, 17, k), kz - 21 - k * 2), V(0, 2, kz - 5), 44, 0, t, 1);
    }
    fx.black = Math.max(prog(t, 45.55, 46.0, ease.in), t < 36.15 ? 1 - (t - 36) / 0.15 : 0);
    return fx;
  }

  // ============================================================ 46-54 WALK
  maxPathZ(t) {   // walk from the south road up to the pedestal
    return lerp(19.5, 3.5, prog(t, 45.6, 53.4, x => x < 0.85 ? x / 0.85 * 0.93 : 0.93 + (x - 0.85) / 0.15 * 0.07));
  }
  groundY(z) {
    let y = 0;
    y = lerp(y, PLAZA_Y, smooth(15.7, 15.3, z));
    y = lerp(y, 0.675, smooth(4.95, 4.65, z));
    y = lerp(y, 1.125, smooth(3.95, 3.65, z));
    return y;
  }
  squareCrowd(t, look, mood, closed = false) {
    const list = this.crowd;
    list.forEach((c, i) => {
      const left = i % 2 === 0, j = Math.floor(i / 2);
      let a = left ? lerp(2.35, 1.82, j / 6) : lerp(0.79, 1.32, j / 6);
      if (closed) a = left ? lerp(2.35, 1.62, j / 6) : lerp(0.79, 1.52, j / 6);   // Max is on the pedestal: close the aisle
      const r = 11.2 + (j % 2) * 2.3;
      this.place(c, V(Math.cos(a) * r, PLAZA_Y, Math.sin(a) * r)); this.face(c, look);
      c.idle(t + i * 0.7);
      if (mood === 'watch') c.setFace(i % 3 === 0 ? 'nervous' : 'smile');
    });
    this.aC0.update(t, 0.6, 0.85); this.aC1.update(t, 0.6, 0.85); this.aC2.update(t, 0.6, 0.85);
  }

  sWalk(t, lt) {
    const W = this.world, M = this.max;
    const z = this.maxPathZ(t), y = this.groundY(z);
    const P = V(0, y, z);
    W.setLighting(t, 'afternoon', null, 0, V(0, 0, 8), 20);
    const hue = 0.52 + 0.08 * Math.sin(t * 0.8);
    W.crystal.update(t, { color: hsl(hue, 0.9, 0.62), glow: 1.15 + 0.15 * Math.sin(t * 2.5) });
    const moving = t < 53.4;
    this.place(M, P, Math.PI);
    if (moving) M.walk(t, 0.85, 0.45); else M.idle(t);
    M.setFace(t < 47.2 ? 'smile' : 'nervous');
    M.headPivot.rotation.x = -0.08;
    this.squareCrowd(t, P, 'watch');
    const fx = { bloom: 0.4, vignette: 0.35, black: 1 - prog(t, 46.0, 46.45) };
    if (t < 48.7) {
      const k = prog(t, 46, 48.7);
      this.setCam(P.clone().add(V(lerp(2.6, 2.0, k), 6.6, 9.5)), V(0, lerp(4.8, 4.4, k), 0), 44, 0, t, 1);
    } else if (t < 50.6) {
      const k = prog(t, 48.7, 50.6);
      this.setCam(P.clone().add(V(1.1, 4.9, -lerp(5.8, 5.4, k))), P.clone().add(V(0, 4.2, 0)), 46, 0, t, 1);
    } else {
      const k = prog(t, 50.6, 54);
      this.setCam(V(lerp(12.5, 11.5, k), lerp(7.6, 7.0, k), lerp(9.5, 8.5, k)), V(0, 4.4, 3), 44, 0, t, 1);
    }
    return fx;
  }

  // ============================================================ 54-62 TOUCH
  sTouch(t, lt) {
    const W = this.world, M = this.max;
    const P = V(0, 1.125, 3.5);
    W.setLighting(t, 'afternoon', null, 0, V(0, 0, 6), 18);
    const tTouch = 54.95, tDark = this.wt('L15', 'nothing', 56.4) - 0.05, tLaugh = tDark + 1.25, tTurn = tDark + 0.9;
    // crystal: hum -> flicker -> dark
    let col = hsl(0.52, 0.9, 0.62), glow = 1.15, dark = 0;
    if (t > tTouch) {
      const k = clamp((t - tTouch) / (tDark - tTouch));
      col = hsl((0.52 + k * 1.6 + t * 0.4) % 1, 0.95, 0.6); glow = 1.15 + k * 1.0;
      if (k > 0.6) glow *= (Math.sin(t * 60) > 0 ? 1 : 0.25);
    }
    if (t > tDark) { dark = clamp((t - tDark) / 0.35); glow = Math.max(0, 1 - (t - tDark) / 0.3) * 0.6 * (Math.sin(t * 50) > 0 ? 1 : 0); }
    W.crystal.update(t, { color: col, glow, dark });
    // Max
    this.place(M, P, Math.PI).idle(t);
    const reach = prog(t, 54.15, tTouch, ease.inOut) * (1 - prog(t, tDark + 0.3, tDark + 0.8));
    M.arms(-0.1, -0.1, -1.52 * reach, 0.18 * reach);
    M.setFace(t < tTouch + 0.2 ? 'nervous' : t < tDark ? 'shock' : t < tLaugh ? 'nervous' : 'sad', t > tLaugh + 2 ? { tear: true } : {});
    const turn = prog(t, tTurn, tTurn + 0.7, ease.inOut);
    M.root.rotation.y = Math.PI - turn * Math.PI;
    if (t > tLaugh + 1.5) M.headPivot.rotation.x = 0.35 * prog(t, tLaugh + 1.5, tLaugh + 2.2);
    // crowd: silence -> laugh + point
    this.squareCrowd(t, P, 'watch', true);
    if (t > tLaugh) {
      this.crowd.forEach((c, i) => {
        const s = t - tLaugh - (i % 4) * 0.08;
        if (s < 0) return;
        c.setFace('laugh');
        c.hips.position.y = 2 + Math.abs(Math.sin(t * 9 + i)) * 0.15;
        c.torso.rotation.x = -0.15 + 0.1 * Math.sin(t * 9 + i);
        if (i % 2) c.arms(-0.6, 0.35, -1.45 + 0.05 * Math.sin(t * 9), 0.05); else c.arms(-1.45 + 0.05 * Math.sin(t * 9), -0.05, -0.7, -0.35);
      });
    } else if (t > tDark) this.crowd.forEach(c => c.setFace('shock'));
    // sparkles while humming, smoke puffs on fizzle
    this.swirl.obj.visible = t > tTouch && t < tDark + 0.4;
    if (this.swirl.obj.visible) {
      const R = rng(31); const sd = Array.from({ length: 320 }, () => [R(), R(), R(), R()]);
      const k = clamp((t - tTouch) / (tDark - tTouch));
      this.swirl.fill((i, o) => {
        if (i > 140) return false;
        const [a, b, c, d] = sd[i];
        const ph = (t * 0.8 + a) % 1, ang = b * 6.28 + t * 2;
        o.x = Math.cos(ang) * (2.2 + c); o.z = Math.sin(ang) * (2.2 + c); o.y = 1.2 + ph * 9;
        const cc = hsl((a + t * 0.5) % 1, 1, 0.65); o.r = cc.r; o.g = cc.g; o.b = cc.b;
        o.a = Math.sin(ph * Math.PI) * k * (t > tDark ? 0 : 1); o.size = 0.3 + d * 0.3; o.rot = t;
      });
    }
    this.fizzle.obj.visible = t > tDark;
    if (t > tDark) this.fizzle.fill((i, o) => {
      const s = t - tDark - i * 0.02; if (s < 0 || s > 2) return false;
      o.x = Math.sin(i * 2.3) * 1.6; o.y = 3 + (i % 7) + s * 1.5; o.z = Math.cos(i * 2.3) * 1.6;
      o.r = 0.55; o.g = 0.55; o.b = 0.6; o.a = 0.45 * (1 - s / 2); o.size = 1.6 + s * 2; o.rot = i;
    });
    // camera
    if (t < 55.75) {
      const k = prog(t, 54, 55.75);
      this.setCam(V(lerp(-9.2, -7.8, k), lerp(6.4, 5.9, k), lerp(6.6, 5.6, k)), V(-0.6, 4.6, 2.2), 42, 0, t, 1);
    } else if (t < tLaugh) {
      const k = prog(t, 55.75, tLaugh);
      this.setCam(V(lerp(-12.5, -11.5, k), lerp(11.5, 10.5, k), lerp(6.5, 5.5, k)), V(0, 4.2, 2.5), 44, 0, t, 1);
    } else if (t < 60.6) {
      const k = prog(t, tLaugh, 60.6);
      const look = V(lerp(-7, 7, k), 3.9, 12);
      this.setCam(V(lerp(2.4, -2.4, k), 6.0, 5.4), look, 50, 0, t, 1);
    } else {
      const k = prog(t, 60.6, 62);
      this.setCam(V(0.5, 5.25, 3.5 + lerp(4.6, 3.9, k)), V(0, 4.75, 3.5), 40);
    }
    return { bloom: 0.4, vignette: t > tDark ? 0.5 : 0.35, black: prog(t, 61.6, 62.0, ease.in) };
  }

  // ============================================================ 62-70 SUNSET
  ledgeSpot() {
    const a = (19 + 0.5) / 32 * Math.PI * 2;
    const out = V(Math.cos(a), 0, Math.sin(a));
    return { a, out, P: out.clone().multiplyScalar(15.25), rotOut: Math.atan2(out.x, out.z), rotIn: Math.atan2(-out.x, -out.z) };
  }

  sSunset(t, lt) {
    const W = this.world, M = this.max;
    const L = this.ledgeSpot();
    W.setLighting(t, 'sunset', null, 0, L.P, 22);
    W.crystal.update(t, { color: hsl(0.6, 0.2, 0.4), glow: 0, dark: 1 });
    this.place(M, L.P, L.rotOut).sit(1.0, 0.5, t);
    M.setFace('sad', { tear: t > 64.5 });
    const fx = { bloom: 0.5, vignette: 0.5, black: 1 - prog(t, 62.0, 62.6) };
    const side = V(-L.out.z, 0, L.out.x);
    if (t < 66.0) {
      const k = prog(t, 62, 66);
      const pos = L.P.clone().addScaledVector(L.out, -lerp(13, 10, k)).addScaledVector(side, lerp(3.5, 2.5, k)).add(V(0, lerp(5.5, 4.5, k), 0));
      this.setCam(pos, L.P.clone().addScaledVector(L.out, 8).add(V(0, 3.6, 0)), 42, 0, t, 1);
    } else {
      const k = prog(t, 66, 70);
      const pos = L.P.clone().addScaledVector(L.out, lerp(7.5, 6.0, k)).addScaledVector(side, lerp(-1.6, -0.6, k)).add(V(0, lerp(3.6, 3.3, k), 0));
      this.setCam(pos, L.P.clone().add(V(0, 3.2, 0)), 40, 0, t, 1.3);
    }
    return fx;
  }

  // ============================================================ 70-78 QUAKE
  sQuake(t, lt) {
    const W = this.world, M = this.max;
    const L = this.ledgeSpot();
    const k0 = prog(t, 70, 73.5);
    W.setLighting(t, 'sunset', 'dusk', k0, L.P, 22);
    const tStand = 73.55, tWait = this.ls('L19'), crack = prog(t, 71.3, 75.8, x => x);
    const beams = prog(t, 71.8, 76.5, x => x);
    const shake = 0.06 + 0.1 * prog(t, 70, 70.4) + 0.12 * prog(t, 75.5, 78);
    W.crystal.update(t, { color: hsl((t * 0.5) % 1, 0.95, 0.6), glow: 0.3 + crack * 1.6, dark: clamp(1 - crack * 1.3), crack: clamp(crack * 1.5), beams, shake: shake * 0.6 });
    // Max: sits -> looks up -> stands and turns toward the crystal
    this.place(M, L.P, L.rotOut);
    if (t < tStand) {
      M.sit(1.0, lerp(0.5, -0.15, prog(t, 70.25, 70.8)), t);
      M.setFace(t < 70.3 ? 'sad' : 'shock');
      M.root.position.x += Math.sin(t * 50) * 0.02;
    } else {
      const s = prog(t, tStand, tStand + 0.55, ease.inOut);
      M.root.rotation.y = lerp(L.rotOut, L.rotIn, s);
      M.root.position.addScaledVector(L.out, -0.9 * s);
      M.root.position.y = PLAZA_Y * s;
      M.idle(t);
      const fl = prog(t, 76.0, 77.9, ease.in);
      M.root.position.y += fl * 0.9;
      M.arms(-0.2 - 0.3 * fl, -0.2 - 0.9 * fl, -0.2 - 0.3 * fl, 0.2 + 0.9 * fl);
      M.headPivot.rotation.x = -0.1 - 0.15 * fl;
      M.setFace('shock', { wide: t > tWait });
    }
    // debris bouncing
    this.debris.mesh.visible = true;
    const dm = this.debris;
    for (let i = 0; i < dm.n; i++) {
      const p = dm.p[i];
      const a = p.hue * 6.283, r = 3 + p.s * 9;
      const hop = Math.abs(Math.sin(t * (5 + p.sp * 0.3) + i)) * (0.15 + 0.5 * p.s) * (0.4 + crack);
      dm.v.set(L.P.x - L.out.x * 5 + Math.cos(a) * r, 0.25 + hop, L.P.z - L.out.z * 5 + Math.sin(a) * r);
      dm.e.set(t * p.rot.x * 0.2, t * p.rot.y * 0.2, 0); dm.q.setFromEuler(dm.e);
      const sc = 0.5 + p.s * 0.7; dm.sc.set(sc, sc, sc);
      dm.m.compose(dm.v, dm.q, dm.sc); dm.mesh.setMatrixAt(i, dm.m);
    }
    dm.mesh.instanceMatrix.needsUpdate = true;
    // light streams from the crystal to Max
    const head = M.root.position.clone().add(V(0, 3.4, 0));
    const src = V(0, 5.5, 0);
    const sI = prog(t, 72.8, 74.5) * (1 + prog(t, 76, 78));
    this.streams.obj.visible = sI > 0;
    const R = rng(51); const sd = Array.from({ length: 220 }, () => [R(), R(), R(), R()]);
    const ctrl = src.clone().lerp(head, 0.5).add(V(0, 5, 0));
    this.streams.fill((i, o) => {
      const [a, b, c, d] = sd[i];
      const ph = (t * (0.45 + c * 0.35) + a) % 1;
      const off = V((b - 0.5) * 6, (c - 0.5) * 5, (d - 0.5) * 6).multiplyScalar(Math.sin(ph * Math.PI));
      const q = src.clone().multiplyScalar((1 - ph) * (1 - ph)).add(ctrl.clone().add(off).multiplyScalar(2 * ph * (1 - ph))).add(head.clone().multiplyScalar(ph * ph));
      o.x = q.x; o.y = q.y; o.z = q.z;
      const cc = hsl((a + t * 0.3) % 1, 1, 0.62); o.r = cc.r; o.g = cc.g; o.b = cc.b;
      o.a = Math.min(1, sI) * Math.sin(ph * Math.PI); o.size = 0.45 + d * 0.5; o.rot = t * 3;
    });
    // swirl around Max near the end
    const sw = prog(t, 75.8, 77.9);
    this.swirl.obj.visible = sw > 0;
    if (sw > 0) {
      const R2 = rng(52); const sd2 = Array.from({ length: 320 }, () => [R2(), R2(), R2(), R2()]);
      this.swirl.fill((i, o) => {
        const [a, b, c, d] = sd2[i];
        const ang = a * 6.283 + t * (3 + c * 3), rr = 1.6 + b * 2.5 * (1 - sw * 0.5);
        o.x = head.x + Math.cos(ang) * rr; o.z = head.z + Math.sin(ang) * rr; o.y = head.y - 3 + d * 6 + Math.sin(t * 2 + i) * 0.3;
        const cc = hsl((a + t * 0.6) % 1, 1, 0.62); o.r = cc.r; o.g = cc.g; o.b = cc.b;
        o.a = sw; o.size = 0.35 + d * 0.4; o.rot = t;
      });
    }
    this.rimLight.position.copy(head).add(L.out.clone().multiplyScalar(-4)); this.rimLight.color.copy(hsl((t * 0.5) % 1, 1, 0.6)); this.rimLight.intensity = 30 * (crack + sw * 2);
    // camera
    let fx = { bloom: 0.45 + crack * 0.25, vignette: 0.5 };
    const side = V(-L.out.z, 0, L.out.x);
    if (t < 71.55) {
      const k = prog(t, 70, 71.55);
      this.setCam(L.P.clone().addScaledVector(L.out, lerp(6.0, 5.4, k)).addScaledVector(side, -0.8).add(V(0, 3.4, 0)), L.P.clone().add(V(0, 3.3, 0)), 40, shake * 1.6, t, 1.3);
    } else if (t < tStand) {
      const k = prog(t, 71.55, tStand);
      const cp = L.out.clone().multiplyScalar(lerp(9.5, 8.2, k)).addScaledVector(V(-L.out.z, 0, L.out.x), 1.5); cp.y = 1.7;
      this.setCam(cp, V(0, lerp(5.5, 6.5, k), 0), 48, shake * 1.4, t, 1);
    } else if (t < 76.2) {
      const k = prog(t, tStand, 76.2);
      const inward = L.out.clone().multiplyScalar(-1);
      this.setCam(M.root.position.clone().addScaledVector(inward, lerp(7, 5.5, k)).addScaledVector(side, 1.4).add(V(0, 4.3, 0)), M.root.position.clone().add(V(0, 4.0, 0)), 42, shake, t, 1.25);
    } else {
      const k = prog(t, 76.2, 78, ease.in);
      const inward = L.out.clone().multiplyScalar(-1);
      this.setCam(M.root.position.clone().addScaledVector(inward, lerp(6.5, 3.4, k)).addScaledVector(side, 0.8).add(V(0, 4.6, 0)), M.root.position.clone().add(V(0, 4.5, 0)), 40, shake * 1.2, t, 1.2);
      fx.flash = prog(t, 77.55, 78, ease.in);
    }
    return fx;
  }

  // ============================================================ 78-86 RAINBOW
  sRainbow(t, lt) {
    const W = this.world, M = this.max, A = this.aM;
    const L = this.ledgeSpot();
    const T0 = 78.0;
    W.setLighting(t, 'dusk', null, 0, L.P, 24);
    W.crystal.update(t, { color: hsl((t * 0.5) % 1, 0.95, 0.6), glow: 1.8, dark: 0, crack: 1, beams: 0.6 });
    const base = L.P.clone().addScaledVector(L.out, -0.9); base.y = PLAZA_Y;
    const fl = 1.6 * prog(t, T0, T0 + 0.8, ease.out) + 0.25 * Math.sin(t * 2.2);
    this.place(M, base.clone().add(V(0, 0.9 + fl, 0)), L.rotIn);
    M.idle(t);
    const armsOut = prog(t, T0, T0 + 0.4, ease.outBack);
    M.arms(-0.3 * armsOut, -1.25 * armsOut, -0.3 * armsOut, 1.25 * armsOut);
    M.legL.rotation.x = 0.15 * Math.sin(t * 2); M.legR.rotation.x = -0.15 * Math.sin(t * 2);
    const tCrowd = 80.55, tHero = 82.5;
    M.setFace(t < tCrowd ? 'shock' : 'grin', { wide: true });
    if (t > tHero - 0.2 && t < tHero + 0.9) M.arms(-0.3, -1.25, -2.9 * prog(t, tHero - 0.2, tHero + 0.2, ease.outBack) - 0.3 + 0.3, 0.6);
    if (t >= tHero + 0.9) M.arms(-0.3, -1.25, -2.9, 0.6);
    const auraI = 1.25 + 0.15 * Math.sin(t * 6);
    A.update(t, auraI, 1.35 * prog(t, T0, T0 + 0.35, ease.outBack) + 0.01);
    const center = M.root.position.clone().add(V(0, 3.2, 0));
    // rings, pillar, glow, shockwaves, confetti
    this.rings.forEach((r, i) => {
      r.visible = true; r.position.copy(center).add(V(0, -1.6 + i * 1.8, 0));
      r.rotation.set(Math.PI / 2 + 0.35 * Math.sin(t * 1.3 + i * 2), 0.3 * Math.cos(t * 1.1 + i), t * (1.5 + i * 0.6));
      const s = prog(t, T0 + 0.1 * i, T0 + 0.5 + 0.1 * i, ease.outBack); r.scale.setScalar(Math.max(0.01, s));
      r.material.uniforms.uTime.value = t + i; r.material.uniforms.uA.value = 1.0;
    });
    this.pillar.group.visible = true; this.pillar.group.position.copy(base); this.pillar.set(t, hsl((t * 0.4) % 1, 0.8, 0.65), 0.55 * prog(t, T0, T0 + 0.6) * (0.8 + 0.2 * Math.sin(t * 8)));
    this.maxGlow.visible = true; this.maxGlow.position.copy(center).addScaledVector(L.out, 1.5); this.maxGlow.scale.setScalar(14 + 4 * Math.sin(t * 3));
    this.maxGlow.material.color.copy(hsl((t * 0.4) % 1, 1, 0.7)); this.maxGlow.material.opacity = 0.4;
    this.shock1.mesh.position.copy(base).add(V(0, 0.3, 0)); this.shock1.update(t, T0, 1.2, 32, true);
    this.shock2.mesh.position.copy(base).add(V(0, 0.35, 0)); this.shock2.update(t, T0 + 0.25, 1.4, 22, true);
    this.confetti.update(t, T0, center, 4.0);
    this.fill.position.copy(center).add(V(0, 2, 0)); this.fill.color.copy(hsl((t * 0.4 + 0.5) % 1, 1, 0.65)); this.fill.intensity = 70;
    // sparkle swirl
    this.swirl.obj.visible = true;
    const R = rng(61); const sd = Array.from({ length: 320 }, () => [R(), R(), R(), R()]);
    this.swirl.fill((i, o) => {
      const [a, b, c, d] = sd[i];
      const ph = (t * (0.35 + c * 0.3) + a) % 1;
      const ang = a * 6.283 + t * (2 + d * 2) + ph * 4, rr = 2 + b * 6 + ph * 3;
      o.x = center.x + Math.cos(ang) * rr; o.z = center.z + Math.sin(ang) * rr; o.y = base.y + ph * 14;
      const cc = hsl((a + t * 0.5) % 1, 1, 0.62); o.r = cc.r; o.g = cc.g; o.b = cc.b;
      o.a = Math.sin(ph * Math.PI) * 1.2; o.size = 0.35 + d * 0.5; o.rot = t * 2 + a;
    });
    // crowd (came back to see) with jaws dropped
    const inward = L.out.clone().multiplyScalar(-1), side = V(-L.out.z, 0, L.out.x);
    this.crowd.forEach((c, i) => {
      const j = i - 6.5;
      const p = base.clone().addScaledVector(inward, 14 + (i % 2) * 2.4 + Math.abs(j) * 0.3).addScaledVector(side, j * 1.8);
      p.y = PLAZA_Y;
      const back = prog(t, T0, T0 + 0.5, ease.out) * 1.2;
      p.addScaledVector(inward, back);
      this.place(c, p); this.face(c, center); c.idle(t + i);
      c.setFace('shock', { wide: true });
      c.arms(-0.9 - 0.2 * (i % 3), -0.3, -0.9 - 0.2 * ((i + 1) % 3), 0.3);
      c.headPivot.rotation.x = -0.2;
    });
    this.aC0.update(t, 0.5, 0.85); this.aC1.update(t, 0.5, 0.85); this.aC2.update(t, 0.5, 0.85);
    // camera
    let fx = { bloom: 0.7, vignette: 0.4, exposure: 1.0 };
    fx.flash = t < T0 + 0.6 ? 1 - prog(t, T0, T0 + 0.6, ease.out) : 0;
    if (t < T0 + 0.7) {
      const k = prog(t, T0, T0 + 0.7, ease.outExpo);
      this.setCam(base.clone().addScaledVector(inward, lerp(11.5, 9.5, k)).addScaledVector(side, lerp(2, 1, k)).add(V(0, lerp(6, 4.6, k), 0)), center.clone().add(V(0, 0.6, 0)), lerp(75, 42, k), 0.3 * (1 - k), t, 1);
    } else if (t < tCrowd) {
      const k = prog(t, T0 + 0.7, tCrowd, x => x);
      const a = lerp(-0.5, 1.4, k);
      const dir = inward.clone().applyAxisAngle(V(0, 1, 0), a);
      this.setCam(base.clone().addScaledVector(dir, 10.5).add(V(0, lerp(4.5, 3.2, k), 0)), center.clone().add(V(0, 0.8, 0)), 44, 0, t, 1);
    } else if (t < tHero) {
      const k = prog(t, tCrowd, tHero);
      const look = base.clone().addScaledVector(inward, 15).addScaledVector(side, lerp(-6, 6, k)); look.y = 4.2;
      this.setCam(base.clone().addScaledVector(inward, 2.0).add(V(0, 5.0, 0)), look, 48, 0, t, 1);
    } else {
      const k = prog(t, tHero, tHero + 0.4, ease.outExpo), k2 = prog(t, tHero + 0.4, 86);
      const dir = inward.clone().applyAxisAngle(V(0, 1, 0), lerp(-0.2, 0.35, k2));
      this.setCam(base.clone().addScaledVector(dir, lerp(11, 8.0, k) - k2 * 1.0).add(V(0, lerp(2.2, 2.6, k2), 0)), center.clone().add(V(0, 1.2, 0)), 44, 0, t, 1);
    }
    return fx;
  }

  // ============================================================ 86-90 END
  sEnd(t, lt) {
    const W = this.world, M = this.max, A = this.aM;
    const L = this.ledgeSpot();
    W.setLighting(t, 'dusk', 'night', prog(t, 86, 89), L.P, 30);
    W.crystal.update(t, { color: hsl((t * 0.5) % 1, 0.95, 0.6), glow: 1.2, crack: 1, beams: 0.15 });
    const base = L.P.clone().addScaledVector(L.out, -0.9); base.y = PLAZA_Y;
    const inward = L.out.clone().multiplyScalar(-1), side = V(-L.out.z, 0, L.out.x);
    const path = (tt) => {
      const k = clamp((tt - 86) / 4);
      const h = 2.5 + 22 * ease.in(k) + 3 * k;
      const a = k * 2.2;
      return base.clone().add(V(0, h, 0)).addScaledVector(side, Math.sin(a) * 2.5 * k).addScaledVector(inward, (1 - Math.cos(a)) * 2.0 * k);
    };
    const p = path(t);
    this.place(M, p.clone().add(V(0, -2.5, 0)), L.rotIn + 0.3 * Math.sin(t));
    M.idle(t); M.arms(-0.2, -1.0, -0.2, 1.0); M.legL.rotation.x = 0.2; M.legR.rotation.x = -0.1;
    M.setFace(t > 88.2 ? 'joy' : 'grin');
    A.update(t, 1.2, 1.25); A.ground.visible = false;
    this.rTrail.update(t, (tt) => path(tt).add(V(0, 0.3, 0)), 2.6, this.cam, 1, 85.4);
    this.rTrail.mesh.visible = true;
    this.maxGlow.visible = true; this.maxGlow.position.copy(p).add(V(0, 1, 0)); this.maxGlow.scale.setScalar(16);
    this.maxGlow.material.color.copy(hsl((t * 0.4) % 1, 1, 0.7)); this.maxGlow.material.opacity = 0.6;
    this.fill.position.copy(p).add(V(0, 3, 0)); this.fill.color.copy(hsl((t * 0.4 + 0.5) % 1, 1, 0.65)); this.fill.intensity = 60;
    this.bokeh(t, p.clone().add(V(0, 1, 0)), 9);
    // camera follows him up, looking up from below
    const k = prog(t, 86, 90);
    const camP = base.clone().addScaledVector(inward, lerp(8.5, 9.5, k)).addScaledVector(side, lerp(-4.5, -2.5, k)).add(V(0, lerp(3.5, p.y - 5, ease.inOut(k)), 0));
    this.setCam(camP, p.clone().add(V(0, -0.3, 0)), 44);
    return { bloom: 0.6, vignette: 0.45, endcard: 88.05 };
  }
}
