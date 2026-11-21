/*
 * Metro Lanes city model on the client: lookups over state.game for drawing and for input checks
 * (so a drag doesn't spam the server with moves it would refuse). The server stays the judge.
 *   ML.city.update(game)   call with each new state.game (rebuilds caches only when parts changed)
 *   ML.city.idx(x, y), xy(t), onMap(x, y), terrain(t) ("." "~" "^"), inArea(t)
 *   ML.city.road(t)        the road on tile t ({o, k, f?, fo?}) or undefined
 *   ML.city.building(t)    {kind: "house"|"shop", id, node, door} covering tile t, or undefined
 *   ML.city.doorOf(node)   a building node's driveway tile (undefined if t isn't a node)
 *   ML.city.linked(a, b)   whether road tiles a and b are linked
 *   ML.city.span(a, b)     drawing from land a straight into water/mountain b:
 *                          {kind: "b"|"t", tiles: [...], land: t} or {error: "..."}
 *   ML.city.spanEnd(a, b)  stepping from a onto an existing bridge/tunnel tile b: the land tile past it
 * Rules mirrored from logic/roads.py: spans go straight, at most game.rules.span[kind] tiles.
 */
(() => {
  const ML = (window.ML = window.ML || {});
  const city = (ML.city = {});
  let game = null, roadsRef = null, housesRef = null, shopsRef = null, linksRef = null;
  let buildings = new Map(), doors = new Map(), links = new Set();

  city.update = (g) => {
    game = g;
    if (!g) return;
    if (g.houses !== housesRef || g.shops !== shopsRef) {
      housesRef = g.houses; shopsRef = g.shops;
      buildings = new Map(); doors = new Map();
      for (const [id, h] of Object.entries(g.houses)) {
        buildings.set(h.t, { kind: "house", id, node: h.t, door: h.door });
        doors.set(h.t, h.door);
      }
      for (const [id, s] of Object.entries(g.shops)) {
        const [x, y] = city.xy(s.t);
        const info = { kind: "shop", id, node: s.node, door: s.door };
        for (const t of [s.t, city.idx(x + 1, y), city.idx(x, y + 1), city.idx(x + 1, y + 1)]) buildings.set(t, info);
        doors.set(s.node, s.door);
      }
    }
    if (g.links !== linksRef) { linksRef = g.links; links = new Set(Object.keys(g.links)); }
    roadsRef = g.roads;
  };

  city.idx = (x, y) => y * game.w + x;
  city.xy = (t) => [t % game.w, Math.floor(t / game.w)];
  city.onMap = (x, y) => x >= 0 && y >= 0 && x < game.w && y < game.h;
  city.terrain = (t) => { const [x, y] = city.xy(t); return game.rows[y][x]; };
  city.inArea = (t) => { const [x, y] = city.xy(t), a = game.area; return x >= a[0] && x <= a[2] && y >= a[1] && y <= a[3]; };
  city.road = (t) => roadsRef && roadsRef[String(t)];
  city.building = (t) => buildings.get(t);
  city.doorOf = (node) => doors.get(node);
  city.linked = (a, b) => links.has(a < b ? `${a},${b}` : `${b},${a}`);

  city.span = (a, b) => {
    const [ax, ay] = city.xy(a), [bx, by] = city.xy(b);
    const dx = bx - ax, dy = by - ay, ter = city.terrain(b), kind = ter === "~" ? "b" : "t";
    const name = kind === "b" ? "bridge" : "tunnel";
    if (dx && dy) return { error: `A ${name} must go straight across, not diagonally.` };
    const tiles = [];
    let [x, y] = [bx, by];
    while (city.onMap(x, y) && city.terrain(city.idx(x, y)) === ter) {
      tiles.push(city.idx(x, y));
      if (tiles.length > game.rules.span[kind]) return { error: `Too far: a ${name} spans at most ${game.rules.span[kind]} tiles.` };
      x += dx; y += dy;
    }
    if (!city.onMap(x, y) || city.terrain(city.idx(x, y)) !== ".") return { error: `The ${name} has nowhere to land.` };
    return { kind, tiles, land: city.idx(x, y) };
  };

  city.spanEnd = (a, b) => {
    const [ax, ay] = city.xy(a), [bx, by] = city.xy(b);
    const dx = bx - ax, dy = by - ay;
    let [x, y] = [bx, by];
    while (city.onMap(x, y)) {
      const r = city.road(city.idx(x, y));
      if (!r || r.k === "r") break;
      x += dx; y += dy;
    }
    return city.onMap(x, y) ? city.idx(x, y) : null;
  };
})();
