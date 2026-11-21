/*
 * Snowbound map: draws the valley on a canvas and turns mouse/keys into actions.
 *   SB.map.init(lobby, rt)  once; draws every animation frame from lobby.state.game
 *   SB.map.reset()          new game: forget decoded rows, center on the cabin
 *   SB.map.center()         center the view on the cabin
 * Rows (state.game.rows, see logic/world.py) are decoded into one pixel per lot on an
 * offscreen canvas, only for row strings that changed, then scaled up with smoothing off.
 * Crews are interpolated with rt.sample. Clicks: shovel a workable lot (snow, and reached or next
 * to a reached lot), catch the golden snowflake, or with Shift set your crews' target.
 * Shared global: window.SB (game.js adds the panels).
 */
(() => {
  const SB = (window.SB = window.SB || {});
  const { $ } = AppDom;
  const SNOW_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const LEVEL_BASE = 1.2;
  const REACHED = new Set([",", "X", "T", "H", "G", "C", "K"]);
  const GROUND = { ",": [74, 82, 92], X: [123, 74, 42], T: [47, 93, 58], H: [141, 90, 59], G: [192, 57, 43], C: [184, 134, 11], K: [230, 126, 34] };
  const HINT = { t: [94, 125, 102], h: [185, 162, 143], g: [217, 136, 128] };
  const FEATURE_NAMES = { ".": "Snow", ",": "Cleared", x: "Cabin", X: "Cabin", t: "Forest", T: "Forest (logs found)",
    h: "Buried cabin", H: "Dug-out cabin", g: "Gas station", G: "Gas station", C: "Supply cache", K: "Skier rescued" };

  const map = (SB.map = {});
  const view = { x: 0, y: 0, zoom: 12 };
  let lobby, rt, canvas, ctx;
  let w = 0, h = 0, levels = null, feats = null, snowRows = [], featRows = [];
  let off = null, offCtx = null, image = null, imageDirty = false;
  let hover = null, lastCursor = null, lastCursorSent = 0;
  let drag = null;
  const particles = [];
  const flakes = Array.from({ length: 160 }, () => ({ x: Math.random(), y: Math.random(), s: 0.5 + Math.random() }));
  const keys = new Set();

  const mix = (a, b, t) => [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * t));

  function lotColor(level, f) {
    if (REACHED.has(f)) {
      const ground = GROUND[f] || GROUND[","];
      return level ? mix(ground, [214, 225, 238], Math.min(1, 0.35 + level / 30)) : ground;
    }
    if (f === "x") return GROUND.X;
    let snow = mix([250, 252, 255], [160, 182, 210], Math.min(1, level / 52));
    if (HINT[f]) snow = mix(snow, HINT[f], 0.45);
    return snow;
  }

  function decode(game) {
    if (!game || !game.rows) return;
    if (game.w !== w || game.h !== h || !levels) {
      w = game.w; h = game.h;
      levels = new Uint8Array(w * h); feats = new Array(w * h).fill(".");
      snowRows = []; featRows = [];
      off = document.createElement("canvas"); off.width = w; off.height = h;
      offCtx = off.getContext("2d"); image = offCtx.createImageData(w, h);
    }
    for (let y = 0; y < h; y++) {
      const s = game.rows.snow[String(y)], f = game.rows.feat[String(y)];
      if (s === undefined || f === undefined || (s === snowRows[y] && f === featRows[y])) continue;
      snowRows[y] = s; featRows[y] = f;
      for (let x = 0; x < w; x++) {
        const i = y * w + x;
        levels[i] = SNOW_CHARS.indexOf(s[x]);
        feats[i] = f[x];
        const c = lotColor(levels[i], f[x]);
        const p = i * 4;
        image.data[p] = c[0]; image.data[p + 1] = c[1]; image.data[p + 2] = c[2]; image.data[p + 3] = 255;
      }
      imageDirty = true;
    }
  }

  const reached = (x, y) => x >= 0 && y >= 0 && x < w && y < h && REACHED.has(feats[y * w + x]);
  map.workable = (x, y) => {
    if (x < 0 || y < 0 || x >= w || y >= h || !levels[y * w + x]) return false;
    return reached(x, y) || reached(x + 1, y) || reached(x - 1, y) || reached(x, y + 1) || reached(x, y - 1);
  };
  map.lotInfo = (x, y) => {
    if (!levels || x < 0 || y < 0 || x >= w || y >= h) return null;
    const i = y * w + x, level = levels[i];
    const snow = level ? Math.pow(LEVEL_BASE, level - 1) : 0;
    return { x, y, snow, name: FEATURE_NAMES[feats[i]] || "Snow", workable: map.workable(x, y) };
  };

  function resize() {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const cw = Math.max(1, Math.round(rect.width * dpr)), ch = Math.max(1, Math.round(rect.height * dpr));
    if (canvas.width !== cw || canvas.height !== ch) { canvas.width = cw; canvas.height = ch; }
    return dpr;
  }

  const toScreen = (x, y) => [(x - view.x) * view.zoom + canvas.width / 2, (y - view.y) * view.zoom + canvas.height / 2];
  function toLot(ev) {
    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const sx = (ev.clientX - rect.left) * dpr, sy = (ev.clientY - rect.top) * dpr;
    return [Math.floor((sx - canvas.width / 2) / view.zoom + view.x), Math.floor((sy - canvas.height / 2) / view.zoom + view.y)];
  }

  function draw(now) {
    const state = lobby.state;
    if (!state || state.phase === "lobby" || !state.game || $("game").hidden) return;
    const game = state.game;
    decode(game);
    const dpr = resize();
    panKeys();
    const z = view.zoom;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = "#1b232c";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (imageDirty) { offCtx.putImageData(image, 0, 0); imageDirty = false; }
    ctx.imageSmoothingEnabled = false;
    const [ox, oy] = toScreen(0, 0);
    ctx.drawImage(off, ox, oy, w * z, h * z);
    const font = (px) => `${Math.round(px)}px system-ui, sans-serif`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";

    // Cabin.
    const [cx, cy] = toScreen(game.cabin[0] + 0.5, game.cabin[1] + 0.5);
    ctx.font = font(Math.max(16, z * 2.4));
    ctx.fillText(game.stove.lit ? "🏠" : "🏚️", cx, cy);
    if (game.stove.lit) {
      ctx.font = font(Math.max(10, z));
      ctx.fillText("🔥", cx + Math.max(10, z * 1.4), cy - Math.max(8, z));
    }

    // Focus flags and other players' cursors.
    for (const [pid, p] of Object.entries(game.players)) {
      if (p.focus) {
        const [fx, fy] = toScreen(p.focus[0] + 0.5, p.focus[1] + 0.5);
        ctx.font = font(Math.max(14, z * 1.4));
        ctx.fillText("🚩", fx, fy - Math.max(6, z * 0.5));
        ctx.fillStyle = p.color; ctx.fillRect(fx - 3, fy - 3, 6, 6);
      }
      if (p.cursor && pid !== state.you) {
        const [px, py] = toScreen(p.cursor[0], p.cursor[1]);
        ctx.strokeStyle = p.color; ctx.lineWidth = 2;
        ctx.strokeRect(px, py, Math.max(4, z), Math.max(4, z));
        ctx.fillStyle = p.color; ctx.font = font(11 * dpr); ctx.textAlign = "left";
        ctx.fillText(p.name, px + Math.max(4, z) + 3, py);
        ctx.textAlign = "center";
      }
    }

    // Golden snowflake.
    if (game.flake) {
      const [gx, gy] = toScreen(game.flake.x + 0.5, game.flake.y + 0.5);
      const pulse = 1 + 0.2 * Math.sin(now / 150);
      const r = Math.max(14, z * 1.6) * pulse;
      const glow = ctx.createRadialGradient(gx, gy, 0, gx, gy, r * 1.6);
      glow.addColorStop(0, "rgba(255,215,0,0.9)"); glow.addColorStop(1, "rgba(255,215,0,0)");
      ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(gx, gy, r * 1.6, 0, Math.PI * 2); ctx.fill();
      ctx.font = font(r * 1.3); ctx.fillStyle = "#fff"; ctx.fillText("❄️", gx, gy);
    }

    // Crews (interpolated).
    const crews = rt.sample((g) => (g && g.crews) || {});
    const defs = game.defs.machines;
    for (const c of Object.values(crews)) {
      const p = game.players[c.p];
      if (!p) continue;
      const [x, y] = toScreen(c.x + 0.5, c.y + 0.5);
      const r = Math.max(8, z * 0.8);
      ctx.fillStyle = p.color; ctx.globalAlpha = 0.85;
      ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
      ctx.globalAlpha = 1;
      ctx.font = font(r * 1.3);
      ctx.fillText(c.s === "stalled" ? "⛽" : (defs[c.m] ? defs[c.m].icon : "?"), x, y);
      if (c.n > 1 && r >= 9) {
        ctx.font = `bold ${font(Math.max(9, r * 0.7))}`;
        ctx.fillStyle = "#fff"; ctx.strokeStyle = "#000"; ctx.lineWidth = 3;
        ctx.strokeText(`×${c.n}`, x + r, y + r * 0.8); ctx.fillText(`×${c.n}`, x + r, y + r * 0.8);
      }
    }

    // Hover outline.
    if (hover) {
      const [hx, hy] = toScreen(hover[0], hover[1]);
      ctx.strokeStyle = map.workable(hover[0], hover[1]) ? "#ffffff" : "rgba(255,255,255,0.35)";
      ctx.lineWidth = 2; ctx.strokeRect(hx, hy, z, z);
    }

    // Click particles.
    ctx.font = `bold ${font(13 * dpr)}`;
    for (let k = particles.length - 1; k >= 0; k--) {
      const pt = particles[k], age = (now - pt.t) / 900;
      if (age >= 1) { particles.splice(k, 1); continue; }
      const [px, py] = toScreen(pt.x + 0.5, pt.y + 0.5);
      ctx.globalAlpha = 1 - age; ctx.fillStyle = "#fff"; ctx.strokeStyle = "#123"; ctx.lineWidth = 3;
      ctx.strokeText(pt.text, px, py - age * 40); ctx.fillText(pt.text, px, py - age * 40);
    }
    ctx.globalAlpha = 1;

    // Blizzard veil.
    if (game.weather.kind === "blizzard") {
      ctx.fillStyle = "rgba(235,242,250,0.18)"; ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      for (const f of flakes) {
        f.x = (f.x + 0.004 * f.s) % 1; f.y = (f.y + 0.003 * f.s) % 1;
        ctx.fillRect(f.x * canvas.width, f.y * canvas.height, 2 * f.s * dpr, 2 * f.s * dpr);
      }
    }
  }

  function panKeys() {
    const step = 12 / view.zoom;
    if (keys.has("left")) view.x -= step;
    if (keys.has("right")) view.x += step;
    if (keys.has("up")) view.y -= step;
    if (keys.has("down")) view.y += step;
  }

  function sendCursor(lot) {
    const key = lot ? lot.join(",") : "";
    const now = performance.now();
    if (key === lastCursor || now - lastCursorSent < 100) return;
    lastCursor = key; lastCursorSent = now;
    if (lobby.me()?.player) lobby.sendInput({ cursor: lot });
  }

  function clickLot(ev, [x, y]) {
    const game = lobby.state && lobby.state.game;
    if (!game || lobby.state.phase !== "playing" || !lobby.me()?.player) return;
    if (ev.shiftKey) {
      lobby.sendGame({ action: "focus", x, y });
      return;
    }
    const f = game.flake;
    if (f && (f.x - x) ** 2 + (f.y - y) ** 2 <= 2.5) {
      lobby.sendGame({ action: "flake", x: f.x, y: f.y });
      return;
    }
    if (!map.workable(x, y)) return;
    lobby.sendGame({ action: "click", x, y });
    const mine = lobby.state.private;
    if (mine && mine.click > 0) particles.push({ x, y, t: performance.now(), text: "+" + SB.fmt(mine.click) });
  }

  map.center = () => {
    const game = lobby.state && lobby.state.game;
    if (game) { view.x = game.cabin[0] + 0.5; view.y = game.cabin[1] + 0.5; }
  };
  map.reset = () => {
    levels = null; w = 0; h = 0; view.zoom = 12; hover = null; lastCursor = null; particles.length = 0;
    map.center();
  };

  map.init = (lobbyRef, rtRef) => {
    lobby = lobbyRef; rt = rtRef;
    canvas = $("map"); ctx = canvas.getContext("2d");
    canvas.addEventListener("contextmenu", (ev) => ev.preventDefault());
    canvas.addEventListener("mousedown", (ev) => {
      drag = { x: ev.clientX, y: ev.clientY, vx: view.x, vy: view.y, button: ev.button, moved: false };
    });
    window.addEventListener("mousemove", (ev) => {
      if (drag) {
        const dpr = window.devicePixelRatio || 1;
        const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y;
        if (Math.abs(dx) + Math.abs(dy) > 5) drag.moved = true;
        if (drag.moved) {
          view.x = drag.vx - (dx * dpr) / view.zoom;
          view.y = drag.vy - (dy * dpr) / view.zoom;
        }
      }
    });
    canvas.addEventListener("mousemove", (ev) => {
      const lot = toLot(ev);
      hover = lot;
      const info = map.lotInfo(lot[0], lot[1]);
      $("hover").textContent = info
        ? `(${info.x}, ${info.y}) ${info.name}${info.snow ? ` · ~${SB.fmt(info.snow)} snow` : ""}${info.workable ? " · click to shovel" : ""}`
        : "";
      sendCursor(info ? lot : null);
    });
    canvas.addEventListener("mouseleave", () => { hover = null; $("hover").textContent = ""; sendCursor(null); });
    window.addEventListener("mouseup", (ev) => {
      if (!drag) return;
      const d = drag;
      drag = null;
      if (!d.moved && d.button === 0 && ev.target === canvas) clickLot(ev, toLot(ev));
    });
    canvas.addEventListener("wheel", (ev) => {
      ev.preventDefault();
      const dpr = window.devicePixelRatio || 1;
      const rect = canvas.getBoundingClientRect();
      const sx = (ev.clientX - rect.left) * dpr, sy = (ev.clientY - rect.top) * dpr;
      const wx = (sx - canvas.width / 2) / view.zoom + view.x, wy = (sy - canvas.height / 2) / view.zoom + view.y;
      view.zoom = Math.max(1, Math.min(48, view.zoom * (ev.deltaY < 0 ? 1.2 : 1 / 1.2)));
      view.x = wx - (sx - canvas.width / 2) / view.zoom;
      view.y = wy - (sy - canvas.height / 2) / view.zoom;
    }, { passive: false });
    const KEYS = { KeyW: "up", ArrowUp: "up", KeyS: "down", ArrowDown: "down", KeyA: "left", ArrowLeft: "left", KeyD: "right", ArrowRight: "right" };
    window.addEventListener("keydown", (ev) => {
      const t = ev.target;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      if (KEYS[ev.code] && !$("game").hidden) { keys.add(KEYS[ev.code]); if (ev.code.startsWith("Arrow")) ev.preventDefault(); }
    });
    window.addEventListener("keyup", (ev) => { if (KEYS[ev.code]) keys.delete(KEYS[ev.code]); });
    window.addEventListener("blur", () => keys.clear());
    AppRealtime.loop(draw);
  };
})();
