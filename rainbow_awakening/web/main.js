// Page entry: builds the world once, then window.renderFrame(f) renders frame f (pure function of time).
import * as THREE from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { World } from './world.js';
import { Overlay } from './overlay.js';
import { Director } from './scenes.js';

const params = new URLSearchParams(location.search);
const W = +(params.get('w') || 1080), H = Math.round(W * 16 / 9);
const FPS = 30;

async function boot() {
  const font = new FontFace('Lilita One', 'url(/font/lilita-one-latin-400-normal.woff2)');
  await font.load(); document.fonts.add(font);
  const timing = await (await fetch('/build/timing.json')).json();

  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(1); renderer.setSize(W, H);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.NeutralToneMapping; renderer.toneMappingExposure = 1.0;
  document.body.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const pm = new THREE.PMREMGenerator(renderer);
  scene.environment = pm.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.55;
  const camera = new THREE.PerspectiveCamera(40, W / H, 0.1, 2000);

  const world = new World(scene);
  freezeStatic(scene);
  const overlay = new Overlay(W, H, timing);
  const director = new Director(scene, camera, world, timing, renderer);

  window.renderFrame = (f, quality = 0.95) => {
    const t = f / FPS;
    const fx = director.update(t);
    renderer.toneMappingExposure = fx.exposure ?? 1.0;
    renderer.render(scene, camera);
    const out = overlay.compose(renderer.domElement, t, fx);
    return out.toDataURL('image/jpeg', quality);
  };
  window.dbg = { scene, camera, director, THREE, renderer };
  window.sceneInfo = () => ({ W, H, calls: renderer.info.render.calls, tris: renderer.info.render.triangles });
  window.ready = true;
}

// Merge every static mesh (userData.dynamic not set, not inside a character / fx) into one mesh per material.
function freezeStatic(scene) {
  const byMat = new Map();
  const remove = [];
  scene.updateMatrixWorld(true);
  scene.traverse(o => {
    if (!o.isMesh || o.userData.dynamic || o.userData.owner) return;
    let p = o.parent, ok = true;
    while (p && p !== scene) { if (p.userData.dynamic) { ok = false; break; } p = p.parent; }
    if (!ok || !o.material || Array.isArray(o.material) || o.material.isShaderMaterial || o.material.transparent) return;
    const g = (o.geometry.index ? o.geometry.toNonIndexed() : o.geometry.clone());
    for (const k of Object.keys(g.attributes)) if (!['position', 'normal', 'uv'].includes(k)) g.deleteAttribute(k);
    if (!g.attributes.uv) g.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(g.attributes.position.count * 2), 2));
    g.clearGroups();
    g.applyMatrix4(o.matrixWorld);
    const key = o.material.uuid + (o.castShadow ? 'c' : '') + (o.receiveShadow ? 'r' : '');
    if (!byMat.has(key)) byMat.set(key, { mat: o.material, geos: [], cast: o.castShadow, recv: o.receiveShadow });
    byMat.get(key).geos.push(g);
    remove.push(o);
  });
  for (const o of remove) o.parent.remove(o);
  for (const { mat, geos, cast, recv } of byMat.values()) {
    const m = new THREE.Mesh(mergeGeometries(geos, false), mat);
    m.castShadow = cast; m.receiveShadow = recv;
    scene.add(m);
  }
}

boot().catch(e => { console.error('BOOT FAILED', e.stack || e); window.bootError = String(e.stack || e); });
