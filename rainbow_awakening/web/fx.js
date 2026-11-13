// Visual effects: auras, particles, trails, glows, beams, shockwaves, confetti.
// Everything is a pure function of time t (set via .update(t, ...)) so any frame renders independently.
import * as THREE from 'three';
import { rng, glowTex, sparkleTex, smokeTex, ringTex, clamp } from './lib.js';

const NOISE = /* glsl */`
float h31(vec3 p){ p = fract(p*0.3183099+.1); p *= 17.0; return fract(p.x*p.y*p.z*(p.x+p.y+p.z)); }
float vnoise(vec3 x){ vec3 i=floor(x), f=fract(x); f=f*f*(3.0-2.0*f);
  return mix(mix(mix(h31(i),h31(i+vec3(1,0,0)),f.x), mix(h31(i+vec3(0,1,0)),h31(i+vec3(1,1,0)),f.x),f.y),
             mix(mix(h31(i+vec3(0,0,1)),h31(i+vec3(1,0,1)),f.x), mix(h31(i+vec3(0,1,1)),h31(i+vec3(1,1,1)),f.x),f.y),f.z); }
float fbm(vec3 p){ return 0.55*vnoise(p)+0.3*vnoise(p*2.03+7.1)+0.15*vnoise(p*4.1+3.3); }
vec3 hsv2rgb(vec3 c){ vec3 p=abs(fract(c.xxx+vec3(0.,2./3.,1./3.))*6.-3.); return c.z*mix(vec3(1.),clamp(p-1.,0.,1.),c.y); }
`;

// ------------------------------------------------------------------ aura shell
// mode 0 = solid color (additive), 1 = rainbow (additive), 2 = dark smoke (normal blend)
function auraMaterial(mode) {
  return new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uColor: { value: new THREE.Color(1, 1, 1) }, uI: { value: 1 }, uH: { value: 7.5 }, uSpeed: { value: 3 } },
    vertexShader: /* glsl */`
      varying vec3 vN; varying vec3 vV; varying vec3 vP;
      void main(){ vP = position; vec4 wp = modelMatrix*vec4(position,1.0);
        vN = normalize(mat3(modelMatrix)*normal); vV = normalize(cameraPosition-wp.xyz);
        gl_Position = projectionMatrix*viewMatrix*wp; }`,
    fragmentShader: NOISE + /* glsl */`
      uniform float uTime, uI, uH, uSpeed; uniform vec3 uColor;
      varying vec3 vN; varying vec3 vV; varying vec3 vP;
      void main(){
        float h = clamp(vP.y/uH, 0.0, 1.0);
        float ang = atan(vP.z, vP.x);
        float fr = 1.0 - abs(dot(normalize(vN), normalize(vV)));
        float n = fbm(vec3(cos(ang)*2.2+3.0, vP.y*0.9 - uTime*uSpeed, sin(ang)*2.2 + uTime*0.4));
        float n2 = fbm(vec3(cos(ang)*5.0, vP.y*2.2 - uTime*uSpeed*1.7, sin(ang)*5.0));
        float flame = smoothstep(0.12, 0.8, (1.0-h)*1.15 + (n-0.5)*1.9 + (n2-0.5)*0.9);
        float a = flame * (0.07 + pow(fr,1.8)*0.75) * smoothstep(0.0,0.08,h) * uI;
        #if MODE == 1
          vec3 col = hsv2rgb(vec3(fract(h*0.9 - uTime*0.45 + ang/6.2831), 0.85, 1.0));
          gl_FragColor = vec4(col*a*1.1, 1.0);
        #elif MODE == 2
          float edge = pow(fr, 3.0);
          vec3 col = mix(vec3(0.02,0.0,0.05), vec3(0.85,0.8,1.0), edge*0.9);
          gl_FragColor = vec4(col, clamp(a*1.25,0.0,0.92));
        #else
          vec3 col = mix(uColor, vec3(1.0), pow(1.0-h,3.0)*0.35);
          gl_FragColor = vec4(col*a*0.95, 1.0);
        #endif
      }`,
    defines: { MODE: mode },
    transparent: true, depthWrite: false, side: THREE.DoubleSide,
    blending: mode === 2 ? THREE.NormalBlending : THREE.AdditiveBlending,
  });
}

