// The town: sky, lighting presets, baseplate ground, roads, houses, trees, plaza and the Awakening crystal.
import * as THREE from 'three';
import { rng, baseplateTex, tileTex, crackTex, lerp, clamp } from './lib.js';
import { plastic, rbox, mesh } from './character.js';
import { glowSprite, Beam } from './fx.js';

// ------------------------------------------------------------------ sky + lighting presets
export const PRESETS = {
  day:       { top: '#3d8bff', hor: '#bfe6ff', bot: '#9fd3ff', sun: '#fff4dc', sunI: 2.6, hemiS: '#d6ecff', hemiG: '#6aa35a', hemiI: 1.15, fog: '#c9e9ff', fogN: 90, fogF: 330, sunDir: [0.55, 0.75, 0.35], stars: 0, win: 0, exp: 1.0, sunDisc: 0.4 },
  dark:      { top: '#07040f', hor: '#2a1440', bot: '#140a22', sun: '#9a8cff', sunI: 0.55, hemiS: '#4a3a7a', hemiG: '#1a1426', hemiI: 0.55, fog: '#1d1030', fogN: 40, fogF: 200, sunDir: [-0.3, 0.8, 0.4], stars: 0.3, win: 0.6, exp: 1.0, sunDisc: 0 },
  afternoon: { top: '#4a8fe8', hor: '#ffe2b8', bot: '#ffd29a', sun: '#ffe1b0', sunI: 2.4, hemiS: '#ffe7c7', hemiG: '#6f9a55', hemiI: 1.0, fog: '#f3dcc0', fogN: 90, fogF: 320, sunDir: [-0.6, 0.55, 0.45], stars: 0, win: 0.05, exp: 1.0, sunDisc: 0.5 },
  sunset:    { top: '#3b3f8f', hor: '#ff8a4c', bot: '#ff6e5a', sun: '#ff9a55', sunI: 2.3, hemiS: '#ffb38a', hemiG: '#4a3b55', hemiI: 0.85, fog: '#ff9e7a', fogN: 70, fogF: 280, sunDir: [-0.85, 0.16, -0.3], stars: 0.05, win: 0.5, exp: 1.0, sunDisc: 1.0 },
  dusk:      { top: '#120d35', hor: '#6a3a8a', bot: '#2a1a40', sun: '#b28cff', sunI: 0.8, hemiS: '#6a5aa8', hemiG: '#22183a', hemiI: 0.75, fog: '#3a2458', fogN: 50, fogF: 230, sunDir: [-0.7, 0.35, -0.3], stars: 0.8, win: 0.9, exp: 1.0, sunDisc: 0.0 },
  night:     { top: '#0a0b2a', hor: '#3b2d7a', bot: '#1a1238', sun: '#9fb0ff', sunI: 0.7, hemiS: '#5a62b8', hemiG: '#1a1a3a', hemiI: 0.8, fog: '#2c2463', fogN: 60, fogF: 260, sunDir: [0.3, 0.6, 0.5], stars: 1, win: 1, exp: 1.0, sunDisc: 0 },
};

function skyMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: {
      top: { value: new THREE.Color() }, hor: { value: new THREE.Color() }, bot: { value: new THREE.Color() },
      sunDir: { value: new THREE.Vector3(0, 1, 0) }, sunCol: { value: new THREE.Color() }, sunDisc: { value: 0 },
      stars: { value: 0 }, uTime: { value: 0 }, flash: { value: 0 },
    },
    vertexShader: `varying vec3 vD; void main(){ vD = normalize(position); vec4 p = projectionMatrix*modelViewMatrix*vec4(position,1.0); gl_Position = p.xyww; }`,
    fragmentShader: `uniform vec3 top, hor, bot, sunCol; uniform vec3 sunDir; uniform float sunDisc, stars, uTime, flash; varying vec3 vD;
      float h(vec3 p){ return fract(sin(dot(p, vec3(12.9898,78.233,37.719)))*43758.5453); }
      void main(){ vec3 d = normalize(vD); float y = d.y;
        vec3 c = y > 0.0 ? mix(hor, top, pow(clamp(y,0.0,1.0), 0.55)) : mix(hor, bot, clamp(-y*4.0,0.0,1.0));
        float s = max(0.0, dot(d, normalize(sunDir)));
        c += sunCol * (pow(s, 600.0)*3.0 + pow(s, 12.0)*0.35) * sunDisc;
        if (stars > 0.0 && y > 0.05) { vec3 g = floor(d*220.0); float r = h(g); float tw = 0.6+0.4*sin(uTime*3.0 + r*40.0);
          c += vec3(step(0.9965, r) * stars * tw * smoothstep(0.05, 0.3, y)); }
        c += vec3(flash);
        gl_FragColor = vec4(c, 1.0);
        #include <colorspace_fragment>
      }`,
    side: THREE.BackSide, depthWrite: false, fog: false,
  });
}

