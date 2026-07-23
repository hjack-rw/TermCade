// The Back button's behaviour. Its markup and its styling are the page's; what it SENDS is the
// app's, so every key value here is filled in from Python and pinned to EngineScreen.BACK_KEY.
(function () {
  var b = document.getElementById('tc-back-fab');

  window.__tcMeta = window.__tcMeta || {};
  window.__tcMeta['termcade_back'] = function (m) {
    b.hidden = !m.allowed;
  };

  // Only the typeface is borrowed from the terminal — the colours are the button's own, so it stays
  // a piece of the cabinet whatever theme the game is drawing in.
  var paint = function () {
    var t = document.querySelector('.xterm');
    if (!t) return;
    b.style.fontFamily = getComputedStyle(t).fontFamily;
  };
  setTimeout(paint, 600);
  setTimeout(paint, 2500);

  b.addEventListener('click', function (e) {
    e.preventDefault();
    var t = document.querySelector('.xterm-helper-textarea');
    if (!t) return;
    t.focus();

    // Hidden until the app says the next screen has a way back too. That is not the guard — the
    // guard is in the app — but it stops a fast finger queueing presses down a channel whose answer
    // is a round trip away.
    b.hidden = true;

    ['keydown', 'keyup'].forEach(function (k) {
      t.dispatchEvent(
        new KeyboardEvent(k, {
          key: '$back_key',
          code: '$back_code',
          shiftKey: $shift,
          ctrlKey: $ctrl,
          altKey: $alt,
          metaKey: $meta,
          keyCode: $back_keycode,
          which: $back_keycode,
          bubbles: true,
        }),
      );
    });
  });
})();