const auraGeo = (() => {
  let g; return () => g || (g = new THREE.LatheGeometry(
    [[1.55, 0], [2.0, 0.7], [2.2, 2.2], [2.05, 4.2], [1.75, 5.6], [1.15, 6.8], [0.25, 7.6]].map(([x, y]) => new THREE.Vector2(x, y)), 28));
})();

// soft round particles with per-point color/size/alpha, additive (or normal for smoke)
function pointsMaterial(tex, additive = true) {
  return new THREE.ShaderMaterial({
    uniforms: { uTex: { value: tex }, uScale: { value: 600 } },
    vertexShader: /* glsl */`
      attribute float size; attribute vec4 rgba; attribute float rot; varying vec4 vC; varying float vR;
      uniform float uScale;
      void main(){ vC = rgba; vR = rot; vec4 mv = modelViewMatrix*vec4(position,1.0);
        gl_PointSize = clamp(size*uScale/max(0.1,-mv.z), 0.0, 220.0); gl_Position = projectionMatrix*mv; }`,
    fragmentShader: /* glsl */`
      uniform sampler2D uTex; varying vec4 vC; varying float vR;
      void main(){ vec2 p = gl_PointCoord-0.5; float c=cos(vR), s=sin(vR); p = vec2(c*p.x-s*p.y, s*p.x+c*p.y)+0.5;
        vec4 t = texture2D(uTex, p); ${additive ? 'gl_FragColor = vec4(vC.rgb*t.a*vC.a, 1.0);' : 'gl_FragColor = vec4(vC.rgb, t.a*vC.a);'} }`,
    transparent: true, depthWrite: false, blending: additive ? THREE.AdditiveBlending : THREE.NormalBlending,
  });
}

export class Particles {
  // update callback fills (i, out) where out = {x,y,z,r,g,b,a,size,rot}; return false to hide
  constructor(n, tex = glowTex(), additive = true) {
    this.n = n;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    g.setAttribute('rgba', new THREE.BufferAttribute(new Float32Array(n * 4), 4));
    g.setAttribute('size', new THREE.BufferAttribute(new Float32Array(n), 1));
    g.setAttribute('rot', new THREE.BufferAttribute(new Float32Array(n), 1));
    this.mat = pointsMaterial(tex, additive);
    this.obj = new THREE.Points(g, this.mat);
    this.obj.frustumCulled = false;
    this.geo = g;
    this.o = { x: 0, y: 0, z: 0, r: 1, g: 1, b: 1, a: 1, size: 1, rot: 0 };
  }
  fill(fn) {
    const P = this.geo.attributes.position.array, C = this.geo.attributes.rgba.array,
      S = this.geo.attributes.size.array, R = this.geo.attributes.rot.array, o = this.o;
    for (let i = 0; i < this.n; i++) {
      o.a = 1; o.size = 1; o.rot = 0;
      const vis = fn(i, o);
      P[i * 3] = o.x; P[i * 3 + 1] = o.y; P[i * 3 + 2] = o.z;
      C[i * 4] = o.r; C[i * 4 + 1] = o.g; C[i * 4 + 2] = o.b; C[i * 4 + 3] = vis === false ? 0 : clamp(o.a, 0, 4);
      S[i] = vis === false ? 0 : o.size; R[i] = o.rot;
    }
    for (const k of ['position', 'rgba', 'size', 'rot']) this.geo.attributes[k].needsUpdate = true;
  }
}

export function glowSprite(color, size, opacity = 1) {
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex(), color, blending: THREE.AdditiveBlending, depthWrite: false, transparent: true, opacity }));
  s.scale.setScalar(size);
  return s;
}

