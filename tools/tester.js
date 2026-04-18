/* ══════════════════════════════════════════════
   WAR ROOM — PLAYWRIGHT AUTO-TESTER
   After every builder run, visits the preview URL
   in a headless browser to capture console errors
   and take a screenshot. Replaces the 5-second
   client-side capture with immediate server-side results.
   ══════════════════════════════════════════════ */

let _chromium = null;

function getChromium() {
  if (_chromium) return _chromium;
  try {
    _chromium = require('playwright').chromium;
    return _chromium;
  } catch {
    return null; // playwright not installed — degrade gracefully
  }
}

async function testBuild(previewUrl) {
  const chromium = getChromium();
  if (!chromium) return { errors: [], screenshot: null, skipped: true };

  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text().slice(0, 200));
    });
    page.on('pageerror', err => {
      errors.push(err.message.slice(0, 200));
    });

    await page.goto(previewUrl, { waitUntil: 'domcontentloaded', timeout: 10000 });
    // Wait for JS simulations to kick off (setInterval, mounted(), RAF)
    await page.waitForTimeout(2500);

    const screenshot = await page.screenshot({ type: 'jpeg', quality: 72 });
    const uniqueErrors = [...new Set(errors)].slice(0, 10);

    return { errors: uniqueErrors, screenshot, skipped: false };
  } catch (err) {
    return { errors: [`Page load failed: ${err.message.slice(0, 150)}`], screenshot: null, skipped: false };
  } finally {
    if (browser) await browser.close();
  }
}

module.exports = { testBuild };
