/*
 * Grid decoding: turns state.game.rows (one string per row and layer) into typed arrays.
 *   grid.dirty: Set of row indexes changed since the renderer last cleared it; grid.resets counts defs/size changes (full redraw)
 *   DC.grid.update(game)  decode changed rows (cached per row string); returns true if anything changed
 *   DC.grid.w, .h         size;  DC.grid.elId(i) element id of cell i
 *   DC.grid.el[y]         Uint8Array of element indexes (into defs.order) per row
 *   DC.grid.mass/germ[y]  levels 0-9;  temp[y]: raw index (value*4-40 C), 255 = vacuum
 *   DC.grid.tempAt(x,y)   degrees C or null (vacuum);  decorAt(x,y) decor number
 *   DC.grid.elementAt(x,y) element def {id, name, phase, color,...}
 *   DC.grid.footprint(d, rot) -> {w, h} of the rotated footprint (mirrors logic/buildings.py footprint)
 *   DC.grid.rotOffset(d, rot, [dx, dy]) -> [dx, dy] of an unrotated offset (port) after rot quarter turns clockwise
 * Shared global: window.DC (other modules add their own parts).
 */
(() => {
  const DC = (window.DC = window.DC || {});
  const ROW_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const LAYERS = ["el", "mass", "temp", "germ", "decor"];
  const grid = { w: 0, h: 0, defs: null, version: 0, resets: 0, dirty: new Set() };
  const rowsSeen = {}; // layer -> [string per row]
  let charToIndex = {};

  function decodeRow(layer, str) {
    const out = new Uint8Array(str.length);
    for (let i = 0; i < str.length; i++) {
      const c = str[i];
      if (layer === "el") out[i] = charToIndex[c] ?? 0;
      else if (layer === "mass" || layer === "germ") out[i] = c.charCodeAt(0) - 48;
      else out[i] = c === "-" ? 255 : ROW_CHARS.indexOf(c);
    }
    return out;
  }

  grid.update = (game) => {
    if (!game || !game.rows) return false;
    if (grid.defs !== game.defs) {
      grid.defs = game.defs;
      charToIndex = {};
      for (let i = 0; i < game.defs.chars.length; i++) charToIndex[game.defs.chars[i]] = i;
      for (const l of LAYERS) { grid[l] = []; rowsSeen[l] = []; }
      grid.resets++; grid.dirty.clear();
    }
    if (grid.w !== game.w || grid.h !== game.h) {
      grid.w = game.w; grid.h = game.h;
      for (const l of LAYERS) { grid[l] = []; rowsSeen[l] = []; }
      grid.resets++; grid.dirty.clear();
    }
    let changed = false;
    for (const l of LAYERS) {
      const rows = game.rows[l] || {};
      for (let y = 0; y < grid.h; y++) {
        const s = rows[y];
        if (s === undefined || rowsSeen[l][y] === s) continue;
        rowsSeen[l][y] = s;
        grid[l][y] = decodeRow(l, s);
        changed = true;
        grid.dirty.add(y); // any layer: a row repaint reads all layers
      }
    }
    if (changed) grid.version++;
    return changed;
  };

  const inside = (x, y) => x >= 0 && y >= 0 && x < grid.w && y < grid.h && grid.el[y];
  grid.inside = inside;
  grid.elId = (i) => grid.defs.order[i];
  grid.elementAt = (x, y) => (inside(x, y) ? grid.defs.elements[grid.defs.order[grid.el[y][x]]] : null);
  grid.tempAt = (x, y) => {
    if (!inside(x, y) || !grid.temp[y]) return null;
    const v = grid.temp[y][x];
    return v === 255 ? null : v * 4 - 40;
  };
  grid.decorAt = (x, y) => (inside(x, y) && grid.decor[y] ? grid.decor[y][x] - 30 : 0);
  grid.massAt = (x, y) => (inside(x, y) && grid.mass[y] ? grid.mass[y][x] : 0);
  grid.germAt = (x, y) => (inside(x, y) && grid.germ[y] ? grid.germ[y][x] : 0);
  grid.footprint = (d, rot) => ((rot || 0) % 2 ? { w: d.h, h: d.w } : { w: d.w, h: d.h });
  grid.rotOffset = (d, rot, off) => {
    let [dx, dy] = off, h = d.h;
    for (let i = 0; i < (rot || 0) % 4; i++) { [dx, dy] = [h - 1 - dy, dx]; h = i % 2 ? d.h : d.w; }
    return [dx, dy];
  };
  DC.grid = grid;
})();
