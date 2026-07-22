// Turn finger drags into the events the app already understands: wheels down, arrows across.
// xterm.js reports mouse buttons and wheels; a touch drag is neither, so the Rules book and the
// Game Log simply would not move.
(function () {
  var y = null,
    x = null,
    moved = 0,
    swiped = false;

  var key = function (name, code) {
    var t = document.querySelector('.xterm-helper-textarea');
    if (!t) return;
    t.focus();
    ['keydown', 'keyup'].forEach(function (k) {
      t.dispatchEvent(
        new KeyboardEvent(k, {
          key: name,
          code: name,
          keyCode: code,
          which: code,
          bubbles: true,
        }),
      );
    });
  };

  document.addEventListener(
    'touchstart',
    function (e) {
      y = e.touches[0].clientY;
      x = e.touches[0].clientX;
      moved = 0;
      swiped = false;
    },
    { passive: true },
  );

  document.addEventListener(
    'touchmove',
    function (e) {
      if (y === null) return;
      var ny = e.touches[0].clientY,
        nx = e.touches[0].clientX;
      var d = y - ny,
        ax = nx - x;

      // A swipe fires ONCE per gesture, and only when it is clearly sideways — a finger travelling
      // twice as far across as down. Otherwise a diagonal scroll would turn pages while the reader
      // was trying to move down one. The page follows the finger: dragging it away leftwards is
      // Right, the next page.
      if (!swiped && Math.abs(ax) > 48 && Math.abs(ax) > Math.abs(ny - y) * 2) {
        swiped = true;
        if (ax < 0) key('ArrowRight', 39);
        else key('ArrowLeft', 37);
        return;
      }
      if (swiped) return;

      // The 24px travel threshold is not cosmetic. xterm turns a wheel into an ESC-prefixed sequence,
      // and Textual reads a stray ESC as the Escape key — so a tap that wobbled a couple of pixels
      // sent Escape, and on the temple that means leaving for the main menu.
      moved += Math.abs(d);
      if (moved < 24 || Math.abs(d) < 3) return;

      var t = document.querySelector('.xterm-screen') || document.body;
      t.dispatchEvent(new WheelEvent('wheel', { deltaY: d * 2, bubbles: true, cancelable: true }));
      y = ny;
    },
    { passive: true },
  );

  document.addEventListener(
    'touchend',
    function () {
      y = null;
      x = null;
      moved = 0;
      swiped = false;
    },
    { passive: true },
  );
})();