// ------------------------------------------------------------------ Aura
const COLORS = {
  purple: new THREE.Color('#b44dff'), yellow: new THREE.Color('#ffe13a'), gold: new THREE.Color('#ffb81c'),
  black: new THREE.Color('#ffffff'), rainbow: new THREE.Color('#ffffff'),
};
export class Aura {
  constructor(kind, opts = {}) {
    this.kind = kind;
    this.group = new THREE.Group();
    const mode = kind === 'rainbow' ? 1 : kind === 'black' ? 2 : 0;
    this.color = COLORS[kind].clone();
    this.shells = [];
    for (const [s, sp, iMul] of [[1.0, 3.0, 1.0], [1.18, 2.1, 0.28]]) {
      const m = auraMaterial(mode);
      m.uniforms.uColor.value = this.color; m.uniforms.uSpeed.value = sp;
      const mesh = new THREE.Mesh(auraGeo(), m);
      mesh.scale.set(s, s * (kind === 'black' ? 1.05 : 1), s);
      mesh.renderOrder = 5; mesh.userData.iMul = iMul;
      this.group.add(mesh); this.shells.push(mesh);
    }
    if (kind === 'black') {       // thin white rim glow around the smoke
      const m = auraMaterial(0); m.uniforms.uColor.value = new THREE.Color('#d8ccff'); m.uniforms.uSpeed.value = 2.4;
      const rim = new THREE.Mesh(auraGeo(), m); rim.scale.setScalar(1.32); rim.userData.iMul = 0.35; rim.renderOrder = 6;
      this.group.add(rim); this.shells.push(rim);
    }
    this.glow = glowSprite(kind === 'black' ? new THREE.Color('#6a5a90') : kind === 'rainbow' ? new THREE.Color('#ffffff') : this.color, 7.5, 0.3);
    this.glow.position.y = 3.4; this.group.add(this.glow);
    this.ground = new THREE.Mesh(new THREE.PlaneGeometry(9, 9), new THREE.MeshBasicMaterial({
      map: glowTex(), color: kind === 'black' ? 0x000000 : (kind === 'rainbow' ? 0xffffff : this.color),
      blending: kind === 'black' ? THREE.NormalBlending : THREE.AdditiveBlending, transparent: true, depthWrite: false, opacity: 0.8,
    }));
    this.ground.rotation.x = -Math.PI / 2; this.ground.position.y = 0.06; this.group.add(this.ground);
    const N = opts.particles ?? (kind === 'rainbow' ? 260 : 110);
    this.parts = new Particles(N, kind === 'black' ? glowTex() : sparkleTex());
    this.group.add(this.parts.obj);
    if (kind === 'black') {
      this.smoke = new Particles(70, smokeTex(), false);
      this.group.add(this.smoke.obj);
    }
    this.R = rng(opts.seed || 3);
    this.seeds = Array.from({ length: Math.max(N, 70) }, () => [this.R(), this.R(), this.R(), this.R()]);
    this.light = null;
    if (opts.light !== false) {
      this.light = new THREE.PointLight(kind === 'black' ? 0x8866cc : this.color, 0, 16, 1.6);
      this.light.position.y = 3; this.group.add(this.light);
    }
    this.intensity = 1;
  }

  update(t, intensity = 1, scale = 1) {
    this.intensity = intensity;
    this.group.visible = intensity > 0.001;
    if (!this.group.visible) { if (this.light) this.light.intensity = 0; return; }
    const flick = 0.88 + 0.12 * Math.sin(t * 17.0) * Math.sin(t * 7.3);
    for (const s of this.shells) {
      s.material.uniforms.uTime.value = t;
      s.material.uniforms.uI.value = intensity * s.userData.iMul * flick;
      s.material.uniforms.uH.value = 7.6;
    }
    this.group.scale.setScalar(scale);
    this.glow.material.opacity = 0.28 * Math.min(1.2, intensity) * flick;
    this.ground.material.opacity = (this.kind === 'black' ? 0.6 : 0.45) * Math.min(1, intensity);
    if (this.light) this.light.intensity = (this.kind === 'rainbow' ? 60 : 30) * intensity * flick;
    if (this.kind === 'rainbow') {
      const c = new THREE.Color().setHSL((t * 0.35) % 1, 0.9, 0.6);
      this.glow.material.color.copy(c); this.ground.material.color.copy(c);
      if (this.light) this.light.color.copy(c);
    }
    const K = this.kind, S = this.seeds, col = this.color;
    this.parts.fill((i, o) => {
      const [a, b, c, d] = S[i];
      const life = K === 'rainbow' ? 1.3 : 1.8;
      const ph = (t / life + a) % 1;
      const ang = b * 6.283 + t * (K === 'rainbow' ? 2.2 : 0.6) * (c < 0.5 ? 1 : -1);
      const rad = 0.9 + c * 1.6 + ph * (K === 'rainbow' ? 1.4 : 0.5);
      o.x = Math.cos(ang) * rad; o.z = Math.sin(ang) * rad; o.y = ph * 7.5 + d * 0.5;
      o.a = Math.sin(ph * Math.PI) * intensity * (K === 'black' ? 0.55 : 0.95);
      o.size = (K === 'black' ? 0.35 : 0.55) * (0.6 + d * 0.8);
      o.rot = t * 2 + a * 6;
      if (K === 'rainbow') { const cc = new THREE.Color().setHSL((a + t * 0.3) % 1, 1, 0.62); o.r = cc.r; o.g = cc.g; o.b = cc.b; }
      else if (K === 'black') { o.r = 0.75; o.g = 0.7; o.b = 1.0; }
      else { o.r = Math.min(1, col.r * 1.2 + 0.2); o.g = Math.min(1, col.g * 1.2 + 0.2); o.b = Math.min(1, col.b * 1.2 + 0.2); }
    });
    if (this.smoke) {
      this.smoke.fill((i, o) => {
        const [a, b, c, d] = S[i];
        const ph = (t / 3.2 + a) % 1;
        const ang = b * 6.283 + t * 0.5 + ph * 2.0;
        const rad = 1.0 + c * 1.2 + ph * 2.2;
        o.x = Math.cos(ang) * rad; o.z = Math.sin(ang) * rad; o.y = 0.2 + ph * 8.0;
        o.r = 0.04; o.g = 0.02; o.b = 0.07;
        o.a = Math.sin(ph * Math.PI) * 0.9 * intensity;
        o.size = 2.4 + ph * 3.5 + d; o.rot = a * 6 + t * (c - 0.5);
      });
    }
  }
}

