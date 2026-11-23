/*
 * Snowbound grid: decodes state.game.rows (logic/world.py) and mirrors the walking rules.
 *   SB.grid.update(game)      decode rows whose strings changed (paints the 1-pixel-per-lot image)
 *   SB.grid.reset()           new game
 *   SB.grid.w, .h, .image     size and the offscreen canvas (one pixel per lot)
 *   SB.grid.level(x, y)       snow level 0-61 (0 = none); feat(x, y) feature char; reached(x, y)
 *   SB.grid.snowAt(x, y)      approximate snow on a lot
 *   SB.grid.passable(x, y, wade?)  can a person stand there (reached, or level <= wade, default move.wade)
 *   SB.grid.road(x, y)        road level 0-4 (0 = none; state.game.roadLevels names them)
 *   SB.grid.workable(x, y)    has snow and is reached or next to a reached lot
 *   SB.grid.move(x, y, dx, dy, rules, wade)  same as logic/avatars.py move(): keep them in sync
 *   SB.grid.speed(p, rules)   walking speed for a public player entry at its position
 * rules = state.game.move ({radius, speed, dusted, road: [walk x per level], frostbite, starving, wade, reach}).
 */
(() => {
  const SB = (window.SB = window.SB || {});
  const SNOW_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
  const LEVEL_BASE = 1.2;
  const REACHED = new Set([",", "X", "T", "H", "G", "C", "K", "S"]);
  const GROUND = { ",": [92, 101, 112], X: [123, 74, 42], T: [62, 98, 70], H: [120, 92, 70], G: [110, 96, 96], C: [120, 104, 70], K: [104, 100, 112], S: [118, 108, 132] };
  const ROADS = [null, [128, 112, 92], [150, 146, 136], [62, 66, 74], [96, 64, 58]];
  const HINT = { t: [70, 110, 82], h: [170, 140, 120], g: [200, 120, 110] };

  const grid = (SB.grid = { w: 0, h: 0, image: null });
  let levels = null, feats = null, roads = null, snowRows = [], featRows = [], roadRows = [], ctx = null, pixels = null, wade = 4;

  const mix = (a, b, t) => [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * t));

  function color(level, f, road) {
    if (REACHED.has(f)) {
      const ground = (road && ROADS[road]) || GROUND[f] || GROUND[","];
      return level ? mix(ground, [222, 230, 240], Math.min(1, 0.4 + level / 30)) : ground;
    }
    if (f === "x") return GROUND.X;
    let snow = level <= wade ? mix([206, 216, 228], [236, 241, 248], level / wade)
      : mix([248, 251, 255], [178, 198, 224], Math.min(1, (level - wade) / 48));
    if (HINT[f]) snow = mix(snow, HINT[f], 0.35);
    return snow;
  }

  grid.reset = () => { levels = null; grid.w = grid.h = 0; };

  grid.update = (game) => {
    if (!game || !game.rows) return false;
    wade = game.move.wade;
    if (game.w !== grid.w || game.h !== grid.h || !levels) {
      grid.w = game.w; grid.h = game.h;
      levels = new Uint8Array(grid.w * grid.h); feats = new Array(grid.w * grid.h).fill("."); roads = new Uint8Array(grid.w * grid.h);
      snowRows = []; featRows = []; roadRows = [];
      grid.image = document.createElement("canvas");
      grid.image.width = grid.w; grid.image.height = grid.h;
      ctx = grid.image.getContext("2d");
      pixels = ctx.createImageData(grid.w, grid.h);
    }
    let changed = false;
    const w = grid.w;
    for (let y = 0; y < grid.h; y++) {
      const s = game.rows.snow[String(y)], f = game.rows.feat[String(y)], r = (game.rows.road || {})[String(y)] || "";
      if (s === undefined || f === undefined || (s === snowRows[y] && f === featRows[y] && r === roadRows[y])) continue;
      snowRows[y] = s; featRows[y] = f; roadRows[y] = r;
      for (let x = 0; x < w; x++) {
        const i = y * w + x;
        levels[i] = SNOW_CHARS.indexOf(s[x]);
        feats[i] = f[x];
        roads[i] = Number(r[x]) || 0;
        const c = color(levels[i], f[x], roads[i]);
        const p = i * 4;
        pixels.data[p] = c[0]; pixels.data[p + 1] = c[1]; pixels.data[p + 2] = c[2]; pixels.data[p + 3] = 255;
      }
      changed = true;
    }
    if (changed) ctx.putImageData(pixels, 0, 0);
    return changed;
  };

  const inside = (x, y) => levels && x >= 0 && y >= 0 && x < grid.w && y < grid.h;
  grid.level = (x, y) => (inside(x, y) ? levels[y * grid.w + x] : 0);
  grid.feat = (x, y) => (inside(x, y) ? feats[y * grid.w + x] : ".");
  grid.reached = (x, y) => inside(x, y) && REACHED.has(feats[y * grid.w + x]);
  grid.snowAt = (x, y) => { const l = grid.level(x, y); return l ? Math.pow(LEVEL_BASE, l - 1) : 0; };
  grid.passable = (x, y, myWade = wade) => inside(x, y) && (grid.reached(x, y) || levels[y * grid.w + x] <= myWade);
  grid.road = (x, y) => (inside(x, y) ? roads[y * grid.w + x] : 0);
  grid.workable = (x, y) => inside(x, y) && levels[y * grid.w + x] > 0 &&
    (grid.reached(x, y) || grid.reached(x + 1, y) || grid.reached(x - 1, y) || grid.reached(x, y + 1) || grid.reached(x, y - 1));

  function blocked(x, y, r, myWade) {
    for (const cx of [x - r, x + r]) for (const cy of [y - r, y + r]) {
      if (!grid.passable(Math.floor(cx), Math.floor(cy), myWade)) return true;
    }
    return false;
  }

  grid.move = (x, y, dx, dy, rules, myWade = wade) => {
    const r = rules.radius;
    for (const part of [1, 0.5, 0.25]) if (dx && !blocked(x + dx * part, y, r, myWade)) { x += dx * part; break; }
    for (const part of [1, 0.5, 0.25]) if (dy && !blocked(x, y + dy * part, r, myWade)) { y += dy * part; break; }
    return [x, y];
  };

  grid.speed = (p, rules) => {
    const lx = Math.floor(p.x), ly = Math.floor(p.y);
    let s = rules.speed;
    if (grid.reached(lx, ly) && grid.level(lx, ly) > 0) s *= rules.dusted;
    else if (grid.road(lx, ly)) s *= rules.road[grid.road(lx, ly)];
    if (p.status === "frostbite") s *= rules.frostbite;
    if (p.status === "starving") s *= rules.starving;
    return s;
  };
})();
