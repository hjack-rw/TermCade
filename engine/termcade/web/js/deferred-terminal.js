// Load textual.js only once the fonts are in. xterm measures the cell and bakes a WebGL texture
// atlas the moment the terminal is constructed, so a font that finishes loading afterwards is never
// drawn with, however correct the stack is by then.
(function () {
  var go = function () {
    var s = document.createElement('script');

    // textual.js starts the terminal from window.onload. Injected late, it misses that event
    // entirely — the script loads, defines its handler, and nothing ever calls it, which shows up
    // as a page that renders no terminal at all and reports no error. So when the document has
    // already finished loading, we call the handler it just installed.
    s.onload = function () {
      if (document.readyState === 'complete' && typeof window.onload === 'function') {
        window.onload();
      }
    };

    // The Jinja expression is left intact: this replacement happens outside our {% raw %} block, so
    // the URL is still filled in by the template engine.
    s.src = '{{ config.static.url }}js/textual.js';
    document.head.appendChild(s);
  };

  // Degrades rather than blocks. A browser without document.fonts, a font that 404s, a request that
  // hangs — every path still ends in the terminal being loaded, because a game in the stock font
  // beats a game that never starts.
  if (!document.fonts) {
    go();
    return;
  }

  Promise.all([$families, document.fonts.load("16px 'Roboto Mono'")])
    .catch(function () {})
    .then(function () {
      return document.fonts.ready;
    })
    .catch(function () {})
    .then(go);
})();
