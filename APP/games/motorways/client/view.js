/*
 * Metro Lanes view: the full-screen canvas. The whole city fits the window (between the HUD boxes).
 *   ML.view.init(lobby, rt)   once; draws every animation frame
 *   ML.view.reset()           new game
 *   ML.view.toTile(clientX, clientY) -> [x, y] in tile units (floats; Math.floor for the tile)
 *   ML.view.owners            show who built each road (thin stripe in their colour); O toggles it
 * Draw order: terrain -> outside the city limits (shaded) -> roads (links, bridges, tunnels, owner
 * stripes, driveways) -> roundabouts and lights -> houses, shops (pins, timer ring)
 * -> cars (interpolated by rt.sample) -> "+1" pops -> ML.input's preview -> other players' cursors.
 */
(() => {
  const ML = (window.ML = window.ML || {});
  const { $ } = AppDom;
  const C = { land: "#f2eee4", landOut: "#d9d4c8", water: "#9ccbe8", mountain: "#c8b59a", peak: "#a8927a",
              road: "#6c717a", bridge: "#8a6b4b", tunnel: "#4a4f57", grid: "rgba(0,0,0,0.035)" };
  const SIDE = { N: [0, -1], S: [0, 1], E: [1, 0], W: [-1, 0] };
  const MARGIN = { left: 16, right: 240, top: 60, bottom: 84 };

  const view = (ML.view = { owners: true });
  let lobby, rt, canvas, ctx;
  let z = 20, ox = 0, oy = 0;
  const headings = new Map();   // car id -> {x, y, a: heading, t: road tile it last reached}
  // "+1" pops: a car reaching the middle of a road tile scores 1 for its builder (the server credits
  // it as the car moves on, logic/traffic.py); shown here in the builder's colour. Purely visual.
  const POP_LIFE = 800, POP_CORE = 0.3, MAX_POPS = 150;
  let pops = [];                 // {x, y, color, born}

  const dpr = () => window.devicePixelRatio || 1;
  const cx = (t) => (t % lobby.state.game.w + 0.5) * z + ox;
  const cy = (t) => (Math.floor(t / lobby.state.game.w) + 0.5) * z + oy;

  view.toTile = (clientX, clientY) => {
    const rect = canvas.getBoundingClientRect();
    return [((clientX - rect.left) * dpr() - ox) / z, ((clientY - rect.top) * dpr() - oy) / z];
  };
  view.reset = () => { headings.clear(); pops = []; };

  function layout(game) {
    const d = dpr();
    const w = Math.round(canvas.clientWidth * d), h = Math.round(canvas.clientHeight * d);
    if (canvas.width !== w) canvas.width = w;
    if (canvas.height !== h) canvas.height = h;
    const aw = w - (MARGIN.left + MARGIN.right) * d, ah = h - (MARGIN.top + MARGIN.bottom) * d;
    z = Math.max(4, Math.min(aw / game.w, ah / game.h));
    ox = MARGIN.left * d + (aw - game.w * z) / 2;
    oy = MARGIN.top * d + (ah - game.h * z) / 2;
  }

  function drawTerrain(game) {
    const a = game.area;
    for (let y = 0; y < game.h; y++) {
      const row = game.rows[y];
      for (let x = 0; x < game.w; x++) {
        const ter = row[x], inside = x >= a[0] && x <= a[2] && y >= a[1] && y <= a[3];
        ctx.fillStyle = ter === "~" ? C.water : ter === "^" ? C.mountain : inside ? C.land : C.landOut;
        ctx.fillRect(ox + x * z, oy + y * z, z + 0.5, z + 0.5);
        if (ter === "^") {
          ctx.fillStyle = C.peak;
          ctx.beginPath();
          ctx.moveTo(ox + (x + 0.15) * z, oy + (y + 0.8) * z);
          ctx.lineTo(ox + (x + 0.5) * z, oy + (y + 0.2) * z);
          ctx.lineTo(ox + (x + 0.85) * z, oy + (y + 0.8) * z);
          ctx.fill();
        }
      }
    }
    // Subtle grid inside the city limits, then shade everything outside them.
    ctx.strokeStyle = C.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let x = a[0]; x <= a[2] + 1; x++) { ctx.moveTo(ox + x * z, oy + a[1] * z); ctx.lineTo(ox + x * z, oy + (a[3] + 1) * z); }
    for (let y = a[1]; y <= a[3] + 1; y++) { ctx.moveTo(ox + a[0] * z, oy + y * z); ctx.lineTo(ox + (a[2] + 1) * z, oy + y * z); }
    ctx.stroke();
    ctx.fillStyle = "rgba(40,44,52,0.28)";
    ctx.beginPath();
    ctx.rect(ox, oy, game.w * z, game.h * z);
    ctx.rect(ox + a[0] * z, oy + a[1] * z, (a[2] - a[0] + 1) * z, (a[3] - a[1] + 1) * z);
    ctx.fill("evenodd");
    ctx.strokeStyle = "rgba(40,44,52,0.5)";
    ctx.setLineDash([z * 0.3, z * 0.2]);
    ctx.strokeRect(ox + a[0] * z, oy + a[1] * z, (a[2] - a[0] + 1) * z, (a[3] - a[1] + 1) * z);
    ctx.setLineDash([]);
  }

  function line(a, b, color, width, dash) {
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    if (dash) ctx.setLineDash(dash);
    ctx.beginPath(); ctx.moveTo(cx(a), cy(a)); ctx.lineTo(cx(b), cy(b)); ctx.stroke();
    if (dash) ctx.setLineDash([]);
  }

  function drawRoads(game) {
    const players = game.players;
    ctx.lineCap = "round";
    const pairs = Object.keys(game.links).map((k) => k.split(",").map(Number));
    const kindOf = (a, b) => { const ra = game.roads[a], rb = game.roads[b]; return ra.k !== "r" ? ra.k : rb.k; };
    // Driveways: building node -> its door, when the door has a road.
    const drive = [];
    for (const h of Object.values(game.houses)) if (game.roads[h.door]) drive.push([h.t, h.door]);
    for (const s of Object.values(game.shops)) if (game.roads[s.door]) drive.push([s.node, s.door]);
    for (const [a, b] of pairs) {
      const k = kindOf(a, b);
      if (k === "b") line(a, b, C.bridge, z * 0.78);
    }
    for (const [a, b] of [...pairs, ...drive]) line(a, b, C.road, z * 0.56);
    for (const [a, b] of pairs) if (kindOf(a, b) === "t") line(a, b, C.tunnel, z * 0.56, [z * 0.25, z * 0.15]);
    ctx.fillStyle = C.road;
    for (const t of Object.keys(game.roads)) {
      if (game.roads[t].k !== "r") continue;
      ctx.beginPath(); ctx.arc(cx(+t), cy(+t), z * 0.28, 0, Math.PI * 2); ctx.fill();
    }
    if (view.owners) {
      // Each half of a link in the colour of the player who built the tile at that end.
      ctx.lineCap = "butt";
      const color = (t) => (players[game.roads[t].o] || {}).color || "#999";
      for (const [a, b] of pairs) {
        const mx = (cx(a) + cx(b)) / 2, my = (cy(a) + cy(b)) / 2;
        for (const [t, ex, ey] of [[a, mx, my], [b, mx, my]]) {
          ctx.strokeStyle = color(t); ctx.lineWidth = z * 0.09;
          ctx.beginPath(); ctx.moveTo(cx(t), cy(t)); ctx.lineTo(ex, ey); ctx.stroke();
        }
      }
      for (const t of Object.keys(game.roads)) {
        ctx.fillStyle = color(t);
        ctx.beginPath(); ctx.arc(cx(+t), cy(+t), z * 0.07, 0, Math.PI * 2); ctx.fill();
      }
      ctx.lineCap = "round";
    }
    // Roundabouts and traffic lights.
    for (const [t, r] of Object.entries(game.roads)) {
      if (!r.f) continue;
      const x = cx(+t), y = cy(+t);
      if (r.f === "roundabout") {
        ctx.fillStyle = C.road; ctx.beginPath(); ctx.arc(x, y, z * 0.48, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = "#7fb069"; ctx.beginPath(); ctx.arc(x, y, z * 0.2, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = "#fff"; ctx.lineWidth = Math.max(1, z * 0.05);
        ctx.beginPath(); ctx.arc(x, y, z * 0.34, 0, Math.PI * 2); ctx.stroke();
      } else {
        ctx.fillStyle = "#2b2f36"; ctx.fillRect(x - z * 0.14, y - z * 0.26, z * 0.28, z * 0.52);
        const h = game.light === "h";
        ctx.fillStyle = h ? "#3ad06b" : "#ff5a4e"; ctx.beginPath(); ctx.arc(x, y - z * 0.12, z * 0.08, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = h ? "#ff5a4e" : "#3ad06b"; ctx.beginPath(); ctx.arc(x, y + z * 0.12, z * 0.08, 0, Math.PI * 2); ctx.fill();
      }
    }
  }

  function roundRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.roundRect ? ctx.roundRect(x, y, w, h, r) : ctx.rect(x, y, w, h);
  }

  function stub(node, side) {
    const [dx, dy] = SIDE[side];
    ctx.strokeStyle = C.road; ctx.lineWidth = z * 0.4; ctx.lineCap = "butt";
    ctx.beginPath(); ctx.moveTo(cx(node), cy(node)); ctx.lineTo(cx(node) + dx * z * 0.75, cy(node) + dy * z * 0.75); ctx.stroke();
  }

  function drawBuildings(game, now) {
    const colors = game.colors;
    for (const h of Object.values(game.houses)) {
      const [hx, hy] = ML.city.xy(h.t);
      const side = Object.keys(SIDE).find((s) => ML.city.idx(hx + SIDE[s][0], hy + SIDE[s][1]) === h.door);
      stub(h.t, side);
      const x = ox + hx * z, y = oy + hy * z;
      ctx.fillStyle = colors[h.c];
      roundRect(x + z * 0.14, y + z * 0.14, z * 0.72, z * 0.72, z * 0.12); ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      for (let k = 0; k < h.home; k++) { ctx.beginPath(); ctx.arc(x + z * (0.37 + k * 0.26), y + z * 0.5, z * 0.09, 0, Math.PI * 2); ctx.fill(); }
    }
    for (const s of Object.values(game.shops)) {
      const [sx, sy] = ML.city.xy(s.t), [nx, ny] = ML.city.xy(s.node);
      const side = Object.keys(SIDE).find((k) => ML.city.idx(nx + SIDE[k][0], ny + SIDE[k][1]) === s.door);
      stub(s.node, side);
      const x = ox + sx * z, y = oy + sy * z;
      if (s.timer > 0) {
        // Overflow timer: a ring that fills up, pulsing when it's nearly full.
        const pulse = s.timer > 0.6 ? 0.5 + 0.5 * Math.sin(now / 120) : 1;
        ctx.strokeStyle = `rgba(220,40,40,${0.35 + 0.5 * pulse})`; ctx.lineWidth = z * 0.22;
        ctx.beginPath(); ctx.arc(x + z, y + z, z * 1.35, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * s.timer); ctx.stroke();
      }
      ctx.fillStyle = colors[s.c];
      roundRect(x + z * 0.08, y + z * 0.08, z * 1.84, z * 1.84, z * 0.25); ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.25)";
      roundRect(x + z * 0.2, y + z * 0.2, z * 1.6, z * 1.6, z * 0.18); ctx.fill();
      // Pins: up to 12 in a 4 x 3 grid; the ones past fullPins are red.
      for (let k = 0; k < s.pins; k++) {
        const px = x + z * (0.45 + (k % 4) * 0.37), py = y + z * (0.55 + Math.floor(k / 4) * 0.45);
        ctx.fillStyle = k >= game.fullPins - 1 ? "#b3261e" : "#ffffff";
        ctx.beginPath(); ctx.arc(px, py, z * 0.13, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = "rgba(0,0,0,0.35)"; ctx.lineWidth = 1; ctx.stroke();
      }
      for (let k = 0; k < Math.min(4, s.parked); k++) {
        ctx.fillStyle = "rgba(0,0,0,0.35)";
        ctx.fillRect(x + z * (0.3 + k * 0.38), y + z * 1.62, z * 0.26, z * 0.16);
      }
    }
  }

  function drawCars(game, now) {
    const cars = rt.sample((g) => g.cars) || {};
    for (const [id, c] of Object.entries(cars)) {
      const prev = headings.get(id);
      let a = prev ? prev.a : 0;
      if (prev && Math.hypot(c.x - prev.x, c.y - prev.y) > 0.01) a = Math.atan2(c.y - prev.y, c.x - prev.x);
      // The tile whose middle the car is in (none while between tiles, so diagonals don't clip corners).
      const tx = Math.floor(c.x), ty = Math.floor(c.y);
      const inCore = Math.abs(c.x - tx - 0.5) < POP_CORE && Math.abs(c.y - ty - 0.5) < POP_CORE;
      const t = inCore && ML.city.onMap(tx, ty) ? ML.city.idx(tx, ty) : (prev ? prev.t : null);
      if (prev && t !== prev.t && t !== null) {
        const road = ML.city.road(t), owner = road && game.players[road.o];
        if (owner && pops.length < MAX_POPS) pops.push({ x: tx + 0.5, y: ty + 0.35, color: owner.color, born: now });
      }
      headings.set(id, { x: c.x, y: c.y, a, t });
      ctx.save();
      ctx.translate(ox + c.x * z, oy + c.y * z);
      ctx.rotate(a);
      ctx.fillStyle = game.colors[c.c];
      roundRect(-z * 0.19, -z * 0.11, z * 0.38, z * 0.22, z * 0.06); ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.6)";
      ctx.fillRect(z * 0.06, -z * 0.08, z * 0.07, z * 0.16);
      ctx.restore();
    }
    if (headings.size > 400) for (const id of headings.keys()) if (!cars[id]) headings.delete(id);
  }

  function drawPops(now) {
    pops = pops.filter((p) => now - p.born < POP_LIFE);
    if (!pops.length) return;
    ctx.font = `bold ${Math.max(9, Math.round(z * 0.36))}px system-ui, sans-serif`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.lineWidth = Math.max(1.5, z * 0.08);
    ctx.strokeStyle = "rgba(255,255,255,0.85)";
    for (const p of pops) {
      const f = (now - p.born) / POP_LIFE;
      const x = ox + p.x * z, y = oy + (p.y - f * 0.6) * z;
      ctx.globalAlpha = f < 0.6 ? 1 : (1 - f) / 0.4;
      ctx.strokeText("+1", x, y);
      ctx.fillStyle = p.color;
      ctx.fillText("+1", x, y);
    }
    ctx.globalAlpha = 1;
  }

  function drawPreview(game) {
    const p = ML.input.preview();
    if (!p) return;
    if (p.tile !== null && p.tile !== undefined) {
      const [x, y] = ML.city.xy(p.tile);
      ctx.strokeStyle = p.ok === false ? "rgba(200,40,40,0.8)" : "rgba(40,40,40,0.55)";
      ctx.lineWidth = Math.max(1, z * 0.06);
      ctx.strokeRect(ox + x * z + 1, oy + y * z + 1, z - 2, z - 2);
    }
    ctx.lineCap = "round";
    for (const [a, b] of p.pending || []) line(a, b, "rgba(108,113,122,0.6)", z * 0.56);
  }

  function drawCursors(game) {
    ctx.font = `${Math.round(11 * dpr())}px system-ui, sans-serif`;
    ctx.textAlign = "left"; ctx.textBaseline = "top";
    for (const [pid, p] of Object.entries(game.players)) {
      if (pid === lobby.state.you || !p.cur) continue;
      const x = ox + p.cur[0] * z, y = oy + p.cur[1] * z;
      ctx.fillStyle = p.color;
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + 11 * dpr(), y + 4 * dpr()); ctx.lineTo(x + 4 * dpr(), y + 11 * dpr()); ctx.fill();
      ctx.fillText(p.name, x + 10 * dpr(), y + 10 * dpr());
    }
  }

  view.init = (lobbyRef, rtRef) => {
    lobby = lobbyRef; rt = rtRef;
    canvas = $("map");
    ctx = canvas.getContext("2d");
    AppRealtime.loop((now) => {
      const state = lobby.state;
      if (!state || state.phase === "lobby" || !state.game || $("game").hidden) return;
      const game = state.game;
      ML.city.update(game);
      layout(game);
      ctx.fillStyle = "#2b2f36";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      drawTerrain(game);
      drawRoads(game);
      drawBuildings(game, now);
      drawCars(game, now);
      drawPops(now);
      drawPreview(game);
      drawCursors(game);
    });
  };
})();
