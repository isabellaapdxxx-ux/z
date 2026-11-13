// Original blocky character rig (Roblox-inspired proportions, no Roblox assets).
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { faceTex } from './lib.js';

const matCache = new Map();
export function plastic(color, extra = {}) {
  const key = color + JSON.stringify(extra);
  if (!matCache.has(key)) matCache.set(key, new THREE.MeshStandardMaterial({ color, roughness: 0.5, metalness: 0.0, ...extra }));
  return matCache.get(key);
}
const geoCache = new Map();
export function rbox(w, h, d, r = 0.1) {
  const key = [w, h, d, r].join();
  if (!geoCache.has(key)) geoCache.set(key, new RoundedBoxGeometry(w, h, d, 2, r));
  return geoCache.get(key);
}
export function mesh(geo, mat, x = 0, y = 0, z = 0, parent) {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true;
  if (parent) parent.add(m);
  return m;
}

const faceCache = new Map();
function getFace(expr, opts) {
  const key = expr + JSON.stringify(opts || {});
  if (!faceCache.has(key)) faceCache.set(key, faceTex(expr, opts));
  return faceCache.get(key);
}

export class Character {
  constructor(o) {
    this.o = Object.assign({
      skin: '#f3c29b', shirt: '#e74c3c', pants: '#34495e', shoes: '#ffffff', shoeAccent: '#e23b3b',
      hair: '#4a2c17', hairStyle: 'cap', hoodie: false, cape: null, scale: 1,
    }, o);
    const O = this.o;
    this.root = new THREE.Group();
    this.root.scale.setScalar(O.scale);
    this.hips = new THREE.Group(); this.hips.position.y = 2; this.root.add(this.hips);
    this.torso = new THREE.Group(); this.hips.add(this.torso);
    const shirt = plastic(O.shirt), skin = plastic(O.skin), pants = plastic(O.pants);
    mesh(rbox(2, 2, 1, 0.14), shirt, 0, 1, 0, this.torso);
    if (O.hoodie) {
      const dark = plastic(O.hoodieDark || '#1f5fb8');
      mesh(rbox(1.7, 0.75, 0.75, 0.25), shirt, 0, 2.02, -0.42, this.torso);          // hood
      mesh(rbox(1.3, 0.62, 0.08, 0.04), dark, 0, 0.55, 0.52, this.torso);            // front pocket
      mesh(rbox(1.92, 0.22, 1.04, 0.08), dark, 0, 0.1, 0, this.torso);              // waistband
      const str = plastic('#f4f4f4');
      for (const s of [-1, 1]) mesh(new THREE.BoxGeometry(0.08, 0.5, 0.06), str, s * 0.22, 1.62, 0.53, this.torso);
    }
    if (O.belt) mesh(rbox(2.04, 0.22, 1.04, 0.06), plastic(O.belt), 0, 0.1, 0, this.torso);
    if (O.emblem) {
      const em = mesh(new THREE.CylinderGeometry(0.42, 0.42, 0.06, 6), plastic(O.emblem, { emissive: O.emblem, emissiveIntensity: 0.25 }), 0, 1.25, 0.52, this.torso);
      em.rotation.x = Math.PI / 2;
    }
    // head
    this.headPivot = new THREE.Group(); this.headPivot.position.y = 2.0; this.torso.add(this.headPivot);
    this.head = mesh(rbox(1.34, 1.3, 1.3, 0.26), skin, 0, 0.7, 0, this.headPivot);
    this.faceMat = new THREE.MeshStandardMaterial({ map: getFace('smile'), transparent: true, roughness: 0.6, depthWrite: false, polygonOffset: true, polygonOffsetFactor: -2 });
    this.face = new THREE.Mesh(new THREE.PlaneGeometry(1.12, 1.12), this.faceMat);
    this.face.position.set(0, 0.68, 0.656); this.headPivot.add(this.face);
    this.expr = 'smile';
    this.buildHair(O);
    // arms (pivot at shoulder)
    this.armL = new THREE.Group(); this.armL.position.set(-1.48, 1.86, 0); this.torso.add(this.armL);
    this.armR = new THREE.Group(); this.armR.position.set(1.48, 1.86, 0); this.torso.add(this.armR);
    for (const a of [this.armL, this.armR]) {
      mesh(rbox(0.94, 1.55, 0.94, 0.12), shirt, 0, -0.72, 0, a);
      mesh(rbox(0.86, 0.5, 0.86, 0.12), skin, 0, -1.7, 0, a);
    }
    // legs (pivot at hip)
    this.legL = new THREE.Group(); this.legL.position.set(-0.5, 0, 0); this.hips.add(this.legL);
    this.legR = new THREE.Group(); this.legR.position.set(0.5, 0, 0); this.hips.add(this.legR);
    const shoe = plastic(O.shoes), acc = plastic(O.shoeAccent), sole = plastic('#d9d9d9');
    for (const [l, s] of [[this.legL, -1], [this.legR, 1]]) {
      mesh(rbox(0.98, 1.72, 1, 0.1), pants, 0, -0.86, 0, l);
      mesh(rbox(1.04, 0.36, 1.32, 0.1), shoe, 0, -1.8, 0.12, l);
      mesh(new THREE.BoxGeometry(1.06, 0.1, 1.34), sole, 0, -1.95, 0.12, l);
      mesh(new THREE.BoxGeometry(0.06, 0.16, 0.7), acc, s * 0.53, -1.78, 0.1, l);
    }
    if (O.cape) {
      this.cape = new THREE.Group(); this.cape.position.set(0, 1.95, -0.55); this.torso.add(this.cape);
      mesh(rbox(1.9, 2.9, 0.1, 0.04), plastic(O.cape), 0, -1.45, 0, this.cape);
    }
    this.root.traverse(m => { m.userData.owner = this; });
  }

