// Publish an explicit file list, never the repository root or local exports.
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'dist');
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out);
const files = [
  'index.html',
  'value_dashboard.html',
  'epic_status_dashboard.html',
  'flow_metrics.js',
  '_headers',
  'LICENSE',
  'js/app.js',
  'js/models.js',
  'js/metrics.js',
  'js/charts.js',
  'js/security.js',
];
const vendor = {
  'chart.umd.js': 'chart.js/dist/chart.umd.js',
  'chartjs-adapter-date-fns.bundle.min.js':
    'chartjs-adapter-date-fns/dist/chartjs-adapter-date-fns.bundle.min.js',
  'papaparse.min.js': 'papaparse/papaparse.min.js',
  'localforage.min.js': 'localforage/dist/localforage.min.js',
};
for (const name of files) {
  const target = path.join(out, name);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.copyFileSync(path.join(root, name), target);
}
fs.mkdirSync(path.join(out, 'vendor'));
for (const [name, source] of Object.entries(vendor)) {
  fs.copyFileSync(path.join(root, 'node_modules', source), path.join(out, 'vendor', name));
}
// Include the complete notices for bundled libraries, including transitive code.
const licenses = {
  'chart.js': 'LICENSE.md',
  '@kurkle/color': 'LICENSE.md',
  'chartjs-adapter-date-fns': 'LICENSE.md',
  'date-fns': 'LICENSE.md',
  papaparse: 'LICENSE',
  localforage: 'LICENSE',
  lie: 'license.md',
  immediate: 'LICENSE.txt',
};
let notices = '# Third-party browser libraries\n\nGenerated from the locked npm installation.\n';
for (const [name, license] of Object.entries(licenses)) {
  const dir = path.join(root, 'node_modules', name);
  const pkg = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'));
  notices += `\n## ${name} ${pkg.version}\n\n${fs.readFileSync(path.join(dir, license), 'utf8')}\n`;
}
fs.writeFileSync(path.join(out, 'THIRD_PARTY_NOTICES.txt'), notices);
console.log(
  `Built ${files.length} application files and ${Object.keys(vendor).length} pinned browser libraries in dist/`
);
