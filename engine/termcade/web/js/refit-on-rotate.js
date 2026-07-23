// Make the terminal re-fit when a phone is turned. textual.js fits the grid from window.onresize
// and nothing else, and the resize that follows a rotation arrives while the browser is still
// settling the new viewport — so the fit measures the OLD dimensions and keeps them.
(function () {
  // Touch only. A desktop window already re-fits continuously while it is dragged, and
  // visualViewport fires on zoom there — so this would add refits to a platform that never needed
  // them and was not asked about.
  if (!window.matchMedia('(pointer: coarse)').matches) return;

  var kick = function () {
    window.dispatchEvent(new Event('resize'));
  };

  // Kicked several times over a second rather than once: there is no event for "the viewport has
  // finished changing", and iOS in particular reports intermediate sizes mid-rotation. Re-fitting
  // an already-correct grid costs nothing, so the cheap answer is to ask more than once.
  var settle = function () {
    [60, 250, 600, 1000].forEach(function (d) {
      setTimeout(kick, d);
    });
  };

  window.addEventListener('orientationchange', settle);
  if (window.screen && window.screen.orientation) {
    window.screen.orientation.addEventListener('change', settle);
  }
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', settle);
  }
})();