  buildHair(O) {
    const hm = plastic(O.hair, { roughness: 0.7 });
    const h = new THREE.Group(); h.position.y = 0.7; this.headPivot.add(h);
    const st = O.hairStyle;
    if (st === 'cap' || st === 'max') {
      mesh(rbox(1.46, 0.42, 1.44, 0.16), hm, 0, 0.62, -0.02, h);
      mesh(rbox(1.46, 0.9, 0.36, 0.12), hm, 0, 0.25, -0.58, h);
      mesh(rbox(0.6, 0.3, 0.3, 0.1), hm, -0.32, 0.45, 0.62, h);                // fringe tuft
      mesh(rbox(0.5, 0.26, 0.3, 0.1), hm, 0.28, 0.48, 0.6, h).rotation.z = -0.25;
      if (st === 'max') {
        const t = mesh(rbox(0.36, 0.36, 0.36, 0.1), hm, 0.05, 0.92, 0.1, h); t.rotation.set(0.3, 0.5, 0.4);  // cowlick
      }
    } else if (st === 'spiky') {
      mesh(rbox(1.44, 0.34, 1.42, 0.12), hm, 0, 0.6, 0, h);
      for (let i = 0; i < 6; i++) {
        const s = mesh(rbox(0.42, 0.5, 0.42, 0.08), hm, -0.5 + (i % 3) * 0.5, 0.85, -0.3 + Math.floor(i / 3) * 0.6, h);
        s.rotation.set(0.3 * (i % 2 ? 1 : -1), 0.4, 0.5 * ((i % 3) - 1));
      }
    } else if (st === 'long') {
      mesh(rbox(1.48, 0.42, 1.46, 0.16), hm, 0, 0.62, 0, h);
      mesh(rbox(1.5, 1.7, 0.4, 0.14), hm, 0, -0.1, -0.56, h);
      for (const s of [-1, 1]) mesh(rbox(0.3, 1.3, 1.1, 0.1), hm, s * 0.7, 0.05, -0.12, h);
      mesh(rbox(1.2, 0.26, 0.3, 0.1), hm, 0, 0.44, 0.6, h);
    } else if (st === 'puff') {
      mesh(rbox(1.75, 1.0, 1.7, 0.45), hm, 0, 0.62, -0.1, h);
    } else if (st === 'buns') {
      mesh(rbox(1.46, 0.4, 1.44, 0.16), hm, 0, 0.6, 0, h);
      for (const s of [-1, 1]) mesh(rbox(0.6, 0.6, 0.6, 0.26), hm, s * 0.72, 0.82, -0.1, h);
      mesh(rbox(1.46, 0.8, 0.34, 0.12), hm, 0, 0.25, -0.58, h);
    } else if (st === 'beanie') {
      const b = plastic(O.beanie || '#333344');
      mesh(rbox(1.5, 0.62, 1.48, 0.2), b, 0, 0.6, 0, h);
      mesh(rbox(1.56, 0.22, 1.54, 0.1), plastic(O.beanieBand || '#555566'), 0, 0.32, 0, h);
    }
  }