// ------------------------------------------------------------------ ribbon trail
// pathFn(t) -> THREE.Vector3; draws the last `len` seconds of the path
export class Trail {
  constructor(color, width = 1.6, segs = 48, rainbow = false) {
    this.segs = segs; this.width = width; this.rainbow = rainbow;
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(segs * 2 * 3), 3));
    g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(segs * 2 * 4), 4));
    g.setAttribute('sd', new THREE.BufferAttribute(new Float32Array(segs * 2).map((_, i) => i % 2), 1));
    const idx = [];
    for (let i = 0; i < segs - 1; i++) { const a = i * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    g.setIndex(idx);
    this.mat = new THREE.ShaderMaterial({
      vertexShader: `attribute vec4 color; attribute float sd; varying vec4 vC; varying float vS; void main(){ vC=color; vS = sd; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);} `,
      fragmentShader: `varying vec4 vC; varying float vS; void main(){ float e = 1.0 - pow(abs(vS*2.0-1.0), 2.0); gl_FragColor = vec4(vC.rgb*vC.a*(0.35+0.65*e), 1.0);} `,
      transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    });
    this.color = new THREE.Color(color);
    this.mesh = new THREE.Mesh(g, this.mat); this.mesh.frustumCulled = false;
    this.geo = g;
  }
  update(t, pathFn, len, camera, alpha = 1, t0 = -1e9) {
    const P = this.geo.attributes.position.array, C = this.geo.attributes.color.array;
    const camPos = camera.position;
    const pts = [];
    for (let i = 0; i < this.segs; i++) pts.push(pathFn(Math.max(t0, t - len * i / (this.segs - 1))));
    const tmp = new THREE.Vector3(), side = new THREE.Vector3(), view = new THREE.Vector3();
    for (let i = 0; i < this.segs; i++) {
      const p = pts[i], q = pts[Math.min(this.segs - 1, i + 1)], pp = pts[Math.max(0, i - 1)];
      tmp.subVectors(pp, q); if (tmp.lengthSq() < 1e-8) tmp.set(1, 0, 0);
      view.subVectors(camPos, p).normalize();
      side.crossVectors(tmp, view).normalize();
      const k = i / (this.segs - 1);
      const w = this.width * (1 - k * 0.85);
      P.set([p.x + side.x * w, p.y + side.y * w, p.z + side.z * w, p.x - side.x * w, p.y - side.y * w, p.z - side.z * w], i * 6);
      let c = this.color;
      if (this.rainbow) c = new THREE.Color().setHSL((k * 1.4 + t * 0.4) % 1, 1, 0.58);
      const a = Math.pow(1 - k, 1.4) * alpha;
      C.set([c.r, c.g, c.b, a, c.r, c.g, c.b, a], i * 8);
    }
    this.geo.attributes.position.needsUpdate = true; this.geo.attributes.color.needsUpdate = true;
    this.mesh.visible = alpha > 0.001;
  }
}

