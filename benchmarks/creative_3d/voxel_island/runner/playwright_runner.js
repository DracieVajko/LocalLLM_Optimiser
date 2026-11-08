// =============================================================================
// Voxel Island — Playwright runner
// =============================================================================
// Runs the creative_3d benchmark in a headless Chromium:
//   1. Opens runtime/index.html
//   2. Waits for the scene to compile (status changes to OK or error)
//   3. Takes screenshot 1 (initial view)
//   4. Rotates the camera via the "Rotate camera 360°" button
//   5. Takes screenshot 2 (rotated view) — must differ from #1
//   6. Zooms, takes screenshot 3
//   7. Reads HUD status text to determine pass/fail
//   8. Writes results to results/
//
// Usage:
//   npx playwright run runner/playwright_runner.js
//   (adapt to your Playwright setup)
// =============================================================================

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..');
const HTML = path.join(ROOT, 'runtime', 'index.html');
const OUT = path.join(ROOT, 'results');
const SCENE_JS = path.join(ROOT, 'scene.js'); // model output goes here

async function main() {
  fs.mkdirSync(OUT, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1280, height: 720 },
    acceptDownloads: true,
  });

  // Capture console errors from the page (Three.js compile errors etc.)
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });

  const results = {
    task: 'voxel_island',
    timestamp: new Date().toISOString(),
    screenshots: [],
    console_errors: errors,
    checks: {},
    score: 0,
    status: 'failed',
  };

  try {
    await page.goto(HTML, { waitUntil: 'domcontentloaded' });

    // Wait for the scene to finish compiling
    await page.waitForFunction(
      () => document.getElementById('loader')?.classList.contains('hidden') ||
            document.getElementById('status')?.textContent?.includes('failed'),
      { timeout: 120000 }
    );

    // Screenshot 1 — initial view
    const s1 = path.join(OUT, 'screenshot_1_initial.png');
    await page.screenshot({ path: s1, fullPage: true });
    results.screenshots.push(s1);

    // Click "Rotate camera 360°" button
    const rotateBtn = page.locator('button:has-text("Rotate camera 360°")');
    if (await rotateBtn.count() > 0) {
      await rotateBtn.click();
      // Wait a bit for rotation to render
      await page.waitForTimeout(3000);
    }

    // Screenshot 2 — rotated view
    const s2 = path.join(OUT, 'screenshot_2_rotated.png');
    await page.screenshot({ path: s2, fullPage: true });
    results.screenshots.push(s2);

    // Click zoom
    const zoomBtn = page.locator('button:has-text("Zoom out")');
    if (await zoomBtn.count() > 0) {
      await zoomBtn.click();
      await page.waitForTimeout(1000);
    }

    // Screenshot 3 — zoomed
    const s3 = path.join(OUT, 'screenshot_3_zoomed.png');
    await page.screenshot({ path: s3, fullPage: true });
    results.screenshots.push(s3);

    // Read HUD status
    const status = await page.locator('#status').textContent();
    const statusClass = await page.locator('#status').getAttribute('class');
    const details = await page.locator('#details').textContent();

    results.hud = { status, statusClass, details };

    // --- Automatic checks ---
    const checks = {};

    // 1. JavaScript parsed without syntax errors (no console errors mentioning scene.js)
    const sceneErrors = errors.filter(e => e.includes('scene.js') || e.includes('createScene'));
    checks.js_parses = sceneErrors.length === 0;
    checks.console_errors = errors.length;

    // 2. createScene returned a valid group (status OK)
    checks.scene_compiles = statusClass === 'ok';

    // 3. Screenshot 2 differs from screenshot 1 (camera actually rotated)
    checks.camera_rotated = await imagesDiffer(s1, s2);

    // 4. Named groups exist — we can't introspect Three.js from outside easily,
    //    so we rely on the model having built them; we check the scene JS source
    //    if available.
    if (fs.existsSync(SCENE_JS)) {
      const src = fs.readFileSync(SCENE_JS, 'utf8');
      checks.has_terrain = /Terrain/.test(src);
      checks.has_trees = /Trees/.test(src);
      checks.has_waterfall = /Waterfall/.test(src);
      checks.has_vegetation = /Vegetation/.test(src);
      checks.returns_group = /THREE\.Group/.test(src);
      checks.exports_createScene = /export function createScene/.test(src);
    } else {
      checks.has_terrain = false;
      checks.has_trees = false;
      checks.has_waterfall = false;
      checks.has_vegetation = false;
      checks.returns_group = false;
      checks.exports_createScene = false;
    }

    results.checks = checks;

    // --- Score ---
    const weights = {
      js_parses: 0.10,
      scene_compiles: 0.20,
      camera_rotated: 0.15,
      has_terrain: 0.10,
      has_trees: 0.10,
      has_waterfall: 0.10,
      has_vegetation: 0.10,
      returns_group: 0.05,
      exports_createScene: 0.10,
    };
    let score = 0;
    let totalW = 0;
    for (const [k, w] of Object.entries(weights)) {
      if (checks[k]) score += w;
      totalW += w;
    }
    results.score = Math.round((score / totalW) * 100);
    results.status = results.score >= 70 ? 'passed' : 'failed';

  } catch (err) {
    results.status = 'error';
    results.error = err.message;
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(OUT, 'result.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results, null, 2));
  }
}

async function imagesDiffer(a, b) {
  const Jimp = require('jimp');
  try {
    const img1 = await Jimp.read(a);
    const img2 = await Jimp.read(b);
    if (img1.bitmap.width !== img2.bitmap.width || img1.bitmap.height !== img2.bitmap.height) {
      return true;
    }
    let diff = 0;
    const n = img1.bitmap.data.length;
    for (let i = 0; i < n; i += 4) {
      diff += Math.abs(img1.bitmap.data[i] - img2.bitmap.data[i]);
      diff += Math.abs(img1.bitmap.data[i+1] - img2.bitmap.data[i+1]);
      diff += Math.abs(img1.bitmap.data[i+2] - img2.bitmap.data[i+2]);
    }
    return (diff / (n / 4 * 3)) > 3; // mean per-channel diff > 3
  } catch {
    return false; // can't compare — assume rotated if button existed
  }
}

main();
