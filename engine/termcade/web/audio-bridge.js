// Play the game's sound in the browser, from samples the app sends down the meta channel. The game
// generates its own audio, so there is nothing to fetch and no asset to serve: raw PCM arrives in
// base64 chunks, is assembled into an AudioBuffer once, and is kept under the id the app gave it.
// The app never sends the same sound twice, which is why the cache is not optional — a music toggle
// replays what is already here.
(function () {
  var AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return;

  var ctx = null,
    music = null,
    pending = null,
    buf = {},
    part = {};

  // Nothing can play before a gesture: every browser refuses audio to a page the player has not
  // touched, and a phone refuses hardest. The listeners stay rather than firing once — a context
  // can fall back to 'suspended' when a phone is locked or the tab is backgrounded, and the next
  // tap has to be able to bring it round again. A loop that arrived before the first gesture is
  // remembered and started here, or the soundtrack (which starts on mount) would be lost every
  // time.
  var wake = function () {
    if (!ctx) ctx = new AC();
    if (ctx.state === 'suspended') ctx.resume();
    if (pending) {
      var p = pending;
      pending = null;
      loop(p);
    }
  };
  ['pointerdown', 'keydown', 'touchend'].forEach(function (e) {
    document.addEventListener(e, wake, { passive: true });
  });

  var decode = function (b64) {
    var s = atob(b64),
      n = s.length,
      b = new Uint8Array(n);
    for (var i = 0; i < n; i++) b[i] = s.charCodeAt(i);
    return b;
  };

  // int16 little-endian to the float -1..1 WebAudio wants.
  var buffer = function (bytes, rate) {
    var pcm = new Int16Array(bytes.buffer, 0, bytes.length >> 1);
    var a = ctx.createBuffer(1, pcm.length, rate),
      c = a.getChannelData(0);
    for (var i = 0; i < pcm.length; i++) c[i] = pcm[i] / 32768;
    return a;
  };

  // Mixing is the browser's: two sources on one destination sum, so an effect lands over the music
  // exactly as the engine's own Mixer does it at a terminal.
  var start = function (a, gain, looping) {
    var s = ctx.createBufferSource(),
      g = ctx.createGain();
    s.buffer = a;
    s.loop = looping;
    g.gain.value = gain;
    s.connect(g);
    g.connect(ctx.destination);
    s.start();
    return { src: s, gain: g };
  };

  var loop = function (m) {
    if (!ctx) {
      pending = m;
      return;
    }
    var a = buf[m.id];
    if (!a) {
      pending = m;
      return;
    }

    var t = ctx.currentTime,
      f = m.crossfade || 0;

    // A crossfade runs both loops for its length and drops the outgoing one at the end — the same
    // shape as the engine's Mixer.fade, because it is replacing the same thing.
    if (music && f > 0) {
      var old = music;
      old.gain.gain.setValueAtTime(old.gain.gain.value, t);
      old.gain.gain.linearRampToValueAtTime(0, t + f);
      old.src.stop(t + f);
      music = start(a, 0, true);
      music.gain.gain.setValueAtTime(0, t);
      music.gain.gain.linearRampToValueAtTime(m.gain, t + f);
      return;
    }

    if (music) {
      try {
        music.src.stop();
      } catch (_) {}
    }
    music = start(a, m.gain, true);
  };

  // Chunks are PLACED by their seq, not appended in arrival order. The socket delivers in order
  // today, which is exactly why appending looked correct — but the sender states a sequence number,
  // and a guarantee nobody checks is not a guarantee. Placing also makes a duplicate harmless
  // instead of corrupting the tune.
  var chunk = function (m) {
    var p = part[m.id] || (part[m.id] = { n: 0, total: m.total, a: [] });
    if (p.a[m.seq] === undefined) {
      p.a[m.seq] = m.data;
      p.n++;
    }
    if (p.n < p.total) return;
    delete part[m.id];

    // The context may not exist yet (no gesture). Keep the bytes; build the buffer on the way in
    // to loop(), which only ever runs once there is a context to build it with.
    var bytes = decode(p.a.join(''));
    var make = function () {
      buf[m.id] = buffer(bytes, m.rate);
    };
    if (ctx) {
      make();
      return;
    }

    var once = function () {
      if (!ctx) return;
      make();
      if (pending && pending.id === m.id) {
        var q = pending;
        pending = null;
        loop(q);
      }
      document.removeEventListener('pointerdown', once);
      document.removeEventListener('keydown', once);
      document.removeEventListener('touchend', once);
    };
    ['pointerdown', 'keydown', 'touchend'].forEach(function (e) {
      document.addEventListener(e, once, { passive: true });
    });
  };

  var handle = function (m) {
    if (m.action === 'chunk') {
      chunk(m);
      return;
    }
    if (m.action === 'loop') {
      loop(m);
      return;
    }
    if (m.action === 'once') {
      if (!ctx || !buf[m.id]) return;
      start(buf[m.id], m.gain, false);
      return;
    }
    if (m.action === 'stop') {
      if (music) {
        try {
          music.src.stop();
        } catch (_) {}
        music = null;
      }
      pending = null;
    }
  };

  window.__tcMeta = window.__tcMeta || {};
  window.__tcMeta['termcade_audio'] = handle;
})();
