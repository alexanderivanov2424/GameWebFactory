/*
 * Canvas drawing (TILE = 16 px per cell). Needs grid.js; reads DC.lobby / DC.rt (set by game.js),
 * DC.view {overlay, hover, drag} and DC.tools (preview) from tools.js.
 * The static cell layer is redrawn into an offscreen canvas only when the grid rows or the
 * overlay change; every frame blits it and draws buildings, orders (with non-default priority numbers), items, colonists, cursors.
 *   DC.render.TILE, DC.render.OVERLAYS (list), DC.render.catColor(category)
 */
(() => {
  const DC = (window.DC = window.DC || {});
  const TILE = 16;
  const OVERLAYS = ["none", "gas", "temp", "germ", "decor", "power", "plumbing"];
  const CAT_COLORS = { base: "#8a7f6a", oxygen: "#4cc6d8", power: "#e0b030", food: "#8cc152",
    plumbing: "#4a8fe0", climate: "#e8734a", decor: "#c47ad8" };
  const catColor = (c) => CAT_COLORS[c] || "#999999";
  const canvas = document.getElementById("map");
  const ctx = canvas.getContext("2d");
  const base = document.createElement("canvas");
  const bctx = base.getContext("2d");
  const rgbCache = {};
  let baseKey = "";
  let occ = null, occFor = null; // {layer: Map(cell index -> building id)}

  const rgb = (hex) => (rgbCache[hex] ||= [parseInt(hex.slice(1, 3), 16) || 0, parseInt(hex.slice(3, 5), 16) || 0,
    parseInt(hex.slice(5, 7), 16) || 0]);
  const hash = (x, y) => { let n = (x * 374761393 + y * 668265263) | 0; n = (n ^ (n >>> 13)) * 1274126177; return ((n ^ (n >>> 16)) >>> 0) / 4294967295; };
  const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
  const abbrev = (name) => {
    const words = name.split(/[\s-]+/).filter(Boolean);
    return words.length > 1 ? words.map((w) => w[0]).join("").slice(0, 3).toUpperCase() : name.slice(0, 3);
  };

  function cellColor(overlay, x, y, e, mass) {
    const [r, g, b] = rgb(e.color);
    if (overlay === "gas") {
      if (e.phase !== "gas") return e.phase === "vacuum" ? "#05070a" : "#222831";
      return `rgba(${r},${g},${b},${0.15 + 0.8 * mass / 9})`;
    }
    if (overlay === "temp") {
      const t = DC.grid.tempAt(x, y);
      if (t === null) return "#05070a";
      return `hsl(${240 - 240 * clamp((t + 20) / 120, 0, 1)},80%,45%)`;
    }
    if (overlay === "germ") {
      const v = DC.grid.germAt(x, y);
      return v === 0 ? "#1a1f27" : `rgb(${20},${60 + 20 * v},${30})`;
    }
    if (overlay === "decor") {
      const d = DC.grid.decorAt(x, y);
      const t = clamp(Math.abs(d) / 20, 0, 1);
      return d < 0 ? `rgb(${60 + 160 * t},${50},${50})` : d > 0 ? `rgb(${50},${60 + 150 * t},${60})` : "#2a2f38";
    }
    return null;
  }

  function drawBase(game) {
    const { w, h } = DC.grid;
    const overlay = DC.view.overlay;
    base.width = w * TILE; base.height = h * TILE;
    const grid = DC.grid, defs = grid.defs;
    for (let y = 0; y < h; y++) {
      const els = grid.el[y];
      if (!els) continue;
      for (let x = 0; x < w; x++) {
        const e = defs.elements[defs.order[els[x]]];
        const px = x * TILE, py = y * TILE;
        const mass = grid.mass[y] ? grid.mass[y][x] : 0;
        const ov = cellColor(overlay, x, y, e, mass);
        if (ov) { bctx.fillStyle = ov; bctx.fillRect(px, py, TILE, TILE); continue; }
        if (e.phase === "vacuum") { bctx.fillStyle = "#05070a"; bctx.fillRect(px, py, TILE, TILE); continue; }
        if (e.phase === "gas") {
          bctx.fillStyle = "#0b0e14"; bctx.fillRect(px, py, TILE, TILE);
          if (mass > 0) {
            const [r, g, b] = rgb(e.color);
            bctx.fillStyle = `rgba(${r},${g},${b},${0.04 + 0.3 * mass / 9})`;
            bctx.fillRect(px, py, TILE, TILE);
          }
        } else if (e.phase === "liquid") {
          bctx.fillStyle = "#0b0e14"; bctx.fillRect(px, py, TILE, TILE);
          const fh = Math.max(2, Math.round(TILE * (mass + 1) / 10));
          bctx.fillStyle = e.color; bctx.fillRect(px, py + TILE - fh, TILE, fh);
        } else {
          const [r, g, b] = rgb(e.color);
          const s = (hash(x, y) - 0.5) * 24;
          bctx.fillStyle = `rgb(${clamp(r + s, 0, 255) | 0},${clamp(g + s, 0, 255) | 0},${clamp(b + s, 0, 255) | 0})`;
          bctx.fillRect(px, py, TILE, TILE);
        }
      }
    }
    if (overlay === "power" || overlay === "plumbing") {
      bctx.fillStyle = "rgba(0,0,0,0.6)"; bctx.fillRect(0, 0, w * TILE, h * TILE);
    }
  }

  function occupancy(game) {
    if (occFor === game.buildings) return occ;
    occFor = game.buildings;
    occ = { main: new Map(), pipe: new Map(), wire: new Map() };
    const w = DC.grid.w;
    for (const [id, b] of Object.entries(game.buildings)) {
      const d = game.defs.buildings[b.t];
      if (!d || !b.b) continue; // unfinished sites are ghosts (drawBuilding), not connected lines
      const map = occ[d.layer || "main"] || occ.main;
      for (let dy = 0; dy < d.h; dy++) for (let dx = 0; dx < d.w; dx++) map.set((b.y + dy) * w + b.x + dx, id);
    }
    return occ;
  }

  function relevant(overlay, d) {
    if (overlay === "power") return d.layer === "wire" || Boolean(Object.keys(d.power || {}).length || d.powerPort);
    if (overlay === "plumbing") return d.layer === "pipe" || Boolean(d.pipeIn || d.pipeOut);
    return true;
  }

  function drawLines(game, layer, color) {
    const o = occupancy(game)[layer];
    const w = DC.grid.w;
    ctx.strokeStyle = color; ctx.lineWidth = 3; ctx.lineCap = "round";
    ctx.beginPath();
    for (const i of o.keys()) {
      const x = i % w, y = (i / w) | 0;
      const cx = x * TILE + TILE / 2, cy = y * TILE + TILE / 2;
      ctx.moveTo(cx, cy); ctx.lineTo(cx + 0.1, cy);
      if (o.has(i + 1) && x + 1 < w) { ctx.moveTo(cx, cy); ctx.lineTo(cx + TILE, cy); }
      if (o.has(i + w)) { ctx.moveTo(cx, cy); ctx.lineTo(cx, cy + TILE); }
    }
    ctx.stroke();
  }

  function drawBuilding(game, id, b, d, overlay, players) {
    const px = b.x * TILE, py = b.y * TILE, pw = d.w * TILE, ph = d.h * TILE;
    const dim = !relevant(overlay, d);
    ctx.globalAlpha = dim ? 0.25 : 1;
    if (!b.b) {
      const color = players[b.by]?.color || "#ffffff";
      ctx.fillStyle = color; ctx.globalAlpha = (dim ? 0.1 : 0.3);
      ctx.fillRect(px, py, pw, ph);
      ctx.globalAlpha = dim ? 0.3 : 1;
      ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.setLineDash([3, 2]);
      ctx.strokeRect(px + 1, py + 1, pw - 2, ph - 2); ctx.setLineDash([]);
      ctx.fillStyle = "rgba(0,0,0,0.7)"; ctx.fillRect(px + 1, py + ph - 5, pw - 2, 4);
      ctx.fillStyle = color; ctx.fillRect(px + 1, py + ph - 5, (pw - 2) * (b.p || 0) / 100, 4);
      if (b.prio && b.prio !== 5) prioLabel(px + 1, py + 1, b.prio);
    } else if (d.ladder) {
      ctx.strokeStyle = "#c9a56a"; ctx.lineWidth = 2;
      ctx.beginPath();
      for (let dy = 0; dy < d.h; dy++) {
        const y0 = py + dy * TILE;
        ctx.moveTo(px + 3, y0); ctx.lineTo(px + 3, y0 + TILE);
        ctx.moveTo(px + TILE - 3, y0); ctx.lineTo(px + TILE - 3, y0 + TILE);
        for (const r of [3, 8, 13]) { ctx.moveTo(px + 3, y0 + r); ctx.lineTo(px + TILE - 3, y0 + r); }
      }
      ctx.stroke();
    } else if (d.layer === "pipe" || d.layer === "wire") {
      // drawn as connected lines by drawLines
    } else if (d.solid && d.w === 1 && d.h === 1 && d.category === "base" && d.kind === "none") {
      ctx.fillStyle = d.insulated ? "#b9a24a" : "#a9a398"; ctx.fillRect(px, py, TILE, TILE);
      ctx.strokeStyle = "rgba(0,0,0,0.4)"; ctx.lineWidth = 1; ctx.strokeRect(px + 0.5, py + 0.5, TILE - 1, TILE - 1);
    } else {
      ctx.fillStyle = catColor(d.category); ctx.fillRect(px + 1, py + 1, pw - 2, ph - 2);
      ctx.strokeStyle = "rgba(0,0,0,0.6)"; ctx.lineWidth = 1; ctx.strokeRect(px + 1.5, py + 1.5, pw - 3, ph - 3);
      ctx.fillStyle = "#101418"; ctx.font = `bold ${d.w * d.h > 1 ? 10 : 7}px sans-serif`;
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(abbrev(d.name), px + pw / 2, py + ph / 2);
      if (b.on === 0) { ctx.fillStyle = "rgba(0,0,0,0.55)"; ctx.fillRect(px + 1, py + 1, pw - 2, ph - 2); }
      if (d.power && d.power.use && b.on !== 0 && !b.pw) { ctx.fillStyle = "#ffeb3b"; ctx.fillRect(px + pw - 5, py + 1, 4, 4); }
    }
    ctx.globalAlpha = 1;
    if (b.dc) {
      ctx.strokeStyle = "#ff3b3b"; ctx.lineWidth = 2; ctx.beginPath();
      ctx.moveTo(px + 2, py + 2); ctx.lineTo(px + pw - 2, py + ph - 2);
      ctx.moveTo(px + pw - 2, py + 2); ctx.lineTo(px + 2, py + ph - 2); ctx.stroke();
    }
    if (overlay === "power" || overlay === "plumbing") {
      const ports = overlay === "power" ? [[d.powerPort, "#ffd54f"]] : [[d.pipeIn, "#4fc3f7"], [d.pipeOut, "#ff8a65"]];
      for (const [p, color] of ports) {
        if (!p) continue;
        ctx.fillStyle = color; ctx.beginPath();
        ctx.arc(px + p[0] * TILE + TILE / 2, py + p[1] * TILE + TILE / 2, 3, 0, 6.3); ctx.fill();
      }
    }
  }

  // Tiny priority number in a cell's top-left corner (only drawn when it isn't the default 5).
  function prioLabel(x, y, n) {
    ctx.globalAlpha = 1; ctx.font = "bold 8px sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "top";
    ctx.fillStyle = "rgba(0,0,0,0.75)"; ctx.fillRect(x, y, 6, 9);
    ctx.fillStyle = "#fff"; ctx.fillText(String(n), x + 1, y);
  }

  function drawDigs(game, players) {
    const w = DC.grid.w;
    for (const [key, o] of Object.entries(game.digs)) {
      const i = Number(key), x = i % w, y = (i / w) | 0, px = x * TILE, py = y * TILE;
      const color = players[o.by]?.color || "#ffffff";
      ctx.globalAlpha = 0.28; ctx.fillStyle = color; ctx.fillRect(px, py, TILE, TILE);
      ctx.globalAlpha = 0.9; ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.beginPath();
      ctx.moveTo(px, py + TILE / 2); ctx.lineTo(px + TILE / 2, py);
      ctx.moveTo(px, py + TILE); ctx.lineTo(px + TILE, py);
      ctx.moveTo(px + TILE / 2, py + TILE); ctx.lineTo(px + TILE, py + TILE / 2);
      ctx.stroke(); ctx.globalAlpha = 1;
      if (o.prio && o.prio !== 5) prioLabel(px, py, o.prio);
      if (o.p > 0) { ctx.fillStyle = "rgba(0,0,0,0.7)"; ctx.fillRect(px + 1, py + TILE - 4, TILE - 2, 3);
        ctx.fillStyle = color; ctx.fillRect(px + 1, py + TILE - 4, (TILE - 2) * o.p / 100, 3); }
    }
  }

  function drawItems(game) {
    const stack = {};
    for (const it of Object.values(game.items)) {
      const cx = Math.floor(it.x), cy = Math.floor(it.y), k = cy * DC.grid.w + cx;
      const n = (stack[k] = (stack[k] || 0) + 1) - 1;
      const e = game.defs.elements[it.el];
      ctx.fillStyle = e ? e.color : "#ffffff";
      const sx = cx * TILE + 1 + (n % 3) * 5, sy = cy * TILE + TILE - 5 - Math.min(2, (n / 3) | 0) * 4;
      ctx.fillRect(sx, sy, 4, 4);
      ctx.strokeStyle = "rgba(0,0,0,0.6)"; ctx.lineWidth = 1; ctx.strokeRect(sx + 0.5, sy + 0.5, 3, 3);
    }
  }

  function drawDupes(game, dupes) {
    ctx.font = "9px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "alphabetic"; ctx.lineJoin = "round";
    for (const [id, d] of Object.entries(dupes)) {
      const px = d.x * TILE + TILE / 2, py = d.y * TILE + TILE - 1;
      const hue = (Number(id.replace(/\D/g, "")) * 67) % 360;
      ctx.fillStyle = d.sick ? "#c0392b" : `hsl(${hue},55%,55%)`;
      ctx.fillRect(px - 4, py - 8, 8, 8);
      ctx.fillStyle = d.sick ? "#e57373" : "#f1c9a5";
      ctx.beginPath(); ctx.arc(px, py - 11, 3.5, 0, 6.3); ctx.fill();
      ctx.strokeStyle = "rgba(0,0,0,0.7)"; ctx.lineWidth = 1; ctx.strokeRect(px - 3.5, py - 7.5, 7, 7);
      if (d.carry) {
        const e = game.defs.elements[d.carry.el];
        ctx.fillStyle = e ? e.color : "#fff"; ctx.beginPath(); ctx.arc(px + 6, py - 6, 2.5, 0, 6.3); ctx.fill();
        ctx.stroke();
      }
      ctx.lineWidth = 3; ctx.strokeStyle = "rgba(0,0,0,0.85)"; ctx.strokeText(d.name, px, py - 17);
      ctx.fillStyle = "#fff"; ctx.fillText(d.name, px, py - 17);
    }
  }

  function rectPx(r) {
    const x0 = Math.min(r[0], r[2]), x1 = Math.max(r[0], r[2]), y0 = Math.min(r[1], r[3]), y1 = Math.max(r[1], r[3]);
    return [x0 * TILE, y0 * TILE, (x1 - x0 + 1) * TILE, (y1 - y0 + 1) * TILE];
  }

  function drawPlayers(game, you) {
    ctx.font = "11px sans-serif"; ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
    for (const [pid, p] of Object.entries(game.players)) {
      if (pid === you) continue;
      if (p.drag) {
        const [x, y, w, h] = rectPx(p.drag);
        ctx.fillStyle = p.color; ctx.globalAlpha = 0.2; ctx.fillRect(x, y, w, h);
        ctx.globalAlpha = 1; ctx.strokeStyle = p.color; ctx.lineWidth = 1.5; ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
      }
      if (p.cursor) {
        const [cx, cy] = p.cursor, px = cx * TILE, py = cy * TILE;
        ctx.strokeStyle = p.color; ctx.lineWidth = 2; ctx.strokeRect(px + 1, py + 1, TILE - 2, TILE - 2);
        const label = p.tool ? `${p.name} (${p.tool})` : p.name;
        ctx.lineWidth = 3; ctx.strokeStyle = "rgba(0,0,0,0.85)"; ctx.strokeText(label, px + TILE, py - 2);
        ctx.fillStyle = p.color; ctx.fillText(label, px + TILE, py - 2);
      }
    }
  }

  function drawPreview(game) {
    const t = DC.tools;
    if (!t || !DC.lobby.me()?.player) return;
    const pv = t.preview();
    if (!pv) return;
    if (pv.rect) {
      const [x, y, w, h] = rectPx(pv.rect);
      ctx.fillStyle = pv.color; ctx.globalAlpha = 0.2; ctx.fillRect(x, y, w, h);
      ctx.globalAlpha = 1; ctx.strokeStyle = pv.color; ctx.lineWidth = 2; ctx.strokeRect(x + 1, y + 1, w - 2, h - 2);
    } else if (pv.cells) {
      const d = game.defs.buildings[pv.building];
      for (const [cx, cy] of pv.cells) {
        let bad = false;
        for (let dy = 0; dy < d.h && !bad; dy++) for (let dx = 0; dx < d.w; dx++) {
          const e = DC.grid.elementAt(cx + dx, cy + dy);
          if (!e || e.phase === "solid") { bad = true; break; }
        }
        ctx.fillStyle = bad ? "#ff4040" : "#40ff70"; ctx.globalAlpha = 0.4;
        ctx.fillRect(cx * TILE, cy * TILE, d.w * TILE, d.h * TILE);
        ctx.globalAlpha = 1; ctx.strokeStyle = bad ? "#ff4040" : "#40ff70"; ctx.lineWidth = 1.5;
        ctx.strokeRect(cx * TILE + 1, cy * TILE + 1, d.w * TILE - 2, d.h * TILE - 2);
      }
    }
  }

  function frame() {
    const lobby = DC.lobby, rt = DC.rt;
    if (!lobby || !rt || !DC.view) return;
    const state = lobby.state;
    const game = state && state.game;
    if (!game || !game.rows || state.phase === "lobby") return;
    DC.grid.update(game);
    const { w, h } = DC.grid;
    if (!DC.grid.el || !DC.grid.el[0]) return;
    if (canvas.width !== w * TILE) canvas.width = w * TILE;
    if (canvas.height !== h * TILE) canvas.height = h * TILE;
    const key = `${DC.grid.version}|${DC.view.overlay}|${w}x${h}`;
    if (key !== baseKey) { baseKey = key; drawBase(game); }
    ctx.drawImage(base, 0, 0);
    const overlay = DC.view.overlay;
    const players = game.players;
    const dupes = rt.sample((g) => g.dupes) || game.dupes;
    drawDigs(game, players);
    ctx.globalAlpha = relevant(overlay, { layer: "pipe" }) ? 1 : 0.25;
    drawLines(game, "pipe", overlay === "plumbing" ? "#7fd6ff" : "#3a82b8");
    ctx.globalAlpha = relevant(overlay, { layer: "wire" }) ? 1 : 0.25;
    drawLines(game, "wire", overlay === "power" ? "#ffe066" : "#b8902a");
    ctx.globalAlpha = 1;
    for (const [id, b] of Object.entries(game.buildings)) {
      const d = game.defs.buildings[b.t];
      if (d) drawBuilding(game, id, b, d, overlay, players);
    }
    drawItems(game);
    drawDupes(game, dupes);
    drawPlayers(game, state.you);
    drawPreview(game);
  }

  DC.render = { TILE, OVERLAYS, catColor, abbrev, frame };
  AppRealtime.loop(frame);
})();
