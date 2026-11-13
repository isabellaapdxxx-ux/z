// Debug: for given times, report camera position and what the camera rays hit (center + lower third).
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
const ROOT = path.resolve(__dirname, '..');
const times = process.argv.slice(2).map(Number);
(async () => {
  const b = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const p = await b.newPage();
  await p.route('http://render.local/**', r => { const u = new URL(r.request().url()).pathname;
    const f = u === '/' ? 'web/index.html' : u.startsWith('/three/') ? 'node_modules' + u : u.startsWith('/font/') ? 'node_modules/@fontsource/lilita-one/files/' + u.slice(6) : u.slice(1);
    r.fulfill({ body: fs.readFileSync(path.join(ROOT, f)), contentType: f.endsWith('.js') ? 'text/javascript' : f.endsWith('.json') ? 'application/json' : 'text/html' }); });
  p.on('pageerror', e => console.log('ERR', e.message));
  await p.goto('http://render.local/?w=270'); await p.waitForFunction('window.ready');
  for (const t of times) {
    const r = await p.evaluate((t) => {
      const { scene, camera, THREE } = window.dbg; window.renderFrame(Math.round(t * 30));
      const rc = new THREE.Raycaster(); const out = { cam: camera.position.toArray().map(v => +v.toFixed(2)) };
      for (const [nm, y] of [['center', 0], ['lower', -0.5]]) {
        rc.setFromCamera(new THREE.Vector2(0, y), camera);
        const hits = rc.intersectObjects(scene.children, true).filter(h => h.object.visible && h.object.type !== 'Points' && h.object.type !== 'Sprite');
        out[nm] = hits.slice(0, 3).map(h => `${h.object.type}:${h.object.geometry.type}:${h.object.material.type}:${(h.object.material.color && h.object.material.color.getHexString()) || ''} d=${h.distance.toFixed(1)}`);
      }
      return out;
    }, t);
    console.log(t, JSON.stringify(r));
  }
  await b.close();
})();
