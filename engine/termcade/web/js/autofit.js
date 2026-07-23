// Pick the largest xterm font that fits the game's grid in this window, and reload with
// ?fontsize=N when that is not the size already in the URL. Runs first, in <head>.
(function () {
  var p = new URLSearchParams(location.search);

  // A touch device fits a DIFFERENT grid when the cartridge offers one. A phone is short — 312px
  // of height against a laptop's 800 — so fitting the desktop's row count means shrinking the font
  // until it is unreadable.
  var touch = window.matchMedia('(pointer: coarse)').matches;
  var c = touch ? $touch_cols : $cols;
  var r = touch ? $touch_rows : $rows;

  var a = Math.floor(window.innerWidth / (c * $cell_w));
  var b = Math.floor(window.innerHeight / (r * $cell_h));
  var f = Math.max($min_font, Math.min(a, b, $max_font));

  // The reload costs a session, so it must not be able to happen twice for one shape. The viewport
  // it last replaced for is remembered, and a disagreement it has already acted on is left alone —
  // otherwise a browser whose reported height changes as its chrome slides away could bounce
  // between two sizes forever, reloading the game each time.
  var current = parseInt(p.get('fontsize'), 10);
  var shape = window.innerWidth + 'x' + window.innerHeight;
  var settled = null;
  try {
    settled = sessionStorage.getItem('tcFit');
  } catch (e) {}

  if (current !== f && settled !== shape) {
    try {
      sessionStorage.setItem('tcFit', shape);
    } catch (e) {}
    p.set('fontsize', f);
    location.replace(location.pathname + '?' + p.toString());
  }
})();