// ------------------------------------------------------------------ houses etc.
const WALLS = ['#ffd166', '#ef476f', '#06d6a0', '#4cc9f0', '#f78c6b', '#c77dff', '#fdfdfd', '#ff9f1c', '#90e0ef', '#ffadad', '#b5e48c'];
const ROOFS = ['#d62828', '#3a86ff', '#2b2d42', '#8338ec', '#e85d04', '#2a9d8f', '#6a4c93', '#c1121f'];

function roofGeo(w, d, h) {
  const s = new THREE.Shape();
  s.moveTo(-w / 2 - 0.5, 0); s.lineTo(w / 2 + 0.5, 0); s.lineTo(0, h); s.lineTo(-w / 2 - 0.5, 0);
  const g = new THREE.ExtrudeGeometry(s, { depth: d + 1, bevelEnabled: false });
  g.translate(0, 0, -(d + 1) / 2);
  return g;
}

export class World {
  constructor(scene) {
    this.scene = scene;
    this.sky = new THREE.Mesh(new THREE.SphereGeometry(800, 32, 16), skyMaterial());
    this.sky.frustumCulled = false; this.sky.renderOrder = -10;
    scene.add(this.sky);
    scene.fog = new THREE.Fog(0xffffff, 80, 300);
    this.sun = new THREE.DirectionalLight(0xffffff, 2.5);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    this.sun.shadow.bias = -0.0004; this.sun.shadow.normalBias = 0.04;
    this.sun.shadow.radius = 3;
    scene.add(this.sun); scene.add(this.sun.target);
    this.hemi = new THREE.HemisphereLight(0xffffff, 0x446644, 1); scene.add(this.hemi);
    this.windowMats = [];
    this.buildGround();
    this.buildPlaza();
    this.buildTown();
    this.buildClouds();
    this.crystal = new Crystal(); scene.add(this.crystal.group);
  }

