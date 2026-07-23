// Stop a phone throwing its on-screen keyboard up on every tap. xterm.js keeps a hidden textarea
// focused to receive keystrokes, and focusing a textarea is what tells a mobile browser to open the
// keyboard. inputmode="none" keeps the focus (and with it paste and IME) while telling the browser
// not to offer the keyboard; desktop browsers ignore it, because they have real keys.
(function () {
  var f = function () {
    document.querySelectorAll('.xterm-helper-textarea').forEach(function (t) {
      if (t.getAttribute('inputmode') !== 'none') {
        t.setAttribute('inputmode', 'none');
      }
    });
  };

  // The textarea is created by xterm.js after this runs, and again whenever the terminal is
  // rebuilt, so an observer sets the attribute rather than a one-off query.
  new MutationObserver(f).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener('DOMContentLoaded', f);
  f();
})();