  setFace(expr, opts) {
    const key = expr + JSON.stringify(opts || {});
    if (this._fk === key) return;
    this._fk = key; this.expr = expr;
    this.faceMat.map = getFace(expr, opts); this.faceMat.needsUpdate = true;
  }

  reset() {
    this.root.rotation.set(0, this.root.rotation.y, 0);
    this.hips.position.set(0, 2, 0); this.hips.rotation.set(0, 0, 0);
    this.torso.rotation.set(0, 0, 0); this.torso.position.set(0, 0, 0); this.torso.scale.set(1, 1, 1);
    this.headPivot.rotation.set(0, 0, 0);
    for (const p of [this.armL, this.armR, this.legL, this.legR]) p.rotation.set(0, 0, 0);
    if (this.cape) this.cape.rotation.set(0.12, 0, 0);
    this.root.visible = true;
    return this;
  }

  idle(t, k = 1) {
    const b = Math.sin(t * 2.2 + this.o.seed || 0);
    this.torso.scale.y = 1 + 0.012 * b * k;
    this.armL.rotation.z = -0.06 - 0.03 * b * k; this.armR.rotation.z = 0.06 + 0.03 * b * k;
    this.headPivot.rotation.y = 0.08 * Math.sin(t * 0.7 + (this.o.seed || 0));
    if (this.cape) this.cape.rotation.x = 0.12 + 0.05 * Math.sin(t * 1.7);
    return this;
  }

  walk(t, speed = 1, amp = 0.55) {
    const p = t * 5.2 * speed;
    const s = Math.sin(p);
    this.legL.rotation.x = s * amp; this.legR.rotation.x = -s * amp;
    this.armL.rotation.x = -s * amp * 0.9; this.armR.rotation.x = s * amp * 0.9;
    this.hips.position.y = 2 + Math.abs(Math.cos(p)) * 0.12;
    this.torso.rotation.y = s * 0.06;
    if (this.cape) this.cape.rotation.x = 0.3 + 0.1 * Math.sin(p * 2);
    return this;
  }

  run(t, speed = 1) {
    const p = t * 9 * speed, s = Math.sin(p);
    this.legL.rotation.x = s * 1.0; this.legR.rotation.x = -s * 1.0;
    this.armL.rotation.x = -s * 1.1; this.armR.rotation.x = s * 1.1;
    this.armL.rotation.z = -0.1; this.armR.rotation.z = 0.1;
    this.hips.position.y = 2 + Math.abs(Math.cos(p)) * 0.3;
    this.hips.rotation.x = 0.28;
    this.headPivot.rotation.x = -0.2;
    if (this.cape) this.cape.rotation.x = 0.9 + 0.15 * Math.sin(p * 2);
    return this;
  }

  fly(t, k = 1) {   // superhero flight pose (root should be rotated/moved by caller)
    this.hips.rotation.x = 1.25 * k;
    this.headPivot.rotation.x = -0.9 * k;
    this.armR.rotation.x = -2.9 * k; this.armR.rotation.z = 0.15 * k;
    this.armL.rotation.x = 0.35 * k; this.armL.rotation.z = -0.2 * k;
    this.legL.rotation.x = 0.1 * Math.sin(t * 6) * k; this.legR.rotation.x = 0.12 * k + 0.1 * Math.sin(t * 6 + 1) * k;
    if (this.cape) this.cape.rotation.x = 1.3 + 0.12 * Math.sin(t * 10);
    return this;
  }

  sit(seatH = 1.2, headDown = 0.5, t = 0) {
    const a = Math.acos(Math.min(0.95, seatH / 2.1));
    this.hips.position.y = seatH + 0.05;
    this.legL.rotation.x = -a; this.legR.rotation.x = -a;
    this.torso.rotation.x = 0.28 + 0.015 * Math.sin(t * 1.6);
    this.headPivot.rotation.x = headDown;
    this.armL.rotation.set(-0.9, 0, 0.18); this.armR.rotation.set(-0.9, 0, -0.18);
    return this;
  }

  arms(lx, lz, rx, rz) {
    this.armL.rotation.x = lx; this.armL.rotation.z = lz;
    this.armR.rotation.x = rx; this.armR.rotation.z = rz;
    return this;
  }
}

export function makeMax() {
  return new Character({
    name: 'Max', skin: '#f2c49e', shirt: '#2f80ed', hoodie: true, hoodieDark: '#1d5fc4',
    pants: '#2b3a5c', shoes: '#ffffff', shoeAccent: '#ff4757', hair: '#5b3416', hairStyle: 'max', seed: 0,
  });
}