  buildGround() {
    const tex = baseplateTex(); tex.repeat.set(160, 160);
    const g = new THREE.Mesh(new THREE.PlaneGeometry(640, 640), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.85 }));
    g.rotation.x = -Math.PI / 2; g.receiveShadow = true; this.scene.add(g);
    const asphalt = new THREE.MeshStandardMaterial({ color: '#4a4f5a', roughness: 0.9 });
    const ring = new THREE.Mesh(new THREE.RingGeometry(15.5, 21, 64), asphalt);
    ring.rotation.x = -Math.PI / 2; ring.position.y = 0.02; ring.receiveShadow = true; this.scene.add(ring);
    const dash = plastic('#ffe08a', { roughness: 0.8 });
    for (let k = 0; k < 40; k++) {
      const a = k / 40 * Math.PI * 2;
      const m = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.04, 0.3), dash);
      m.position.set(Math.cos(a) * 18.25, 0.04, Math.sin(a) * 18.25); m.rotation.y = -a + Math.PI / 2; m.receiveShadow = true;
      this.scene.add(m);
    }
    for (let k = 0; k < 4; k++) {
      const a = k * Math.PI / 2;
      const road = new THREE.Mesh(new THREE.PlaneGeometry(6, 140), asphalt);
      road.rotation.x = -Math.PI / 2; road.rotation.z = a;
      road.position.set(Math.cos(a) * 90, 0.021, Math.sin(a) * 90);
      road.receiveShadow = true; this.scene.add(road);
      for (let j = 0; j < 14; j++) {
        const r = 23 + j * 5;
        const m = new THREE.Mesh(new THREE.BoxGeometry(2, 0.04, 0.3), dash);
        m.position.set(Math.cos(a) * r, 0.04, Math.sin(a) * r); m.rotation.y = -a; m.receiveShadow = true; this.scene.add(m);
      }
    }
  }

  buildPlaza() {
    const tex = tileTex(); tex.repeat.set(7, 7);
    const p = new THREE.Mesh(new THREE.CylinderGeometry(15.5, 15.5, 0.24, 48), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.75 }));
    p.position.y = 0.12; p.receiveShadow = true; this.scene.add(p);
    // low ledge around the plaza (gaps at the 4 roads)
    const stone = plastic('#d8d2c4', { roughness: 0.8 });
    const n = 32;
    this.ledges = [];
    for (let k = 0; k < n; k++) {
      const a = (k + 0.5) / n * Math.PI * 2;
      const deg = (a * 180 / Math.PI) % 90;
      if (deg < 9 || deg > 81) continue;
      const m = mesh(rbox(3.0, 1.0, 1.3, 0.12), stone, Math.cos(a) * 15.0, 0.5, Math.sin(a) * 15.0, this.scene);
      m.rotation.y = -a + Math.PI / 2;
      this.ledges.push(m);
    }
    // pedestal
    const ped = plastic('#9aa3b5', { roughness: 0.6 }), ped2 = plastic('#c9cfdb', { roughness: 0.6 });
    mesh(new THREE.CylinderGeometry(4.6, 4.8, 0.45, 8), ped, 0, 0.45, 0, this.scene);
    mesh(new THREE.CylinderGeometry(3.7, 3.8, 0.45, 8), ped2, 0, 0.9, 0, this.scene);
    // lamp posts around the plaza
    const pole = plastic('#2d3142'), bulb = new THREE.MeshStandardMaterial({ color: '#fff3c4', emissive: '#ffd27a', emissiveIntensity: 0.3 });
    this.windowMats.push(bulb);
    for (let k = 0; k < 8; k++) {
      if (k <= 2) continue;      // keep the south side (where most shots look) clear
      const a = (k + 0.5) / 8 * Math.PI * 2;
      const x = Math.cos(a) * 13.3, z = Math.sin(a) * 13.3;
      mesh(new THREE.BoxGeometry(0.35, 6, 0.35), pole, x, 3.2, z, this.scene);
      mesh(rbox(0.9, 0.9, 0.9, 0.15), bulb, x, 6.4, z, this.scene);
    }
    // benches
    const wood = plastic('#a0522d');
    for (const a of [Math.PI * 0.62, Math.PI * 1.38]) {
      const b = new THREE.Group(); b.position.set(Math.cos(a) * 11, 0, Math.sin(a) * 11); b.rotation.y = -a - Math.PI / 2;
      mesh(rbox(4, 0.3, 1.2, 0.08), wood, 0, 1.0, 0, b); mesh(rbox(4, 1, 0.25, 0.08), wood, 0, 1.6, -0.5, b);
      for (const s of [-1.6, 1.6]) mesh(new THREE.BoxGeometry(0.3, 1.0, 1), pole, s, 0.5, 0, b);
      this.scene.add(b);
    }
  }

  house(x, z, rotY, R) {
    const g = new THREE.Group(); g.position.set(x, 0, z); g.rotation.y = rotY;
    const w = 8 + Math.floor(R() * 3), d = 7 + Math.floor(R() * 3), h = 5.5 + Math.floor(R() * 3);
    const wall = plastic(WALLS[Math.floor(R() * WALLS.length)], { roughness: 0.55 });
    const roof = plastic(ROOFS[Math.floor(R() * ROOFS.length)], { roughness: 0.5 });
    mesh(rbox(w, h, d, 0.15), wall, 0, h / 2, 0, g);
    const r = new THREE.Mesh(roofGeo(w, d, 3 + R() * 1.5), roof); r.position.y = h; r.castShadow = r.receiveShadow = true; g.add(r);
    if (R() < 0.6) mesh(new THREE.BoxGeometry(1, 3, 1), plastic('#7f4f24'), w * 0.25, h + 2.0, -d * 0.15, g);
    mesh(rbox(1.8, 3.2, 0.3, 0.08), plastic('#6b3e26'), 0, 1.6, d / 2 + 0.05, g);
    mesh(new THREE.BoxGeometry(0.25, 0.25, 0.2), plastic('#ffd166', { metalness: 0.6, roughness: 0.3 }), 0.55, 1.6, d / 2 + 0.25, g);
    const win = new THREE.MeshStandardMaterial({ color: '#bde0fe', emissive: '#ffcf6e', emissiveIntensity: 0, roughness: 0.15, metalness: 0.1 });
    this.windowMats.push(win);
    const frame = plastic('#ffffff');
    for (const s of [-1, 1]) {
      mesh(new THREE.BoxGeometry(1.9, 1.9, 0.2), frame, s * w * 0.3, h * 0.55, d / 2 + 0.02, g);
      mesh(new THREE.BoxGeometry(1.5, 1.5, 0.24), win, s * w * 0.3, h * 0.55, d / 2 + 0.03, g);
    }
    for (const s of [-1, 1]) {   // side windows
      const m = mesh(new THREE.BoxGeometry(0.24, 1.5, 1.5), win, s * (w / 2 + 0.03), h * 0.55, 0, g);
      m.castShadow = false;
    }
    this.scene.add(g);
    return g;
  }

  tree(x, z, R, s = 1) {
    const g = new THREE.Group(); g.position.set(x, 0, z); g.scale.setScalar(s); g.rotation.y = R() * 6;
    mesh(rbox(0.9, 3.2, 0.9, 0.1), plastic('#8b5a2b'), 0, 1.6, 0, g);
    const leaf = plastic(['#2fbf71', '#38b000', '#70e000', '#2a9d8f'][Math.floor(R() * 4)], { roughness: 0.65 });
    mesh(rbox(3.6, 2.6, 3.6, 0.3), leaf, 0, 4.2, 0, g);
    mesh(rbox(2.4, 1.8, 2.4, 0.3), leaf, 0.2, 5.9, -0.1, g);
    this.scene.add(g);
    return g;
  }

  buildTown() {
    const R = rng(42);
    this.houses = [];
    for (let k = 0; k < 12; k++) {
      const q = Math.floor(k / 3), j = k % 3;
      const a = q * Math.PI / 2 + (j + 1) * Math.PI / 8;
      this.houses.push(this.house(Math.cos(a) * 31, Math.sin(a) * 31, -a - Math.PI / 2, R));
    }
    for (let k = 0; k < 20; k++) {
      const a = (k + 0.5) / 20 * Math.PI * 2;
      const deg = (a * 180 / Math.PI) % 90;
      if (deg < 8 || deg > 82) continue;
      this.houses.push(this.house(Math.cos(a) * 52, Math.sin(a) * 52, -a - Math.PI / 2, R));
    }
    for (let k = 0; k < 26; k++) {
      const a = (k + 0.5) / 26 * Math.PI * 2 + R() * 0.1;
      const deg = (a * 180 / Math.PI) % 90;
      if (deg < 6 || deg > 84) continue;
      const r = k % 2 ? 41 : 24.5;
      this.tree(Math.cos(a) * r, Math.sin(a) * r, R, 0.8 + R() * 0.4);
    }
    for (let k = 0; k < 30; k++) {   // far trees
      const a = R() * Math.PI * 2, r = 70 + R() * 60;
      const deg = (a * 180 / Math.PI) % 90;
      if (deg < 6 || deg > 84) continue;
      this.tree(Math.cos(a) * r, Math.sin(a) * r, R, 1 + R() * 0.6);
    }
  }

  buildClouds() {
    const R = rng(77);
    this.clouds = [];
    const m = new THREE.MeshStandardMaterial({ color: '#ffffff', roughness: 1, emissive: '#ffffff', emissiveIntensity: 0.25, fog: false });
    this.cloudMat = m;
    for (let k = 0; k < 14; k++) {
      const g = new THREE.Group();
      const n = 3 + Math.floor(R() * 3);
      for (let i = 0; i < n; i++) {
        const b = new THREE.Mesh(rbox(6 + R() * 6, 3 + R() * 2, 5 + R() * 4, 1.0), m);
        b.position.set((i - n / 2) * 4.5, R() * 1.5, R() * 3 - 1.5); g.add(b);
      }
      const a = R() * Math.PI * 2, r = 60 + R() * 120;
      g.userData = { a, r, y: 45 + R() * 30, sp: 0.004 + R() * 0.004, dynamic: true };
      this.scene.add(g); this.clouds.push(g);
    }
  }

  // blend two presets, k = 0..1
  setLighting(t, a, b = null, k = 0, focus = new THREE.Vector3(), extent = 30) {
    const A = PRESETS[a], B = PRESETS[b || a];
    const C = (x, y) => new THREE.Color(x).lerp(new THREE.Color(y), k);
    const L = (x, y) => lerp(x, y, k);
    const u = this.sky.material.uniforms;
    u.top.value.copy(C(A.top, B.top)); u.hor.value.copy(C(A.hor, B.hor)); u.bot.value.copy(C(A.bot, B.bot));
    u.sunCol.value.copy(C(A.sun, B.sun)); u.sunDisc.value = L(A.sunDisc, B.sunDisc);
    u.stars.value = L(A.stars, B.stars); u.uTime.value = t;
    const sd = new THREE.Vector3(...A.sunDir).lerp(new THREE.Vector3(...B.sunDir), k).normalize();
    u.sunDir.value.copy(sd);
    this.sun.color.copy(C(A.sun, B.sun)); this.sun.intensity = L(A.sunI, B.sunI);
    this.sun.position.copy(focus).addScaledVector(sd, 80);
    this.sun.target.position.copy(focus);
    const sc = this.sun.shadow.camera;
    sc.left = -extent; sc.right = extent; sc.top = extent; sc.bottom = -extent; sc.near = 1; sc.far = 220;
    sc.updateProjectionMatrix();
    this.hemi.color.copy(C(A.hemiS, B.hemiS)); this.hemi.groundColor.copy(C(A.hemiG, B.hemiG)); this.hemi.intensity = L(A.hemiI, B.hemiI);
    this.scene.fog.color.copy(C(A.fog, B.fog)); this.scene.fog.near = L(A.fogN, B.fogN); this.scene.fog.far = L(A.fogF, B.fogF);
    const win = L(A.win, B.win);
    for (const m of this.windowMats) m.emissiveIntensity = win * 1.2;
    this.cloudMat.color.copy(C(A.hor, B.hor)).lerp(new THREE.Color('#ffffff'), 0.6);
    this.cloudMat.emissive.copy(this.cloudMat.color); this.cloudMat.emissiveIntensity = 0.2;
    for (const c of this.clouds) {
      const d = c.userData, a = d.a + t * d.sp;
      c.position.set(Math.cos(a) * d.r, d.y, Math.sin(a) * d.r); c.rotation.y = -a;
    }
  }
}

