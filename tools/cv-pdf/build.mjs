// Renders tools/cv-pdf/cv.html to cv/Kambiz-Kamrani-CV.pdf, and records in
// tools/cv-pdf/source.sha256 which version of the web CV it was written for.
//
//   bundle exec ruby -e "require 'jekyll'; Jekyll::Commands::Build.process({})"
//   (cd _site && python3 -m http.server 8123 &)
//   node tools/cv-pdf/build.mjs [site-url]      (default http://127.0.0.1:8123)
//
// The built site only needs to be running so the web CV can be fingerprinted.
// Needs Playwright with Chromium (set CHROMIUM_PATH to use another Chromium)
// and the Liberation Serif font (Debian/Ubuntu: fonts-liberation). The PDF
// embeds the font, so readers don't need it.

import { chromium } from 'playwright';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { cvSourceHash } from './source-hash.mjs';

const BASE = process.argv[2] || 'http://127.0.0.1:8123';
const TEMPLATE = new URL('./cv.html', import.meta.url);
const PDF = fileURLToPath(new URL('../../cv/Kambiz-Kamrani-CV.pdf', import.meta.url));
const HASH = fileURLToPath(new URL('./source.sha256', import.meta.url));
const FONT = 'Liberation Serif';

const browser = await chromium.launch(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {});
try {
  const web = await browser.newPage();
  await web.goto(BASE + '/cv/', { waitUntil: 'networkidle' });
  const hash = await cvSourceHash(web);
  await web.close();

  const page = await browser.newPage();
  await page.goto(TEMPLATE.href);

  // A missing font would silently fall back to something else and change the
  // layout, so say so rather than write a different-looking PDF.
  const [named, fallback] = await page.evaluate(font => {
    const width = family => {
      const s = document.createElement('span');
      s.style.cssText = `position:absolute;visibility:hidden;font:20px ${family}`;
      s.textContent = 'The quick brown fox, Kamrani 0123456789';
      document.body.append(s);
      const w = s.getBoundingClientRect().width;
      s.remove();
      return w;
    };
    return [width(`"${font}", monospace`), width('monospace')];
  }, FONT);
  if (named === fallback) throw new Error(`The font "${FONT}" is not installed here (Debian/Ubuntu: apt install fonts-liberation).`);

  const updated = new Date().toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  await page.evaluate(d => { document.getElementById('updated').textContent = d; }, updated);

  // Tagged and outlined: screen readers get a real structure, and PDF readers
  // get bookmarks for each section.
  await page.pdf({ path: PDF, preferCSSPageSize: true, printBackground: true, tagged: true, outline: true });
  writeFileSync(HASH, hash + '\n');
  console.log(`Wrote ${PDF}\nRecorded source ${hash.slice(0, 12)}…`);
} finally {
  await browser.close();
}
