// The page's scripts, checked by something that reads JavaScript.
//
// These files used to be Python string literals, where a missing brace was invisible until the
// browser silently did less than it used to — no error, no failing test, just a feature quietly
// gone. Moving them to `.js` made that catchable; this is what does the catching.

const globals = require('globals');

// What Python fills in. Each is a bare identifier in the template, so without declaring them here
// `no-undef` would fire on every one — and, more usefully, declaring them means a placeholder that
// gets renamed on only one side is a lint error rather than a runtime `KeyError`.
const PLACEHOLDERS = [
  'cols',
  'rows',
  'touch_cols',
  'touch_rows',
  'cell_w',
  'cell_h',
  'min_font',
  'max_font',
  'back_keycode',
  'shift',
  'ctrl',
  'alt',
  'meta',
  'families',
];

module.exports = [
  {
    files: ['engine/termcade/web/*.js'],
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: 'script',
      globals: {
        ...globals.browser,
        ...Object.fromEntries(PLACEHOLDERS.map((name) => [`$${name}`, 'readonly'])),
      },
    },
    rules: {
      'no-undef': 'error',
      'no-unused-vars': ['error', { caughtErrors: 'none' }],
      // Swallowing is the point in several places: a browser that refuses `sessionStorage`, an
      // AudioBufferSource stopped twice. Every one of them is a path that must not take the page
      // down with it.
      'no-empty': ['error', { allowEmptyCatch: true }],
      eqeqeq: 'error',
      'no-implicit-globals': 'error',
    },
  },
];
