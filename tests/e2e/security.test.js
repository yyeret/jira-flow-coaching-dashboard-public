const fs = require('fs');
const os = require('os');
const path = require('path');
const http = require('http');
const { URL } = require('url');
const Papa = require('papaparse');

const root = path.resolve(__dirname, '../..');
const publicRoot = path.join(root, 'dist');
const marker = 'SECURITY_PAYLOAD';
const payload = `${marker}<img src=x onerror="window.__xss=true"><svg onload="window.__xss=true">`;
let browser;
let server;
let origin;
let fixture;
let files;

beforeAll(async () => {
  fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'flow-security-'));
  files = fs
    .readdirSync(path.join(root, 'sample_data'))
    .filter((name) => name.endsWith('.csv'))
    .map((name) => {
      const source = fs.readFileSync(path.join(root, 'sample_data', name), 'utf8');
      const parsed = Papa.parse(source, { header: true, skipEmptyLines: true });
      for (const row of parsed.data) {
        for (const key of ['Summary', 'Parent Summary', 'Suggested Outcome Framing', 'Rationale']) {
          if (key in row) row[key] = payload;
        }
      }
      const target = path.join(fixture, name);
      fs.writeFileSync(target, Papa.unparse(parsed.data));
      return target;
    });
  server = http.createServer((req, res) => {
    const file = path.join(
      publicRoot,
      decodeURIComponent(new URL(req.url, 'http://localhost').pathname)
    );
    if (!file.startsWith(publicRoot + path.sep)) {
      res.writeHead(403).end();
      return;
    }
    fs.readFile(file, (error, bytes) => {
      if (error) {
        res.writeHead(404).end();
        return;
      }
      res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : 'text/html');
      res.end(bytes);
    });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  origin = `http://127.0.0.1:${server.address().port}`;
  const puppeteer = (await import('puppeteer')).default;
  browser = await puppeteer.launch({ headless: true });
});

afterAll(async () => {
  if (browser) await browser.close();
  if (server) await new Promise((resolve) => server.close(resolve));
  if (fixture) fs.rmSync(fixture, { recursive: true, force: true });
});

test.each(['index.html', 'value_dashboard.html', 'epic_status_dashboard.html'])(
  '%s renders malicious CSV as inert text and clears cached data',
  async (name) => {
    const context = await browser.createBrowserContext();
    const page = await context.newPage();
    try {
      await page.goto(`${origin}/${name}`, { waitUntil: 'networkidle0' });
      await page.waitForFunction(
        () => typeof Papa !== 'undefined' && typeof localforage !== 'undefined'
      );
      await page.evaluate(() =>
        document.getElementById('folderInput').removeAttribute('webkitdirectory')
      );
      const input = await page.$('#folderInput');
      await input.uploadFile(...files);
      await page.waitForFunction((text) => document.body.textContent.includes(text), {}, marker);
      expect(await page.evaluate(() => window.__xss)).toBeUndefined();
      expect(await page.$('img[src="x"]')).toBeNull();
      // Clearing data must complete before the new page is loaded.
      await page.evaluate(() => localforage.setItem('security-test', 'retained'));
      await Promise.all([
        page.waitForNavigation({ waitUntil: 'networkidle0' }),
        page.click('#clearSavedDataBtn'),
      ]);
      expect(await page.evaluate(() => localforage.length())).toBe(0);
      expect(
        await page.evaluate(() => document.body.textContent.includes('SECURITY_PAYLOAD'))
      ).toBe(false);
    } finally {
      await context.close();
    }
  }
);

test('AI consent gates requests, keys use headers, and model HTML remains inert', async () => {
  const context = await browser.createBrowserContext();
  const page = await context.newPage();
  let allowAi = false;
  const requests = [];
  page.on('dialog', (dialog) => {
    if (dialog.type() === 'confirm' && !allowAi) return dialog.dismiss();
    return dialog.accept();
  });
  await page.setRequestInterception(true);
  page.on('request', async (request) => {
    if (request.url().startsWith('https://generativelanguage.googleapis.com/')) {
      if (request.method() === 'OPTIONS') {
        return request.respond({
          status: 204,
          headers: {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST',
            'Access-Control-Allow-Headers': 'Content-Type, x-goog-api-key',
          },
        });
      }
      requests.push({ url: request.url(), headers: request.headers() });
      return request.respond({
        status: 200,
        contentType: 'application/json',
        headers: { 'Access-Control-Allow-Origin': '*' },
        body: JSON.stringify({ candidates: [{ content: { parts: [{ text: payload }] } }] }),
      });
    }
    return request.continue();
  });
  try {
    await page.goto(`${origin}/index.html`, { waitUntil: 'networkidle0' });
    await page.evaluate(() =>
      document.getElementById('folderInput').removeAttribute('webkitdirectory')
    );
    await (await page.$('#folderInput')).uploadFile(...files);
    await page.waitForFunction((text) => document.body.textContent.includes(text), {}, marker);
    await page.evaluate(() => {
      document.getElementById('geminiApiKeyInput').value = 'synthetic-test-key';
      document.getElementById('saveApiSettingsBtn').click();
    });
    expect(await page.evaluate(() => localStorage.getItem('geminiApiKey'))).toBeNull();
    await page.click('#cfdAiInsightBtn');
    expect(requests).toHaveLength(0);
    allowAi = true;
    await page.click('#cfdAiInsightBtn');
    await page.waitForFunction(
      (text) => document.getElementById('cfdAiInsightCard').textContent.includes(text),
      {},
      marker
    );
    expect(requests).toHaveLength(1);
    expect(requests[0].url).not.toContain('synthetic-test-key');
    expect(requests[0].headers['x-goog-api-key']).toBe('synthetic-test-key');
    expect(await page.$('#cfdAiInsightCard img')).toBeNull();
    expect(await page.evaluate(() => window.__xss)).toBeUndefined();
  } finally {
    await context.close();
  }
});
