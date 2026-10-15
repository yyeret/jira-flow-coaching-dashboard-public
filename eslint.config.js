const prettier = require('eslint-config-prettier');

module.exports = [
  {
    ignores: [
      'node_modules/**',
      'dist/**',
      '.venv/**',
      'venv/**',
      'sample_data/**',
      'sprint_carryover_screenshot.png',
      'coverage/**',
      'test_*.js',
      'test.js',
      'value_dashboard.html',
      'epic_status_dashboard.html',
      'batch_results_*.json',
      'plans/**',
      '*.png',
    ],
  },
  {
    files: ['**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'commonjs',
      globals: {
        // Node globals
        process: 'readonly',
        __dirname: 'readonly',
        require: 'readonly',
        module: 'readonly',
        console: 'readonly',
        setTimeout: 'readonly',
        // Browser globals
        window: 'readonly',
        document: 'readonly',
        Event: 'readonly',
        Papa: 'readonly',
        Chart: 'readonly',
        applyDataToDashboard: 'readonly',
        localforage: 'readonly',
        ClipboardItem: 'readonly',
        alert: 'readonly',
        localStorage: 'readonly',
        getComputedStyle: 'readonly',
        navigator: 'readonly',
        fetch: 'readonly',
        // Jest globals
        jest: 'readonly',
        describe: 'readonly',
        test: 'readonly',
        it: 'readonly',
        expect: 'readonly',
        beforeEach: 'readonly',
        afterEach: 'readonly',
        beforeAll: 'readonly',
        afterAll: 'readonly',
      },
    },
    rules: {
      'no-unused-vars': 'warn',
      'no-undef': 'error',
    },
  },
  {
    files: ['js/**/*.js'],
    languageOptions: {
      sourceType: 'module',
    },
  },
  prettier,
];
