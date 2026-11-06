/*
 * Real-time game helpers (for games built on gamekit/realtime.py). Load after lobby.js.
 *
 *   const lobby = AppLobby.connect("my-game", { onState, onError, onConnection });
 *   const rt = AppRealtime.attach(lobby, { delay });   // delay: ms behind the server (default 2 ticks)
 *
 *   rt.sample(pick)   Smooth positions for drawing. pick(game) returns {id: {x, y, ...}} from a
 *                     game state; sample returns the same shape at the render time, with every
 *                     number interpolated between the two snapshots around it (other fields
 *                     come from the newer one). Ids that just appeared aren't interpolated.
 *                     Before the first snapshot it returns pick(lobby.state.game).
 *   rt.ping           Round trip to the server in ms (null until measured). The server also
 *                     gets it (member.ping), so games can show everyone's ping.
 *   rt.controls(keyMap, { enabled })
 *                     Keyboard input: keyMap maps KeyboardEvent.code to an action name, e.g.
 *                     { KeyW: "up", ArrowUp: "up", ... }. Whenever the set of held actions
 *                     changes, sends lobby.sendInput({ keys: [...sorted actions] }). Ignores
 *                     typing in inputs (the chat), releases everything when the window loses
 *                     focus, and only acts while enabled() returns true (e.g. you're playing).
 *                     Returns { keys() } (the held actions).
 *   AppRealtime.loop(draw)   Calls draw(now) every animation frame; returns stop().
 *
 * Why the delay: snapshots arrive TICK_RATE times a second with some jitter. Drawing a little
 * in the past means there are (almost) always two snapshots to interpolate between, so motion
 * looks smooth at any frame rate. Everything you see, your own piece included, is `delay` plus
 * half a ping behind the server (client-side prediction can come later: snap.ack is the last
 * input the server applied).
 */
(() => {
  const PING_EVERY = 2000; // ms
  const KEEP = 2000; // ms of snapshots kept

  function attach(lobby, options = {}) {
    let buffer = []; // { t: server ms, game } oldest first
    let offset = null; // local time - server time, estimated from snapshot arrivals
    let gameNumber = null;
    let ping = null;

    lobby.on("state", (state) => {
      if (state.gameNumber !== gameNumber || state.phase === "lobby") {
        gameNumber = state.gameNumber;
        buffer = [];
      }
    });

    lobby.on("snap", (snap) => {
      const now = performance.now();
      const sample = now - snap.t;
      // Adopt faster arrivals at once; let the estimate drift up slowly after slower ones.
      if (offset === null || sample < offset) offset = sample;
      else offset += (sample - offset) * 0.05;
      buffer.push({ t: snap.t, game: lobby.state.game });
      while (buffer.length > 2 && buffer[0].t < snap.t - KEEP) buffer.shift();
    });

    lobby.on("pong", (pong) => {
      if (typeof pong.t === "number") ping = Math.round(performance.now() - pong.t);
    });
    const sendPing = () => lobby.send({ type: "ping", t: performance.now(), rtt: ping });
    setInterval(sendPing, PING_EVERY);
    setTimeout(sendPing, 300);

    function delay() {
      if (options.delay != null) return options.delay;
      return 2 * (1000 / (lobby.state?.tickRate || 20));
    }

    function lerpItem(a, b, f) {
      const out = { ...b };
      for (const key of Object.keys(b)) {
        if (typeof b[key] === "number" && typeof a[key] === "number") out[key] = a[key] + (b[key] - a[key]) * f;
      }
      return out;
    }

    function sample(pick) {
      if (buffer.length === 0) return lobby.state?.game ? pick(lobby.state.game) || {} : {};
      const renderTime = performance.now() - offset - delay();
      let i = buffer.length - 1;
      while (i > 0 && buffer[i].t > renderTime) i--;
      const older = buffer[i];
      const newer = buffer[i + 1];
      if (!newer || renderTime <= older.t) return pick(older.game) || {};
      const f = (renderTime - older.t) / (newer.t - older.t);
      const a = pick(older.game) || {};
      const b = pick(newer.game) || {};
      const out = {};
      for (const [id, item] of Object.entries(b)) {
        out[id] = a[id] && typeof item === "object" ? lerpItem(a[id], item, f) : item;
      }
      return out;
    }

    function controls(keyMap, { enabled = () => true } = {}) {
      const held = new Set(); // KeyboardEvent.code
      let lastSent = "";

      const keys = () => [...new Set([...held].map((code) => keyMap[code]))].sort();
      function sync() {
        const now = keys();
        const text = now.join(",");
        if (text === lastSent) return;
        lastSent = text;
        lobby.sendInput({ keys: now });
      }
      function typing(target) {
        return target instanceof HTMLElement &&
          (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));
      }

      window.addEventListener("keydown", (event) => {
        if (!(event.code in keyMap) || typing(event.target) || !enabled()) return;
        event.preventDefault(); // arrows and space would scroll the page
        if (event.repeat) return;
        held.add(event.code);
        sync();
      });
      window.addEventListener("keyup", (event) => {
        if (!held.delete(event.code)) return;
        sync();
      });
      window.addEventListener("blur", () => {
        held.clear();
        sync();
      });
      return { keys };
    }

    return {
      sample,
      controls,
      get ping() {
        return ping;
      },
    };
  }

  function loop(draw) {
    let stopped = false;
    function frame(now) {
      if (stopped) return;
      try {
        draw(now);
      } catch (error) {
        console.error(error);
      }
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
    return () => {
      stopped = true;
    };
  }

  window.AppRealtime = { attach, loop };
})();
