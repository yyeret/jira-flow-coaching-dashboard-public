describe('Dashboard E2E Tests', () => {
  let browser;
  let page;
  let puppeteer;

  beforeAll(async () => {
    puppeteer = (await import('puppeteer')).default;
    // Launch puppeteer in headless mode
    browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox'],
    });
    page = await browser.newPage();
  });

  afterAll(async () => {
    if (browser) {
      await browser.close();
    }
  });

  it('should load the dashboard and verify the title', async () => {
    const path = require('path');
    const filePath = `file://${path.resolve(__dirname, '../../dist/index.html')}`;
    await page.goto(filePath);

    // Check the title or a specific header to ensure the app is loaded
    const title = await page.title();
    expect(title).toMatch(/Flow Analytics Dashboard/i);

    // Verify the drag and drop zone is present
    const uploadZoneExists = await page.evaluate(() => {
      return document.getElementById('uploadZone') !== null;
    });
    expect(uploadZoneExists).toBe(true);
  });

  it('should have the AI Settings modal and all chart-level AI Insight buttons', async () => {
    const path = require('path');
    const filePath = `file://${path.resolve(__dirname, '../../dist/index.html')}`;
    await page.goto(filePath);

    // Verify API Settings modal exists
    const modalExists = await page.evaluate(() => {
      return document.getElementById('apiSettingsModal') !== null;
    });
    expect(modalExists).toBe(true);

    // Verify AI settings input and model select exist
    const inputExists = await page.evaluate(() => {
      return (
        document.getElementById('geminiApiKeyInput') !== null &&
        document.getElementById('geminiModelSelect') !== null
      );
    });
    expect(inputExists).toBe(true);

    // Verify CFD AI Insight button exists
    const cfdBtnExists = await page.evaluate(() => {
      return document.getElementById('cfdAiInsightBtn') !== null;
    });
    expect(cfdBtnExists).toBe(true);

    // Verify Control Chart AI Insight button exists
    const controlBtnExists = await page.evaluate(() => {
      return document.getElementById('controlAiInsightBtn') !== null;
    });
    expect(controlBtnExists).toBe(true);

    // Verify Carryover AI Insight button exists
    const carryoverBtnExists = await page.evaluate(() => {
      return document.getElementById('carryoverAiInsightBtn') !== null;
    });
    expect(carryoverBtnExists).toBe(true);
  });

  it('should load the value dashboard and verify the title', async () => {
    const path = require('path');
    const filePath = `file://${path.resolve(__dirname, '../../dist/value_dashboard.html')}`;
    await page.goto(filePath);

    // Check the title
    const title = await page.title();
    expect(title).toMatch(/Value & Outcome Coaching Dashboard/i);

    // Verify the drag and drop zone is present
    const uploadZoneExists = await page.evaluate(() => {
      return document.getElementById('uploadZone') !== null;
    });
    expect(uploadZoneExists).toBe(true);
  });
});
