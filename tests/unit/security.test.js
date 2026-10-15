const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.join(__dirname, '../..');
const security = fs.readFileSync(path.join(root, 'js/security.js'), 'utf8');
const app = fs.readFileSync(path.join(root, 'js/app.js'), 'utf8');
const payload = '\"><img src=x onerror=alert(1)><svg onload=alert(2)> & \' ';

function loadSecurity(extra = '') {
  const context = vm.createContext({ window: { confirm: () => false } });
  vm.runInContext(security.replace(/export /g, '') + extra, context);
  return context;
}

test('HTML escaping protects text and quoted attribute contexts', () => {
  const context = loadSecurity();
  const escaped = context.escapeHtml(payload);
  expect(escaped).not.toMatch(/[<>"']/);
  expect(escaped).toContain('&lt;img');
  expect(escaped).toContain('&amp;');
});

test('model output is rendered as text without assigning HTML', () => {
  const context = loadSecurity();
  const element = { style: {} };
  Object.defineProperty(element, 'innerHTML', {
    set() {
      throw new Error('Unsafe HTML sink');
    },
  });
  context.renderUntrustedText(element, payload);
  expect(element.textContent).toBe(payload);
  expect(element.style.whiteSpace).toBe('pre-wrap');
});

test('declining AI consent returns false', () => {
  expect(loadSecurity().confirmAiTransfer()).toBe(false);
});

test('data table escapes malicious Jira summaries, types, status and keys', () => {
  const table = { innerHTML: '' };
  const context = vm.createContext({
    window: { addEventListener() {} },
    document: { getElementById: () => table },
    localStorage: { removeItem() {} },
  });
  const code =
    security.replace(/export /g, '') +
    app.replace(/^import [\s\S]*? from ['"][^'"]+['"];\s*/gm, '');
  vm.runInContext(code, context);
  context.renderDataTable(
    [
      {
        key: payload,
        summary: payload,
        type: payload,
        currentStatus: payload,
        created: null,
        updated: null,
        transitions: {},
      },
    ],
    'Started',
    'Done'
  );
  expect(table.innerHTML).not.toContain('<img');
  expect(table.innerHTML).not.toContain('<svg');
  expect(table.innerHTML).toContain('&lt;img');
  expect(table.innerHTML).toContain(encodeURIComponent(payload));
});

test('Gemini credentials cannot regress to persistent storage or URL parameters', () => {
  expect(app).not.toMatch(/localStorage\.(?:getItem|setItem)\('geminiApiKey'/);
  expect(app).not.toContain('generateContent?key=');
  expect(app.match(/'x-goog-api-key': apiKey/g)).toHaveLength(2);
});
