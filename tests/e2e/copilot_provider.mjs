/** Read-only capture of the already-paid cached answer. Refuses a non-exhausted ledger. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const requireFrontend = createRequire(resolve(ROOT, 'frontend/package.json'));
const { chromium, expect } = requireFrontend('@playwright/test');
const baseURL = process.env.OILWELL_FRONTEND_URL || 'http://127.0.0.1:5173';
const smoke = JSON.parse(await readFile(resolve(ROOT, 'reports/copilot/provider_smoke.json'), 'utf8'));
const out = resolve(ROOT, 'reports/copilot/qa');
function reservedCalls() {
  const db = new DatabaseSync(resolve(ROOT, '.local/copilot/cache.sqlite3'), { readOnly: true });
  try { return db.prepare('SELECT calls FROM budget WHERE id=1').get().calls; }
  finally { db.close(); }
}
const before = reservedCalls();
assert.equal(before, 2, 'This capture is allowed only after the hard two-attempt budget is exhausted');
assert.equal(smoke.explanation.status, 'provider');
const result = { check: 'Cached live-provider answer displayed with exact usage and no new reservation', status: 'pending',
  replay_id: smoke.replay_id, sequence: smoke.sequence, reserved_before: before, paid_calls_by_this_capture: 0 };
const browser = await chromium.launch({ executablePath: process.env.OILWELL_BROWSER_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, timezoneId: 'Asia/Oral' });
const page = await context.newPage();
const errors = [], directProviderRequests = [], requests = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => {
  if (/api\.openai\.com/.test(request.url())) directProviderRequests.push(request.url());
  if (request.url().endsWith('/explanation')) requests.push(request.postDataJSON());
});
try {
  await page.goto(`${baseURL}/#replay`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByLabel('Replay session')).toBeVisible();
  await page.getByLabel('Replay session').selectOption(smoke.replay_id);
  const panel = page.locator('.copilot-panel');
  await expect(panel.getByLabel('Prediction to explain')).toBeVisible({ timeout: 20000 });
  await panel.getByLabel('Prediction to explain').selectOption(String(smoke.sequence));
  await panel.getByLabel('Question about this prediction').fill('show sensor trends');
  await panel.getByLabel('Use optional AI provider for this request').check();
  assert.equal(requests.length, 0, 'Typing/selecting cannot send a request');
  const pending = page.waitForResponse(response => response.url().endsWith('/explanation'));
  await panel.getByRole('button', { name: 'Explain alert', exact: true }).click();
  const response = await pending;
  assert.equal(response.status(), 200);
  const answer = await response.json();
  assert.equal(answer.status, 'provider');
  assert.equal(answer.cached, true);
  assert.equal(answer.reason, 'provider_selected');
  assert.equal(answer.provider_model, smoke.explanation.provider_model);
  assert.deepEqual(answer.usage, { input_tokens: 1331, output_tokens: 78 });
  assert.equal(answer.evidence_hash, smoke.explanation.evidence_hash);
  assert.deepEqual(answer.observations, smoke.explanation.observations);
  assert.deepEqual(answer.possible_interpretations, smoke.explanation.possible_interpretations);
  await expect(panel.locator('.copilot-result-meta')).toContainText('provider selected');
  await expect(panel.locator('.copilot-result-meta')).toContainText('cached');
  await expect(panel.locator('.copilot-result-meta')).toContainText(answer.provider_model);
  await expect(panel.locator('.copilot-result')).toContainText('AI selected from verified claims');
  assert.deepEqual(errors, []);
  assert.deepEqual(directProviderRequests, []);
  assert.deepEqual(requests, [{ question: 'show sensor trends', use_provider: true }]);
  const after = reservedCalls();
  assert.equal(after, before);
  await panel.screenshot({ path: resolve(out, 'copilot-provider-cached.png') });
  Object.assign(result, { status: 'passed', reserved_after: after, additional_reservations: after - before,
    cached: answer.cached, provider: answer.provider, provider_model: answer.provider_model, usage: answer.usage,
    evidence_hash: answer.evidence_hash, observations: answer.observations.length,
    interpretations: answer.possible_interpretations.length, browser_errors: errors,
    screenshot: 'reports/copilot/qa/copilot-provider-cached.png' });
  console.log('PASS cached real-provider response: 1331 input / 78 output tokens; zero new reservations');
} catch (error) {
  Object.assign(result, { status: 'failed', error: String(error), reserved_after: reservedCalls() });
  process.exitCode = 1;
  console.error(String(error));
} finally {
  await writeFile(resolve(out, 'provider_browser_results.json'), JSON.stringify(result, null, 2) + '\n');
  await context.close(); await browser.close();
}