// ------------------------------------------------------------------ shockwave ring
export class Shockwave {
  constructor(color = 0xffffff) {
    this.mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({
      map: ringTex(), color, blending: THREE.AdditiveBlending, transparent: true, depthWrite: false, side: THREE.DoubleSide }));
    this.mesh.rotation.x = -Math.PI / 2;
  }
  update(t, t0, dur = 1.0, maxR = 30, rainbow = false) {
    const k = (t - t0) / dur;
    this.mesh.visible = k >= 0 && k <= 1;
    if (!this.mesh.visible) return;
    const r = maxR * (1 - Math.pow(1 - k, 2.5));
    this.mesh.scale.set(r * 2, r * 2, 1);
    this.mesh.material.opacity = (1 - k) * 1.0;
    if (rainbow) this.mesh.material.color.setHSL((t * 0.8) % 1, 0.9, 0.62);
  }
}

// ------------------------------------------------------------------ light beams (crystal leaks, rainbow pillar)
export function beamMaterial() {
  return new THREE.ShaderMaterial({
    uniforms: { uColor: { value: new THREE.Color(1, 1, 1) }, uA: { value: 1 }, uTime: { value: 0 } },
    vertexShader: `varying vec2 vUv; void main(){ vUv=uv; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);} `,
    fragmentShader: `uniform vec3 uColor; uniform float uA, uTime; varying vec2 vUv;
      void main(){ float x = 1.0 - pow(abs(vUv.x*2.0-1.0), 1.5); float y = pow(1.0 - vUv.y, 1.2);
        float shimmer = 0.75 + 0.25*sin(vUv.y*30.0 - uTime*12.0);
        float a = x*y*uA*shimmer; gl_FragColor = vec4(uColor*a, 1.0);} `,
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
  });
}
export class Beam {
  // a camera-facing-ish crossed quad beam from origin along +Y (rotate group to aim)
  constructor(len = 10, width = 0.8) {
    this.group = new THREE.Group();
    this.mat = beamMaterial();
    const geo = new THREE.PlaneGeometry(width, len); geo.translate(0, len / 2, 0);
    for (let k = 0; k < 2; k++) { const m = new THREE.Mesh(geo, this.mat); m.rotation.y = k * Math.PI / 2; this.group.add(m); }
  }
  set(t, color, a) { this.mat.uniforms.uColor.value.copy(color); this.mat.uniforms.uA.value = a; this.mat.uniforms.uTime.value = t; this.group.visible = a > 0.001; }
}

// ------------------------------------------------------------------ blocky confetti (instanced cubes)
export class Confetti {
  constructor(n = 220, seed = 8) {
    this.n = n;
    this.mesh = new THREE.InstancedMesh(new THREE.BoxGeometry(0.32, 0.32, 0.32), new THREE.MeshBasicMaterial({ toneMapped: false }), n);
    this.mesh.frustumCulled = false;
    const R = rng(seed);
    this.p = Array.from({ length: n }, () => ({
      dir: new THREE.Vector3(R() - 0.5, R() * 0.9 + 0.2, R() - 0.5).normalize(),
      sp: 9 + R() * 16, rot: new THREE.Vector3(R() * 9, R() * 9, R() * 9), hue: R(), s: 0.6 + R() * 0.9,
    }));
    for (let i = 0; i < n; i++) this.mesh.setColorAt(i, new THREE.Color().setHSL(this.p[i].hue, 0.95, 0.6));
    this.m = new THREE.Matrix4(); this.q = new THREE.Quaternion(); this.e = new THREE.Euler(); this.v = new THREE.Vector3(); this.sc = new THREE.Vector3();
  }
  update(t, t0, origin, dur = 3.5) {
    const k = t - t0;
    this.mesh.visible = k >= 0 && k <= dur;
    if (!this.mesh.visible) return;
    for (let i = 0; i < this.n; i++) {
      const p = this.p[i];
      const drag = (1 - Math.exp(-k * 1.6)) / 1.6;
      this.v.copy(p.dir).multiplyScalar(p.sp * drag).add(origin);
      this.v.y += -4.5 * k * k * 0.5 + 0.0;
      this.v.y = Math.max(0.2, this.v.y);
      this.e.set(p.rot.x * k, p.rot.y * k, p.rot.z * k); this.q.setFromEuler(this.e);
      const s = p.s * clamp((dur - k) / 0.8) * clamp(k / 0.05);
      this.sc.set(s, s, s);
      this.m.compose(this.v, this.q, this.sc);
      this.mesh.setMatrixAt(i, this.m);
    }
    this.mesh.instanceMatrix.needsUpdate = true;
  }
}
