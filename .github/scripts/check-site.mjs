// Loads the built site in headless Chromium and fails on what a successful
// `jekyll build` can't catch: page errors, missing files, dashboards that
// render blank (the Liquid trap in CLAUDE.md), a broken theme toggle, and
// charts that come out differently on a dark page load than after toggling.
//
//   node .github/scripts/check-site.mjs [base-url]   (default http://127.0.0.1:8123)
//
// Set CHROMIUM_PATH to use a preinstalled Chromium instead of Playwright's.

import { chromium } from 'playwright';

const BASE = process.argv[2] || 'http://127.0.0.1:8123';
const PAGES = [
  { path: '/', charts: 0 },
  { path: '/blog/', charts: 0 },
  { path: '/cv/', charts: 2 },
  { path: '/exercise/', charts: 10 },
  { path: '/music/', charts: 10 },
];

// Every colour each chart resolves to, keyed by canvas id.
const SNAPSHOT = () => typeof Chart === 'undefined' ? [] : Object.values(Chart.instances).map(ch => [
  ch.canvas.id,
  JSON.stringify(ch.data.datasets.map(d => [d.borderColor, d.backgroundColor, d.pointBackgroundColor])),
  JSON.stringify(Object.entries(ch.options.scales || {}).map(([k, s]) =>
    [k, s.ticks && s.ticks.color, s.grid && s.grid.color, s.angleLines && s.angleLines.color])),
]).sort((a, b) => a[0].localeCompare(b[0]));

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
const failures = [];
const fail = (path, msg) => { failures.push(`${path}: ${msg}`); console.log(`  ✗ ${msg}`); };

async function open(path, colorScheme) {
  const context = await browser.newContext({ colorScheme, viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const problems = [];
  page.on('pageerror', e => problems.push(`page error: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) problems.push(`console error: ${m.text()}`); });
  page.on('response', r => { if (r.status() >= 400) problems.push(`${r.status()} ${new URL(r.url()).pathname}`); });
  page.on('requestfailed', r => problems.push(`request failed: ${r.url()}`));
  await page.goto(BASE + path, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(1000);
  return { context, page, problems };
}

for (const { path, charts } of PAGES) {
  console.log(path);
  const light = await open(path, 'light');
  const { page } = light;

  const built = await page.evaluate(() => typeof Chart === 'undefined' ? 0 : Object.keys(Chart.instances).length);
  if (built < charts) fail(path, `expected at least ${charts} charts, found ${built}`);

  const before = await page.evaluate(SNAPSHOT);
  await page.click('#theme-toggle');
  await page.waitForTimeout(500);
  if (await page.evaluate(() => document.documentElement.getAttribute('data-theme')) !== 'dark') fail(path, 'theme toggle did not switch to dark');
  const toggledDark = await page.evaluate(SNAPSHOT);
  await page.click('#theme-toggle');
  await page.waitForTimeout(500);
  const restored = await page.evaluate(SNAPSHOT);

  const dark = await open(path, 'dark');
  const loadedDark = await dark.page.evaluate(SNAPSHOT);

  if (charts) {
    const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
    if (!same(loadedDark, toggledDark)) fail(path, 'charts differ between a dark page load and toggling to dark');
    if (!same(before, restored)) fail(path, 'charts not restored after toggling back to light');
    if (same(before, toggledDark)) fail(path, 'charts did not change in dark mode');
  }
  for (const p of [...new Set([...light.problems, ...dark.problems])]) fail(path, p);
  if (!failures.some(f => f.startsWith(path + ':'))) console.log(`  ✓ ${built} charts, toggle and theme consistency OK`);

  await light.context.close();
  await dark.context.close();
}

await browser.close();
if (failures.length) {
  console.log(`\n${failures.length} problem(s):\n` + failures.map(f => '  ' + f).join('\n'));
  process.exit(1);
}
console.log('\nAll pages OK.');
