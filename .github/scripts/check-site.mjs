// Loads the built site in headless Chromium and fails on what a successful
// `jekyll build` can't catch: page errors, missing files, dashboards that
// render blank (the Liquid trap in CLAUDE.md), a broken theme toggle, and
// charts that come out differently on a dark page load than after toggling.
//
//   node .github/scripts/check-site.mjs [base-url]   (default http://127.0.0.1:8123)
//
// Set CHROMIUM_PATH to use a preinstalled Chromium instead of Playwright's.

import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import { cvSourceHash } from '../../tools/cv-pdf/source-hash.mjs';

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

// The CV page links a PDF built from tools/cv-pdf/cv.html. Check that the link
// works, and that the PDF was built for the CV as it reads now: build.mjs
// records a fingerprint of the page's content, and a changed page without a
// rebuilt PDF would quietly serve an out-of-date CV.
async function checkCvPdf(page, path) {
  const href = await page.locator('a.pdf-link').first().getAttribute('href', { timeout: 2000 }).catch(() => null);
  if (!href) return fail(path, 'no PDF download link (a.pdf-link) on the page');
  const res = await fetch(new URL(href, BASE));
  if (!res.ok) return fail(path, `${href} returned ${res.status}`);
  const bytes = Buffer.from(await res.arrayBuffer());
  if (bytes.subarray(0, 5).toString() !== '%PDF-') return fail(path, `${href} is not a PDF`);
  if (bytes.length < 10_000) fail(path, `${href} is only ${bytes.length} bytes; the PDF looks empty`);
  const recorded = readFileSync(new URL('../../tools/cv-pdf/source.sha256', import.meta.url), 'utf8').trim();
  if (recorded !== await cvSourceHash(page))
    fail(path, 'the CV page has changed since its PDF was built. Update tools/cv-pdf/cv.html to match, then run tools/cv-pdf/build.mjs (see CLAUDE.md).');
}

for (const { path, charts } of PAGES) {
  console.log(path);
  const light = await open(path, 'light');
  const { page } = light;

  const built = await page.evaluate(() => typeof Chart === 'undefined' ? 0 : Object.keys(Chart.instances).length);
  if (built < charts) fail(path, `expected at least ${charts} charts, found ${built}`);
  if (path === '/cv/') await checkCvPdf(page, path);

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
