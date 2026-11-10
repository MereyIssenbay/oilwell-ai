/** Independent browser acceptance against the real local dashboard/API.
 * Run from repository root: node tests/e2e/dashboard.mjs
 * Browser fixtures below are limited to explicit network failure injection.
 */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(fileURLToPath(new URL('../..', import.meta.url)));
const requireFrontend = createRequire(resolve(ROOT, 'frontend/package.json'));
const { chromium, expect } = requireFrontend('@playwright/test');
const baseURL = process.env.OILWELL_FRONTEND_URL || 'http://127.0.0.1:5173';
const browserPath = process.env.OILWELL_BROWSER_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const output = resolve(ROOT, 'reports/frontend/qa');
await mkdir(output, { recursive: true });
const results = { base_url: baseURL, browser: 'installed Chrome', checks: [], failures: [], screenshots: [] };
const browser = await chromium.launch({ executablePath: browserPath, headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, timezoneId: 'Asia/Oral' });
const page = await context.newPage();
const pageErrors = [];
page.on('pageerror', error => pageErrors.push(error.message));

async function check(name, action) {
  try {
    await action();
    results.checks.push({ name, status: 'passed' });
    console.log(`PASS ${name}`);
  } catch (error) {
    results.failures.push({ name, error: String(error) });
    console.error(`FAIL ${name}: ${error}`);
  }
}

async function screenshot(name) {
  const path = resolve(output, name);
  await page.screenshot({ path, fullPage: true });
  results.screenshots.push(`reports/frontend/qa/${name}`);
}

