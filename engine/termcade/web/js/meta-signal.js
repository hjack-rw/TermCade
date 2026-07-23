// Listen for everything the app says to the page. Installed in <head>, because wrapping the
// WebSocket constructor after textual.js has already opened its socket is too late.
(function () {
  window.__tcMeta = window.__tcMeta || {};
  var W = window.WebSocket;

  window.WebSocket = function (u, p) {
    var s = p ? new W(u, p) : new W(u);
    s.addEventListener('message', function (e) {
      if (typeof e.data !== 'string') return;
      var m;
      try {
        m = JSON.parse(e.data);
      } catch (_) {
        return;
      }
      // What each message MEANS is not decided here: a packet is handed to whatever registered for
      // its type, so the Back button and the speaker each own their own behaviour and neither has
      // to know the other exists.
      var h = m && window.__tcMeta[m[0]];
      if (h) h(m[1]);
    });
    return s;
  };

  window.WebSocket.prototype = W.prototype;

  // The statics come across too. Only `prototype` did, which left `WebSocket.OPEN` and its siblings
  // undefined on the replaced global. The shipped textual.js reads none of them today — checked —
  // so this is not a bug being fixed but a trap being closed: the day upstream writes
  // `socket.readyState === WebSocket.OPEN`, that comparison silently becomes false forever and the
  // symptom is a game that connects and then does nothing.
  ['CONNECTING', 'OPEN', 'CLOSING', 'CLOSED'].forEach(function (state) {
    window.WebSocket[state] = W[state];
  });
})();
