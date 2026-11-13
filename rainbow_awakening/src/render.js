// Renders frames of the video in headless Chromium (WebGL via SwiftShader) with N parallel workers.
//
//   node src/render.js --w 1080 --out frames/full                # all 2700 frames
//   node src/render.js --w 540 --step 2 --out frames/preview      # quick low-res preview (every 2nd frame)
//   node src/render.js --w 540 --times 1.5,30,79 --out frames/stills
//
// Frames are written as <out>/f_00000.jpg (frame index = time * 30). Existing frames are skipped,
// so an interrupted render resumes where it stopped (use --force to re-render).
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const args = Object.fromEntries(process.argv.slice(2).reduce((a, x, i, arr) => {
  if (x.startsWith('--')) a.push([x.slice(2), arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true]);
  return a;
}, []));
const W = +(args.w || 1080);
const FPS = 30, N = 2700;
const out = path.resolve(args.out || 'frames/full');
const workers = +(args.workers || 3);
const quality = +(args.q || 0.95);
fs.mkdirSync(out, { recursive: true });

let frames;
if (args.times) frames = String(args.times).split(',').map(s => Math.round(parseFloat(s) * FPS));
else {
  const [a, b] = String(args.frames || `0:${N}`).split(':').map(Number);
  const step = +(args.step || 1);
  frames = [];
  for (let f = a; f < b; f += step) frames.push(f);
}
const todo = frames.filter(f => args.force || !fs.existsSync(path.join(out, `f_${String(f).padStart(5, '0')}.jpg`)));
console.log(`${frames.length} frames requested, ${todo.length} to render at ${W}x${Math.round(W * 16 / 9)} with ${workers} workers -> ${out}`);

const MIME = { '.js': 'text/javascript', '.html': 'text/html', '.json': 'application/json', '.woff2': 'font/woff2' };
function resolve(p) {
  if (p === '/' || p === '/index.html') return path.join(ROOT, 'web/index.html');
  if (p.startsWith('/web/')) return path.join(ROOT, p);
  if (p.startsWith('/build/')) return path.join(ROOT, p);
  if (p.startsWith('/three/')) return path.join(ROOT, 'node_modules', p);
  if (p.startsWith('/font/')) return path.join(ROOT, 'node_modules/@fontsource/lilita-one/files', p.slice(6));
  return null;
}

async function worker(id, list) {
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--disable-gpu-vsync'] });
  const page = await browser.newPage({ viewport: { width: 400, height: 700 } });
  await page.route('http://render.local/**', route => {
    const u = new URL(route.request().url());
    const f = resolve(u.pathname);
    if (!f || !fs.existsSync(f)) return route.fulfill({ status: 404, body: 'not found' });
    route.fulfill({ body: fs.readFileSync(f), contentType: MIME[path.extname(f)] || 'application/octet-stream' });
  });
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') console.log(`[w${id}] ${m.type()}: ${m.text()}`); });
  page.on('pageerror', e => console.log(`[w${id}] PAGE ERROR: ${e.message}`));
  await page.goto(`http://render.local/?w=${W}`);
  await page.waitForFunction('window.ready || window.bootError', null, { timeout: 120000 });
  const err = await page.evaluate('window.bootError');
  if (err) throw new Error(err);
  const t0 = Date.now();
  let done = 0;
  for (const f of list) {
    const url = await page.evaluate(([f, q]) => window.renderFrame(f, q), [f, quality]);
    fs.writeFileSync(path.join(out, `f_${String(f).padStart(5, '0')}.jpg`), Buffer.from(url.split(',')[1], 'base64'));
    done++;
    if (done % 25 === 0 || done === list.length) {
      const el = (Date.now() - t0) / 1000;
      console.log(`[w${id}] ${done}/${list.length} frames, ${(el / done).toFixed(2)} s/frame, last f=${f}`);
    }
  }
  if (args.info) console.log(`[w${id}]`, await page.evaluate('window.sceneInfo()'));
  await browser.close();
}

(async () => {
  const lists = Array.from({ length: workers }, () => []);
  todo.forEach((f, i) => lists[i % workers].push(f));
  const T = Date.now();
  await Promise.all(lists.filter(l => l.length).map((l, i) => worker(i, l)));
  console.log(`done in ${((Date.now() - T) / 1000).toFixed(1)} s`);
})().catch(e => { console.error(e); process.exit(1); });