const routes = [
  ['overview', 'Overview'], ['wells', 'Wells & Sensor Explorer'], ['replay', 'Historical Replay'],
  ['alerts', 'Alerts & Event History'], ['model', 'Model Information'],
];
const apiGet = async path => {
  const response = await context.request.get(`${baseURL}/api${path}`);
  assert.equal(response.status(), 200, `GET ${path}`);
  return response.json();
};
async function navigate(route) {
  await page.locator(`nav a[href="#${route}"]`).click();
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(routes.find(r => r[0] === route)[1]);
}
function panel(title) {
  return page.locator('section.panel').filter({ has: page.getByRole('heading', { name: title, exact: true }) });
}
let ownedReplay;
let stoppedReplay;
try {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  const wells = await apiGet('/wells');
  const model = await apiGet('/models/info');
  await check('Overview counts come from real registered catalog', async () => {
    await expect(page.locator('.stat').filter({ hasText: 'Registered wells' }).locator('strong')).toHaveText(String(wells.items.length));
    await expect(page.locator('.stat').filter({ hasText: 'Sensor channels' }).locator('strong')).toHaveText(String(model.sensor_names.length));
  });
  for (const [route, title] of routes) {
    await check(`${title}: route, historical badge and diagnostic disclosure`, async () => {
      await navigate(route);
      await expect(page.locator('.replay-badge')).toHaveText('Historical Replay');
      await expect(page.locator('.diagnostic-banner')).toContainText('rejected for monitoring');
      assert.equal(/[\u00c2\u00c3\u0400-\u04ff]/u.test(await page.locator('body').innerText()), false, 'Visible English UI contains mojibake');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
    });
  }
  await check('Model identity and threshold match real endpoint', async () => {
    await expect(page.locator('.model-details')).toContainText(model.model_version);
    await expect(page.locator('.model-details')).toContainText(String(model.threshold));
    await expect(page.locator('.model-details')).toContainText(model.preprocessor_fingerprint);
  });
  await screenshot('model-desktop.png');
  await navigate('wells');
  await check('Real telemetry chart renders source timestamps without local timezone shift', async () => {
    await page.getByLabel('Well', { exact: true }).selectOption('WELL-00011');
    await page.getByLabel('Sensor', { exact: true }).selectOption('P-PDG');
    await expect(panel('Sensor explorer').locator('.js-plotly-plot')).toBeVisible({ timeout: 20000 });
    const sid = await page.getByLabel('Dataset instance', { exact: true }).inputValue();
    const original = await apiGet(`/wells/WELL-00011/telemetry?source_instance_id=${encodeURIComponent(sid)}&limit=600`);
    await expect.poll(async () => panel('Sensor explorer').locator('.js-plotly-plot').evaluate(node => node.data?.[0]?.x?.[0]), { timeout: 15000 }).toBe(original.items[0].timestamp);
    const trace = await panel('Sensor explorer').locator('.js-plotly-plot').evaluate(node => ({ x: node.data[0].x, y: node.data[0].y, connectgaps: node.data[0].connectgaps }));
    assert.deepEqual(trace.x, original.items.map(row => row.timestamp));
    assert.deepEqual(trace.y, original.items.map(row => row.sensors['P-PDG']));
    assert.equal(trace.connectgaps, false);
    assert.equal(/[\u00c2\u00c3\u0400-\u04ff]/u.test((await page.locator('svg text').allTextContents()).join(' ')), false, 'Plot labels contain mojibake');
  });
  await screenshot('explorer-desktop.png');
  const oldDemo = JSON.parse(await readFile(resolve(ROOT, 'reports/replay/demo.json'), 'utf8'));
  await navigate('replay');
  await check('Existing real normal/transient replay comparison matches persisted endpoint', async () => {
    await expect(page.getByLabel('Replay session')).toBeVisible();
    await page.getByLabel('Replay session').selectOption(oldDemo.replay_id);
    const comparison = await apiGet(`/replays/${oldDemo.replay_id}/evaluation?limit=100`);
    await expect(panel('Predicted vs actual').locator('tbody tr')).toHaveCount(comparison.items.length, { timeout: 20000 });
    for (const row of comparison.items) {
      const visible = panel('Predicted vs actual').locator('tbody tr').filter({ hasText: `Row ${row.source_position}` });
      await expect(visible).toContainText(row.timestamp.replace('T', ' '));
      await expect(visible).toContainText(row.actual_event_name.replaceAll('_', ' '));
      await expect(visible).toContainText(row.decision_matches ? 'match' : 'mismatch');
    }
    await expect(page.locator('.prediction-card')).toContainText('Selected-class confidence');
    await expect(page.locator('.prediction-card')).toContainText('uncalibrated');
    const retained = await apiGet(`/replays/${oldDemo.replay_id}/event-history?limit=1000`);
    const latest = retained.items.filter(e => e.event_type === 'prediction').at(-1).payload;
    await expect(page.locator('.confidence')).toHaveText(`${(latest.prediction.confidence * 100).toFixed(2)}%`);
  });
  await screenshot('replay-completed-desktop.png');
  await check('UI creates and controls a real bounded replay, reloads and reconnects', async () => {
    const active = (await apiGet('/replays')).items.filter(s => ['created', 'running', 'paused'].includes(s.state));
    assert.equal(active.length, 0, 'Another owner has an active replay; do not interrupt it');
    await page.getByLabel('Well', { exact: true }).selectOption('WELL-00011');
    await page.getByLabel('Dataset instance', { exact: true }).selectOption(oldDemo.source_instance_id);
    await page.getByLabel('Start row', { exact: true }).fill('3540');
    await page.getByLabel('End row', { exact: true }).fill('3619');
    await page.getByLabel('Replay speed', { exact: true }).selectOption('20');
    const createdResponse = page.waitForResponse(r => r.url().endsWith('/api/replays') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Create replay', exact: true }).click();
    const created = await createdResponse;
    assert.equal(created.status(), 201);
    ownedReplay = (await created.json()).replay_id;
    results.created_replay_id = ownedReplay;
    await expect(page.getByLabel('Replay session')).toHaveValue(ownedReplay);
    await page.getByRole('button', { name: /Start$/ }).click();
    await expect.poll(async () => (await apiGet(`/replays/${ownedReplay}`)).cursor_position, { timeout: 20000 }).toBeGreaterThanOrEqual(3542);
    await page.getByRole('button', { name: /Pause$/ }).click();
    await expect.poll(async () => (await apiGet(`/replays/${ownedReplay}`)).state).toBe('paused');
    const paused = await apiGet(`/replays/${ownedReplay}`);
    await page.waitForTimeout(350);
    assert.equal((await apiGet(`/replays/${ownedReplay}`)).cursor_position, paused.cursor_position);
    const denied = await context.request.get(`${baseURL}/api/replays/${ownedReplay}/evaluation`);
    assert.equal(denied.status(), 409);
    await expect(panel('Predicted vs actual')).toContainText('available only after this replay completes');
    await page.getByLabel('Playback speed', { exact: true }).selectOption('10');
    await page.getByRole('button', { name: 'Apply speed', exact: true }).click();
    await expect.poll(async () => (await apiGet(`/replays/${ownedReplay}`)).speed_multiplier).toBe(10);
    await page.getByLabel('Playback speed', { exact: true }).selectOption('20');
    await page.getByRole('button', { name: 'Apply speed', exact: true }).click();
    await expect.poll(async () => (await apiGet(`/replays/${ownedReplay}`)).speed_multiplier).toBe(20);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(page.getByLabel('Replay session')).toHaveValue(ownedReplay);
    await expect(page.getByRole('button', { name: /Resume$/ })).toBeEnabled();
    await page.getByRole('button', { name: /Resume$/ }).click();
    await expect.poll(async () => (await apiGet(`/replays/${ownedReplay}`)).state).toBe('running');
    await context.setOffline(true);
    await page.waitForTimeout(1800);
    await context.setOffline(false);
    await expect.poll(async () => (await apiGet(`/replays/${ownedReplay}`)).state, { timeout: 90000, intervals: [300, 500] }).toBe('completed');
    const evaluation = await apiGet(`/replays/${ownedReplay}/evaluation`);
    assert.deepEqual(evaluation.items.map(r => r.source_position), [3599, 3609, 3619]);
    assert.equal(evaluation.items[0].actual_binary, null);
    assert.equal(evaluation.items[0].decision_matches, null);
    await expect(panel('Predicted vs actual').locator('tbody tr')).toHaveCount(3, { timeout: 15000 });
    await expect(page.getByLabel('Replay session').locator('option:checked')).toContainText('completed');
    await expect(panel('Predicted vs actual').locator('tbody tr').first()).toContainText('Unknown label');
    await expect(panel('Predicted vs actual').locator('tbody tr').first()).toContainText('unavailable');
    await expect(panel('Sensor telemetry')).toContainText('80 retained readings', { timeout: 15000 });
    const history = await apiGet(`/replays/${ownedReplay}/event-history?limit=1000`);
    const latest = history.items.filter(e => e.event_type === 'prediction').at(-1).payload;
    await expect(page.locator('.prediction-card')).toContainText(`Row ${latest.source_position}`);
    results.replay_evidence = { replay_id: ownedReplay, source_rows: 80, predictions: evaluation.items.length, unknown_label_preserved: true, terminal_sequence: history.items.at(-1).sequence };
  });
  await screenshot('replay-unknown-normal-desktop.png');
  await check('UI Stop is terminal, preserves cursor and withholds retrospective labels', async () => {
    await page.getByLabel('Well', { exact: true }).selectOption('WELL-00011');
    await page.getByLabel('Dataset instance', { exact: true }).selectOption(oldDemo.source_instance_id);
    await page.getByLabel('Start row', { exact: true }).fill('0');
    await page.getByLabel('End row', { exact: true }).fill('29');
    const createdResponse = page.waitForResponse(r => r.url().endsWith('/api/replays') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Create replay', exact: true }).click();
    const response = await createdResponse;
    assert.equal(response.status(), 201);
    stoppedReplay = (await response.json()).replay_id;
    results.stopped_replay_id = stoppedReplay;
    await expect(page.getByLabel('Replay session')).toHaveValue(stoppedReplay);
    await page.getByRole('button', { name: /Start$/ }).click();
    await expect.poll(async () => (await apiGet(`/replays/${stoppedReplay}`)).cursor_position).toBeGreaterThanOrEqual(0);
    await page.getByRole('button', { name: /Stop$/ }).click();
    await expect.poll(async () => (await apiGet(`/replays/${stoppedReplay}`)).state).toBe('stopped');
    const first = await apiGet(`/replays/${stoppedReplay}`);
    await page.waitForTimeout(500);
    assert.deepEqual(await apiGet(`/replays/${stoppedReplay}`), first);
    await expect(page.getByRole('button', { name: /Start$/ })).toBeDisabled();
    await expect(page.getByRole('button', { name: /Resume$/ })).toBeDisabled();
    await expect(page.getByRole('button', { name: /Stop$/ })).toBeDisabled();
    assert.equal((await context.request.get(`${baseURL}/api/replays/${stoppedReplay}/evaluation`)).status(), 409);
    await expect(panel('Predicted vs actual')).toContainText('available only after this replay completes');
    const history = await apiGet(`/replays/${stoppedReplay}/event-history?limit=1000`);
    assert.equal(history.items.filter(e => e.event_type === 'prediction').length, 0);
    results.stop_evidence = { state: first.state, cursor_position: first.cursor_position, prediction_count: 0, evaluation_status: 409 };
    await page.getByLabel('Replay session').selectOption(ownedReplay);
    await expect(panel('Predicted vs actual').locator('tbody tr')).toHaveCount(3, { timeout: 15000 });
  });
  await check('Alerts and timeline use exact persisted episodes, without counting updates as new alerts', async () => {
    await navigate('alerts');
    const rid = ownedReplay || oldDemo.replay_id;
    const history = await apiGet(`/replays/${rid}/event-history?limit=1000`);
    const episodes = history.items.filter(e => e.event_type === 'alert_episode');
    const openings = episodes.filter(e => e.payload.transition === 'opened');
    await expect(page.locator('.stat').filter({ hasText: 'Openings in retained window' }).locator('strong')).toHaveText(String(openings.length));
    await expect(panel('Replay episode history').locator('tbody tr')).toHaveCount(episodes.length);
    assert.equal(await page.locator('.timeline-row').count(), Math.min(100, history.items.length));
    await expect(panel('Replay episode history')).toContainText('not physical risk');
    await expect(panel('Synchronous diagnostic detections')).toContainText('not replay episodes');
  });
  await screenshot('alerts-desktop.png');
  await check('Mobile routes stay within viewport and retain accessible controls and badge', async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    for (const [route] of routes) {
      await navigate(route);
      await expect(page.locator('.replay-badge')).toBeVisible();
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `Horizontal body overflow on ${route}`);
    }
    await screenshot('model-mobile.png');
    await navigate('replay');
    await expect(panel('Predicted vs actual').locator('tbody tr')).toHaveCount(3, { timeout: 15000 });
    await expect(panel('Sensor telemetry').locator('.js-plotly-plot')).toBeVisible();
    await screenshot('replay-mobile.png');
  });
  await check('Explicit loading, network error and retry restore actual catalog', async () => {
    const failureContext = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const failurePage = await failureContext.newPage();
    let fail = true;
    await failurePage.route('**/api/wells?*', async route => {
      if (fail) { await new Promise(resolve => setTimeout(resolve, 600)); await route.abort('failed'); }
      else await route.continue();
    });
    await failurePage.goto(baseURL, { waitUntil: 'domcontentloaded' });
    await expect(failurePage.getByRole('status')).toBeVisible();
    await expect(failurePage.getByRole('alert')).toContainText('Backend connection unavailable');
    fail = false;
    await failurePage.getByRole('button', { name: 'Retry', exact: true }).click();
    await expect(failurePage.locator('.stat').filter({ hasText: 'Registered wells' }).locator('strong')).toHaveText(String(wells.items.length));
    await expect(failurePage.getByRole('alert')).toHaveCount(0);
    await failureContext.close();
  });
  await navigate('overview');
  await page.setViewportSize({ width: 1440, height: 1000 });
  await expect(panel('Sensor telemetry').locator('.js-plotly-plot')).toBeVisible();
  await screenshot('overview-desktop.png');
  await check('No uncaught browser exceptions', async () => assert.deepEqual(pageErrors, []));
} finally {
  for (const cleanupId of [ownedReplay, stoppedReplay].filter(Boolean)) {
    const response = await context.request.get(`${baseURL}/api/replays/${cleanupId}`);
    if (response.ok()) {
      const value = await response.json();
      if (['created', 'running', 'paused'].includes(value.state)) {
        await context.request.post(`${baseURL}/api/replays/${cleanupId}/commands`, {
          headers: { 'Idempotency-Key': `qa-cleanup-${Date.now()}` },
          data: { command: 'stop', expected_version: value.version },
        });
      }
    }
  }
  results.completed_at = new Date().toISOString();
  results.passed = results.checks.length;
  results.failed = results.failures.length;
  await writeFile(resolve(output, 'results.json'), `${JSON.stringify(results, null, 2)}\n`);
  await context.close();
  await browser.close();
}
if (results.failed) process.exitCode = 1;
