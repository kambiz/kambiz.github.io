// A fingerprint of what the web CV (/cv/) says, so the downloadable PDF can
// be checked against it. build.mjs records it when the PDF is written, and
// .github/scripts/check-site.mjs recomputes it from the served page: if the
// two differ, the page changed and the PDF has not caught up.
//
// It covers the page's text and link targets. It leaves out what isn't CV
// content, or changes by itself: the stat cards (one is a years-in-practice
// figure that moves with the date), the nav and footer, the charts' canvases,
// and the download link.

import { createHash } from 'node:crypto';

export async function cvSourceHash(page) {
  const text = await page.evaluate(() => {
    const root = document.querySelector('.container').cloneNode(true);
    root.querySelectorAll('.stats-grid, .nav-link, .footer, canvas, .pdf-link').forEach(n => n.remove());
    const links = [...root.querySelectorAll('a[href]')].map(a => a.getAttribute('href'));
    return root.textContent.replace(/\s+/g, ' ').trim() + '\n' + links.join('\n');
  });
  return createHash('sha256').update(text).digest('hex');
}