// ------------------------------------------------------------------ the Awakening crystal
function crackMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { uMap: { value: crackTex() }, uP: { value: 0 }, uTime: { value: 0 }, uA: { value: 1 } },
    vertexShader: `varying vec2 vUv; varying float vY; void main(){ vUv=uv; vY=position.y; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);} `,
    fragmentShader: `uniform sampler2D uMap; uniform float uP, uTime, uA; varying vec2 vUv; varying float vY;
      vec3 hsv2rgb(vec3 c){ vec3 p=abs(fract(c.xxx+vec3(0.,2./3.,1./3.))*6.-3.); return c.z*mix(vec3(1.),clamp(p-1.,0.,1.),c.y); }
      void main(){ vec4 t = texture2D(uMap, vUv*vec2(2.0,1.0)); float m = t.a * step(t.r, uP) ;
        vec3 col = mix(vec3(1.0), hsv2rgb(vec3(fract(vUv.x*2.0 + vY*0.15 - uTime*0.5), 0.8, 1.0)), 0.75);
        gl_FragColor = vec4(col*m*2.2*uA, 1.0); }`,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.FrontSide,
    polygonOffset: true, polygonOffsetFactor: -4,
  });
}

export class Crystal {
  constructor() {
    this.group = new THREE.Group(); this.group.position.set(0, 1.12, 0);
    this.body = new THREE.Group(); this.group.add(this.body);
    this.mat = new THREE.MeshStandardMaterial({ color: '#bff3ff', emissive: '#6fe7ff', emissiveIntensity: 0.9, roughness: 0.08, metalness: 0.05, flatShading: true, transparent: true, opacity: 0.88 });
    this.coreMat = new THREE.MeshBasicMaterial({ color: '#c9f6ff', transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending, depthWrite: false, toneMapped: false });
    const prism = (r, h, tip) => {
      const g = new THREE.Group();
      const a = new THREE.Mesh(new THREE.CylinderGeometry(r, r * 1.08, h, 6), this.mat); a.position.y = h / 2;
      const b = new THREE.Mesh(new THREE.ConeGeometry(r, tip, 6), this.mat); b.position.y = h + tip / 2;
      for (const m of [a, b]) { m.castShadow = true; g.add(m); }
      return g;
    };
    this.main = prism(1.7, 6.2, 2.8); this.body.add(this.main);
    const core = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 0.8, 6, 6), this.coreMat); core.position.y = 3.6; this.body.add(core);
    this.core = core;
    const R = rng(4);
    this.sides = [];
    for (let k = 0; k < 6; k++) {
      const a = k / 6 * Math.PI * 2 + 0.3;
      const s = prism(0.6 + R() * 0.3, 1.6 + R() * 1.6, 1.0 + R() * 0.6);
      s.position.set(Math.cos(a) * 1.9, 0, Math.sin(a) * 1.9);
      s.rotation.set(Math.sin(a) * 0.45, 0, -Math.cos(a) * 0.45);
      this.body.add(s); this.sides.push(s);
    }
    // cracks (shell around the main prism)
    this.crackMat = crackMaterial();
    const cg = new THREE.CylinderGeometry(1.74, 1.86, 6.24, 6, 1, true); cg.translate(0, 3.1, 0);
    this.cracks = new THREE.Mesh(cg, this.crackMat); this.body.add(this.cracks);
    const cg2 = new THREE.ConeGeometry(1.74, 2.84, 6, 1, true); cg2.translate(0, 6.2 + 1.42, 0);
    this.cracks2 = new THREE.Mesh(cg2, this.crackMat); this.body.add(this.cracks2);
    this.glow = glowSprite(new THREE.Color('#7fe9ff'), 16, 0.6); this.glow.position.y = 4.2; this.group.add(this.glow);
    this.light = new THREE.PointLight('#7fe9ff', 40, 30, 1.5); this.light.position.y = 4.5; this.group.add(this.light);
    this.beams = [];
    const BR = rng(17);
    for (let k = 0; k < 9; k++) {
      const b = new Beam(14 + BR() * 10, 1.0 + BR() * 0.8);
      b.group.position.set((BR() - 0.5) * 2, 1.5 + BR() * 6, (BR() - 0.5) * 2);
      b.group.rotation.set((BR() - 0.5) * 2.6, BR() * 6.28, (BR() - 0.5) * 2.6);
      b.hue = k / 9; this.body.add(b.group); this.beams.push(b);
    }
  }

  // color: THREE.Color, glow 0..2, dark 0..1, crack 0..1, beams 0..1
  update(t, { color = new THREE.Color('#7fe9ff'), glow = 1, dark = 0, crack = 0, beams = 0, shake = 0, visible = true } = {}) {
    this.group.visible = visible;
    if (!visible) { this.light.intensity = 0; return; }
    const grey = new THREE.Color('#58606e');
    this.mat.color.copy(new THREE.Color('#e9fbff').lerp(color, 0.35).lerp(grey, dark));
    this.mat.emissive.copy(color.clone().lerp(new THREE.Color('#000000'), dark));
    this.mat.emissiveIntensity = 0.85 * glow * (1 - dark) + 0.02;
    this.mat.opacity = lerp(0.88, 0.97, dark);
    this.coreMat.color.copy(color.clone().lerp(new THREE.Color('#ffffff'), 0.4));
    this.coreMat.opacity = 0.75 * glow * (1 - dark);
    this.core.visible = this.coreMat.opacity > 0.01;
    this.glow.material.color.copy(color); this.glow.material.opacity = clamp(0.32 * glow * (1 - dark), 0, 0.9);
    this.glow.scale.setScalar(8 + glow * 2.5);
    this.light.color.copy(color); this.light.intensity = 45 * glow * (1 - dark);
    this.crackMat.uniforms.uP.value = crack; this.crackMat.uniforms.uTime.value = t;
    this.cracks.visible = this.cracks2.visible = crack > 0.001;
    this.body.position.set(shake * Math.sin(t * 61), 0, shake * Math.cos(t * 53));
    for (const b of this.beams) {
      b.set(t, new THREE.Color().setHSL((b.hue + t * 0.2) % 1, 0.9, 0.6), beams * (0.55 + 0.45 * Math.sin(t * 9 + b.hue * 20)));
      b.group.rotation.y += 0;  // static aim, shimmer comes from shader
    }
  }
}
