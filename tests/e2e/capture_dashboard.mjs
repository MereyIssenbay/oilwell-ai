/** Read-only screenshot and chart-resize verification after the functional run. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const { chromium, expect } = createRequire(resolve(root, 'frontend/package.json'))('@playwright/test');
const output = resolve(root, 'reports/frontend/qa');
const result = JSON.parse(await readFile(resolve(output, 'results.json'), 'utf8'));
const baseURL = process.env.OILWELL_FRONTEND_URL || 'http://127.0.0.1:5173';
const browser = await chromium.launch({
  executablePath: process.env.OILWELL_BROWSER_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
  headless: true,
});
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, timezoneId: 'Asia/Oral' });
await context.addInitScript(id => localStorage.setItem('oilwell-replay-id', id), result.created_replay_id);
const page = await context.newPage();
const checks = [];
const dimensions = [];
const pageErrors = [];
page.on('pageerror', error => pageErrors.push(error.message));

async function readyCharts(name) {
  await expect(page.locator('.js-plotly-plot').first()).toBeVisible({ timeout: 15000 });
  for (const node of await page.locator('.js-plotly-plot').all()) {
    await expect.poll(async () => node.evaluate(element => Math.abs(element.clientWidth - (element._fullLayout?.width ?? -10000))),
      { timeout: 15000, message: `Plotly autosize matches current container on ${name}` }).toBeLessThanOrEqual(2);
    dimensions.push({ view: name, ...await node.evaluate(element => ({ container_width: element.clientWidth, plotly_width: element._fullLayout.width })) });
  }
}
async function capture(route, filename, { chart = false, comparison = false } = {}) {
  await page.locator(`nav a[href="#${route}"]`).click();
  await expect(page.locator('.replay-badge')).toBeVisible();
  assert.equal(/[\u00c2\u00c3\u0400-\u04ff]/u.test(await page.locator('body').innerText()), false);
  if (comparison) {
    const panel = page.locator('section.panel').filter({ has: page.getByRole('heading', { name: 'Predicted vs actual', exact: true }) });
    await expect(panel.locator('tbody tr')).toHaveCount(3);
  }
  if (chart) await readyCharts(filename);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
  await page.screenshot({ path: resolve(output, filename), fullPage: true });
  checks.push(filename);
}
try {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  await expect(page.getByLabel('Replay session')).toHaveValue(result.created_replay_id);
  await capture('overview', 'overview-desktop.png', { chart: true });
  await capture('replay', 'replay-unknown-normal-desktop.png', { chart: true, comparison: true });
  await capture('alerts', 'alerts-desktop.png');
  await capture('model', 'model-desktop.png');
  await page.setViewportSize({ width: 390, height: 844 });
  await capture('model', 'model-mobile.png');
  await capture('replay', 'replay-mobile.png', { chart: true, comparison: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await capture('overview', 'overview-desktop.png', { chart: true });
  assert.deepEqual(pageErrors, []);
  await writeFile(resolve(output, 'capture_results.json'), `${JSON.stringify({
    read_only: true, checks, dimensions, browser_exceptions: pageErrors,
    completed_at: new Date().toISOString(),
  }, null, 2)}\n`);
  console.log(JSON.stringify({ captures: checks.length, dimensions, errors: pageErrors }));
} finally {
  await context.close();
  await browser.close();
}
