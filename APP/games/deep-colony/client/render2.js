/*
 * Drawing helpers for render.js (load render2.js BEFORE render.js; needs grid.js). Pure helpers: the canvas context and TILE are passed in.
 *   DC.render2.occupancy(game)           {layer: Map(cell index -> building id)} of finished buildings, rotation-aware
 *   DC.render2.canPlaceHint(game, d, rot, x, y)   client placement hint (the server decides)
 *   DC.render2.relevant(overlay, d)      false when the building is dimmed in that overlay
 *   DC.render2.drawLines(ctx, TILE, game, layer, color)   pipes / gas pipes / wires as connected lines
 *   DC.render2.drawPorts(ctx, TILE, d, rot, px, py, kinds)  coloured port dots ([] kinds = all)
 *   DC.render2.drawPackets(ctx, TILE, game, overlay)      pipe contents as dots (plumbing / vent overlays)
 *   DC.render2.PORT_COLORS {powerPort, pipeIn, pipeOut, gasIn, gasOut}
 */
(() => {
  const DC = (window.DC = window.DC || {});
  const PORT_COLORS = { powerPort: "#ffd54f", pipeIn: "#2979ff", pipeOut: "#00e5ff", gasIn: "#9aa5b1", gasOut: "#ffffff" };
  const LINE_LAYERS = ["main", "pipe", "gaspipe", "wire"];
  const mapOf = (mk) => Object.fromEntries(LINE_LAYERS.map((l) => [l, mk()]));
  const layerOf = (d) => (LINE_LAYERS.includes(d.layer) ? d.layer : "main");

  let occ = null, occFor = null;
  function occupancy(game) {
    if (occFor === game.buildings) return occ;
    occFor = game.buildings;
    occ = mapOf(() => new Map());
    const w = DC.grid.w;
    for (const [id, b] of Object.entries(game.buildings)) {
      const d = game.defs.buildings[b.t];
      if (!d || !b.b) continue; // unfinished sites are ghosts, not connected lines
      const fp = DC.grid.footprint(d, b.r), map = occ[layerOf(d)];
      for (let dy = 0; dy < fp.h; dy++) for (let dx = 0; dx < fp.w; dx++) map.set((b.y + dy) * w + b.x + dx, id);
    }
    return occ;
  }

  // Placement hint: occupancy including sites, plus finished solid tiles.
  let pOccFor = null, pOcc = null;
  function placeOcc(game) {
    if (pOccFor === game.buildings) return pOcc;
    pOccFor = game.buildings;
    pOcc = { ...mapOf(() => new Set()), solid: new Set() };
    const w = DC.grid.w;
    for (const b of Object.values(game.buildings)) {
      const d = game.defs.buildings[b.t];
      if (!d) continue;
      const fp = DC.grid.footprint(d, b.r), set = pOcc[layerOf(d)];
      for (let dy = 0; dy < fp.h; dy++) for (let dx = 0; dx < fp.w; dx++) {
        const i = (b.y + dy) * w + b.x + dx;
        set.add(i);
        if (b.b && d.solid && layerOf(d) === "main") pOcc.solid.add(i);
      }
    }
    return pOcc;
  }

  function canPlaceHint(game, d, rot, x, y) {
    const { w, h } = DC.grid, o = placeOcc(game), fp = DC.grid.footprint(d, rot), layer = layerOf(d);
    for (let dy = 0; dy < fp.h; dy++) for (let dx = 0; dx < fp.w; dx++) {
      const cx = x + dx, cy = y + dy;
      if (cx <= 0 || cy <= 0 || cx >= w - 1 || cy >= h - 1) return false;
      const e = DC.grid.elementAt(cx, cy);
      if (!e || e.phase === "solid") return false;
      const i = cy * w + cx;
      if (o[layer].has(i)) return false;
      if (layer === "main" && d.solid && o.solid.has(i)) return false;
    }
    if (d.floor) {
      for (let dx = 0; dx < fp.w; dx++) {
        const cx = x + dx, cy = y + fp.h;
        if (cx >= w || cy >= h) return false;
        const e = DC.grid.elementAt(cx, cy);
        if (!((e && e.phase === "solid") || o.solid.has(cy * w + cx))) return false;
      }
    }
    return true;
  }

  function relevant(overlay, d) {
    if (overlay === "power") return d.layer === "wire" || Boolean(Object.keys(d.power || {}).length || d.powerPort);
    if (overlay === "plumbing") return d.layer === "pipe" || Boolean(d.pipeIn || d.pipeOut);
    if (overlay === "vent") return d.layer === "gaspipe" || Boolean(d.gasIn || d.gasOut);
    return true;
  }

  function drawLines(ctx, TILE, game, layer, color) {
    const o = occupancy(game)[layer], w = DC.grid.w;
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

  function drawPorts(ctx, TILE, d, rot, px, py, kinds) {
    for (const k of kinds && kinds.length ? kinds : Object.keys(PORT_COLORS)) {
      if (!d[k]) continue;
      const [dx, dy] = DC.grid.rotOffset(d, rot, d[k]);
      ctx.fillStyle = PORT_COLORS[k]; ctx.strokeStyle = "rgba(0,0,0,0.8)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.arc(px + dx * TILE + TILE / 2, py + dy * TILE + TILE / 2, 3, 0, 6.3); ctx.fill(); ctx.stroke();
    }
  }

  // One dot per pipe segment, in the element's colour; size by kg against a full liquid segment (10 kg) / gas segment (1 kg).
  function drawPackets(ctx, TILE, game, overlay) {
    const w = DC.grid.w;
    const sets = overlay === "plumbing" ? [[game.pipes, 10]] : overlay === "vent" ? [[game.gaspipes, 1]] : [];
    for (const [pk, full] of sets) {
      for (const [key, p] of Object.entries(pk || {})) {
        const i = Number(key), e = game.defs.elements[p.el];
        ctx.fillStyle = e ? e.color : "#ffffff"; ctx.strokeStyle = "rgba(0,0,0,0.8)"; ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc((i % w) * TILE + TILE / 2, ((i / w) | 0) * TILE + TILE / 2, 1.5 + 2.5 * Math.min(1, p.kg / full), 0, 6.3);
        ctx.fill(); ctx.stroke();
      }
    }
  }

  DC.render2 = { occupancy, canPlaceHint, relevant, drawLines, drawPorts, drawPackets, PORT_COLORS };
})();
