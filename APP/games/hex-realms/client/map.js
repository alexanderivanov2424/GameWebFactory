/*
 * Hex Realms: the pannable, zoomable SVG hex map (terrain: PNG art from art/terrain/ (TERRAIN_ART) or a flat colour, territory (weak land dashed), structures, units,
 * your pending orders (Travel goals dashed; units with orders greyed out), highlights, build ghost, event flashes). No game rules here.
 *
 *   const map = HexMap.create(element, { onCell(key), onHover(key|null), onRightClick(key) });
 *   map.draw(game, you, priv)   rebuild the dynamic layers from state (terrain only if the map changed)
 *   map.setHighlights({key: "reach"|"attack"|"range"|"sel"|"claim"|"goal"})   toggle classes on pre-made cell overlays
 *                               ("sel" cells also get one outline round their outside edge, none inside)
 *   map.setGhost({cells, ok, label} | null)   footprint preview under the mouse (small, rebuilt per hover)
 *   map.flash([{at, kind}])     brief pulsing markers (battle/siege cells)
 *   map.centre(key)             pan to a cell;  map.fit() resets the zoom
 *   map.focus(keys, zoom, ms)   glide (pan + zoom, eased) to centre `keys`; a Promise
 *   map.getView() / map.setView(view, ms)   save and glide back to a view ({x, y, k})
 *   map.mark(keys)              rings round cells (the combat replay.js is showing); [] clears
 *   HexMap.util                 pointy-top axial helpers: parse, key, add, neighbors, dist, center, DIRS
 *
 * Pointy-top axial "q,r" keys: x = SIZE*sqrt(3)*(q + r/2), y = SIZE*1.5*r. Drag pans, the wheel zooms
 * around the pointer, a click without dragging reports the cell. Styles (.hr-*) live in index.html.
 */
(() => {
  const { svg, fill } = AppDom;
  // Native append() would print arrays as "[object SVGElement]" and null as "null".
  const put = (node, ...children) => node.append(...children.flat(Infinity).filter((c) => c !== null && c !== undefined && c !== false));
  const SIZE = 30;
  const SQ3 = Math.sqrt(3);
  const UNIT_R = SIZE * 0.42;  // a unit's disc
  const DIRS = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]]; // DIRS[i] faces angle 60*i
  const COLORS = {
    plains: "#5c9a47", desert: "#d8bf7c", forest: "#2f6d3c",
    hills: "#8c7b55", mountain: "#8a8f9b", water: "#3a6ea6",
  };
  // Art files live in art/ next to this script. Units: art/units/<content "art"> (100 x 100 = the unit's disc at 4x),
  // drawn over the disc instead of the icon. Terrain: PNGs in art/terrain/ (208 x 240 = one hex at 4x), drawn over the flat colour. Each terrain lists
  // its variants as [file, weight]; a cell picks one from a hash of its key (the same for every viewer).
  // Terrains not listed here keep the flat colour and line glyph.
  const ART_DIR = new URL("art/", document.currentScript?.src || location.href).href;
  const TERRAIN_ART = {
    plains: [["plains.png", 1]],
    desert: [["desert.png", 1]],
    forest: [["forest.png", 1]],
    mountain: [["mountain_1.png", 99], ["mountain_2.png", 1]],
    hills: [["hill.png", 1]],
    water: [["ocean.png", 1]],
  };

  const parse = (k) => k.split(",").map(Number);
  const key = (q, r) => `${q},${r}`;
  const add = (k, [dq, dr]) => { const [q, r] = parse(k); return key(q + dq, r + dr); };
  const neighbors = (k) => DIRS.map((d) => add(k, d));
  const center = (k) => { const [q, r] = parse(k); return [SIZE * SQ3 * (q + r / 2), SIZE * 1.5 * r]; };
  const dist = (a, b) => {
    const [aq, ar] = parse(a), [bq, br] = parse(b);
    return (Math.abs(aq - bq) + Math.abs(ar - br) + Math.abs(aq + ar - bq - br)) / 2;
  };
  const corner = (x, y, i, s) => {
    const a = (Math.PI / 180) * (60 * i - 30);
    return [x + s * Math.cos(a), y + s * Math.sin(a)];
  };
  const pts = (x, y, s = SIZE) => Array.from({ length: 6 }, (_, i) => corner(x, y, i, s).map((v) => v.toFixed(1)).join(",")).join(" ");
  const middle = (ks) => { const ps = ks.map(center); return [0, 1].map((i) => ps.reduce((a, p) => a + p[i], 0) / ps.length); };
  const hexAt = (k, s, attrs) => { const [x, y] = center(k); return svg("polygon", { points: pts(x, y, s), ...attrs }); };

  // Edge i of a cell faces DIRS[i] and joins corners i and i+1: lines where the neighbour isn't in `same`.
  // `scale` < 1 draws the edges inset towards each cell's centre.
  function borders(cells, same, attrs, scale = 1) {
    const lines = [];
    for (const k of cells) {
      const [x, y] = center(k);
      neighbors(k).forEach((n, i) => {
        if (same(n)) return;
        const [x1, y1] = corner(x, y, i, SIZE * scale), [x2, y2] = corner(x, y, i + 1, SIZE * scale);
        lines.push(svg("line", { x1: x1.toFixed(1), y1: y1.toFixed(1), x2: x2.toFixed(1), y2: y2.toFixed(1), ...attrs }));
      });
    }
    return lines;
  }

  // One solid shape for a group of cells: each cell inset to `scale` of its size, with the gaps
  // between its own cells filled (a strip along each shared edge, a triangle where three meet),
  // so only the outside edge is inset. A thin stroke of the same colour hides seams.
  const BLOB = 0.8;
  function blob(cells, attrs, scale = BLOB) {
    const own = new Set(cells), out = [], seen = new Set();
    const inset = (k, [vx, vy]) => { const [x, y] = center(k); return [x + scale * (vx - x), y + scale * (vy - y)]; };
    const poly = (ps) => svg("polygon", { points: ps.map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" "), ...attrs });
    for (const k of cells) {
      const [x, y] = center(k);
      out.push(poly(Array.from({ length: 6 }, (_, i) => inset(k, corner(x, y, i, SIZE)))));
      neighbors(k).forEach((n, i) => {
        if (!own.has(n)) return;
        const v1 = corner(x, y, i, SIZE), v2 = corner(x, y, i + 1, SIZE);
        if (n > k) out.push(poly([inset(k, v1), inset(k, v2), inset(n, v2), inset(n, v1)]));
        const prev = neighbors(k)[(i + 5) % 6];  // corner i is shared by k, neighbour i-1 and neighbour i
        const id = v1.map((v) => v.toFixed(0)).join(",");
        if (own.has(prev) && !seen.has(id)) { seen.add(id); out.push(poly([inset(k, v1), inset(prev, v1), inset(n, v1)])); }
      });
    }
    return out;
  }

  // An inset outline round a region (`same(n)` says whether cell n is in it), drawn for `cells` (all of the
  // region or part of it, e.g. only its weak land): their outside edges inset to `scale`, plus, where two
  // region cells meet on the outside (a shared corner whose third cell isn't in the region), each cell's
  // half of the short join between their inset corners (so parts drawn in different styles still meet).
  function outline(cells, same, attrs, scale) {
    const out = borders(cells, same, attrs, scale);
    const inset = (k, [vx, vy]) => { const [x, y] = center(k); return [x + scale * (vx - x), y + scale * (vy - y)]; };
    const line = ([x1, y1], [x2, y2]) => svg("line", { x1: x1.toFixed(1), y1: y1.toFixed(1), x2: x2.toFixed(1), y2: y2.toFixed(1), ...attrs });
    const half = (k, n, v) => { const a = inset(k, v), b = inset(n, v); return line(a, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]); };
    for (const k of cells) {
      const [x, y] = center(k), ns = neighbors(k);
      ns.forEach((n, i) => {
        if (!same(n)) return;
        if (!same(ns[(i + 5) % 6])) out.push(half(k, n, corner(x, y, i, SIZE)));
        if (!same(ns[(i + 1) % 6])) out.push(half(k, n, corner(x, y, i + 1, SIZE)));
      });
    }
    return out;
  }

  // The outline of blob(cells), for the hover highlight.
  function blobLine(cells, attrs, scale = BLOB) {
    const own = new Set(cells);
    return outline(cells, (n) => own.has(n), attrs, scale);
  }

  // Territory borders: BORDER_W wide, inset (BORDER, a scale towards each cell's centre) by half their width so
  // the line's outer edge lies on the cell's edge; two realms' borders then sit side by side, touching.
  const BORDER_W = 3;
  const BORDER = 1 - (BORDER_W / 2) / (SIZE * SQ3 / 2);

  function glyph(terrain, x, y) {
    const a = { class: "hr-glyph" };
    if (terrain === "forest") return svg("path", { ...a, d: `M${x - 9},${y + 6} l5,-11 l5,11 z M${x + 1},${y + 8} l6,-13 l6,13 z` });
    if (terrain === "hills") return svg("path", { ...a, d: `M${x - 14},${y + 6} q7,-16 14,0 q7,-11 14,0` });
    if (terrain === "mountain") return svg("path", { ...a, d: `M${x - 14},${y + 9} l9,-20 l5,9 l4,-6 l9,17 z` });
    if (terrain === "water") return svg("path", { ...a, d: `M${x - 12},${y} q3,-5 6,0 t6,0 t6,0 M${x - 8},${y + 9} q3,-5 6,0 t6,0` });
    if (terrain === "desert") return svg("path", { ...a, d: `M${x - 8},${y - 4} h1 M${x + 6},${y + 3} h1 M${x - 2},${y + 9} h1 M${x + 3},${y - 8} h1`, "stroke-width": 2.5 });
    return null;
  }

  // A number in [0, 1) from a string (FNV-1a, then MurmurHash3's final mix to spread similar keys apart),
  // so art variants are picked the same way on every page.
  function hash01(text) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) h = Math.imul(h ^ text.charCodeAt(i), 16777619);
    h = Math.imul(h ^ (h >>> 16), 0x85ebca6b);
    h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }

  // The terrain art for cell k (an <image> covering its hex), or the line glyph when the terrain has no art.
  function terrainArt(terrain, k, mapKey, x, y) {
    const variants = TERRAIN_ART[terrain];
    if (!variants) return glyph(terrain, x, y);
    let roll = hash01(`${mapKey}|${k}`) * variants.reduce((sum, [, w]) => sum + w, 0);
    const [file] = variants.find(([, w]) => (roll -= w) < 0) || variants[variants.length - 1];
    return svg("image", { href: ART_DIR + "terrain/" + file, x: x - 26, y: y - SIZE, width: 52, height: 2 * SIZE, class: "hr-art" });
  }

  function create(element, handlers = {}) {
    const root = svg("svg", { class: "hr-svg" });
    const world = svg("g");
    const layer = (name) => { const g = svg("g", { class: `hr-${name}` }); put(world, g); return g; };
    const terrainG = layer("terrain"), territoryG = layer("territory"), structG = layer("structs"), dimG = layer("dim"), hlG = layer("hl"), selG = layer("sel");
    const hoverG = layer("hover"), orderG = layer("orders"), unitG = layer("units"), ghostG = layer("ghost"), flashG = layer("flashes"), markG = layer("marks");
    hlG.style.pointerEvents = "none";
    put(root, world);
    fill(element, root);

    let view = { x: 0, y: 0, k: 0.9 };
    let cells = null, all = new Set(), lastKey = null, hl = {}, hlClass = {};
    let hover = null, drag = null, moved = false, shapeAt = {};  // shapeAt: {cell: {cells, color}} for the hover outline
    // Hovering a structure or site outlines it in its owner's colour.
    function drawHover() {
      const s = hover && shapeAt[hover];
      fill(hoverG, s ? blobLine(s.cells, { class: "hr-hover-line", stroke: s.color }) : []);
    }
    const applyView = () => world.setAttribute("transform", `translate(${view.x.toFixed(1)} ${view.y.toFixed(1)}) scale(${view.k.toFixed(3)})`);

    function cellAt(event) {
      const rect = element.getBoundingClientRect();
      const x = (event.clientX - rect.left - view.x) / view.k, y = (event.clientY - rect.top - view.y) / view.k;
      const fq = (SQ3 / 3 * x - y / 3) / SIZE, fr = (2 / 3 * y) / SIZE, fs = -fq - fr;
      let q = Math.round(fq), r = Math.round(fr), s = Math.round(fs);
      const dq = Math.abs(q - fq), dr = Math.abs(r - fr), ds = Math.abs(s - fs);
      if (dq > dr && dq > ds) q = -r - s; else if (dr > ds) r = -q - s;
      const k = key(q, r);
      return all.has(k) ? k : null;
    }

    element.addEventListener("mousedown", (e) => {
      if (e.button !== 0 && e.button !== 1) return;
      drag = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, button: e.button };
      moved = false;
      e.preventDefault();
    });
    window.addEventListener("mousemove", (e) => {
      if (drag) {
        const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
        if (!moved && Math.hypot(dx, dy) < 4) return;
        moved = true;
        view.x = drag.vx + dx; view.y = drag.vy + dy;
        applyView();
      }
    });
    window.addEventListener("mouseup", (e) => {
      if (!drag) return;
      const wasClick = !moved && drag.button === 0;
      drag = null;
      if (wasClick && element.contains(e.target)) { const k = cellAt(e); if (k) handlers.onCell?.(k, e); }
    });
    element.addEventListener("mousemove", (e) => {
      if (drag && moved) return;
      const k = cellAt(e);
      if (k !== hover) { hover = k; drawHover(); handlers.onHover?.(k); }
    });
    element.addEventListener("mouseleave", () => { if (hover !== null) { hover = null; drawHover(); handlers.onHover?.(null); } });
    element.addEventListener("contextmenu", (e) => { e.preventDefault(); handlers.onRightClick?.(cellAt(e)); });
    element.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = element.getBoundingClientRect();
      const px = e.clientX - rect.left, py = e.clientY - rect.top;
      const k = Math.min(3, Math.max(0.3, view.k * Math.exp(-e.deltaY * 0.0012)));
      view.x = px - (px - view.x) * (k / view.k);
      view.y = py - (py - view.y) * (k / view.k);
      view.k = k;
      applyView();
    }, { passive: false });

    // Every cell of the hexagonal map; unexplored ones (not in game.cells under fog) are drawn as fog.
    function disk(radius) {
      const out = [];
      for (let q = -radius; q <= radius; q++) {
        for (let r = Math.max(-radius, -q - radius); r <= Math.min(radius, -q + radius); r++) out.push(key(q, r));
      }
      return out;
    }

    function buildStatic(game, mapKey) {
      fill(terrainG); fill(hlG); hl = {}; hlClass = {};
      // Top row first (y grows with r), left to right in a row: later cells paint over earlier ones, so a
      // tile's art may spill up over the tiles above it (its image's top corners lie over them).
      const keys = disk(game.radius).sort((a, b) => { const [qa, ra] = parse(a), [qb, rb] = parse(b); return ra - rb || qa - qb; });
      all = new Set(keys);
      for (const k of keys) {
        const [x, y] = center(k);
        const terrain = game.cells[k];
        if (terrain) put(terrainG, svg("polygon", { points: pts(x, y), fill: COLORS[terrain] || "#777", class: "hr-cell" }), terrainArt(terrain, k, mapKey, x, y));
        else put(terrainG, svg("polygon", { points: pts(x, y), class: "hr-fog" }));
        hl[k] = svg("polygon", { points: pts(x, y, SIZE - 1), class: "hr-hlcell" }); // transparent until highlighted (SVG fills black by default)
        put(hlG, hl[k]);
      }
    }

    function draw(game, you, priv) {
      const gkey = game.seats.join() + game.radius;
      if (game.cells !== cells) {
        const first = lastKey !== gkey;
        cells = game.cells; lastKey = gkey;
        buildStatic(game, gkey);
        if (first) { fit(); }
      }
      const players = game.players, content = game.content;
      const color = (pid) => players[pid]?.color || "#888";
      const nameOf = (pid) => players[pid]?.name || pid;
      for (const g of [territoryG, structG, orderG, unitG]) fill(g);
      // Explored but not seen right now: dimmed (enemy units there aren't shown).
      fill(dimG, (game.dim || []).map((k) => hexAt(k, SIZE, { class: "hr-dim" })));

      // Territory: a border in the owner's colour all round it (ownership shows here; the inside isn't shaded).
      // Weak land (bought with gold, game.claims) has a dashed border. The border lines are opaque
      // inside one translucent group, so where segments overlap (round caps, joins) they don't get darker.
      const weak = game.claims || {};
      for (const pid of game.seats) {
        const mine = Object.keys(game.territory).filter((k) => game.territory[k] === pid);
        const line = { stroke: color(pid), "stroke-width": BORDER_W, "stroke-linecap": "round" };
        const same = (n) => game.territory[n] === pid;
        const strong = mine.filter((k) => weak[k] !== pid), bought = mine.filter((k) => weak[k] === pid);
        put(territoryG, svg("g", { opacity: 0.8 }, ...outline(strong, same, line, BORDER),
            ...outline(bought, same, { ...line, "stroke-dasharray": "6 5", "stroke-linecap": "butt" }, BORDER)));
      }

      // Structures: solid, in the structure's own colour (content "color"), fused into one shape each.
      shapeAt = {};
      const reasonFor = (sid, s, def) => {
        if (s.active === false) return "Switched off.";
        return "Not working: no free workers.";
      };
      for (const [sid, s] of Object.entries(game.structures)) {
        const def = content.structures[s.type];
        if (!def) continue;
        const needsWork = (def.jobs > 0) || Object.keys(def.produce || {}).length > 0;
        const idle = !s.working && needsWork;
        let tip = `${def.name} (${nameOf(s.owner)})`;
        if (s.maxHp) tip += ` hp ${s.hp}/${s.maxHp}`;
        if (idle) tip += `\n${reasonFor(sid, s, def)}`;
        const g = svg("g", { class: `hr-struct${idle ? " hr-idle" : ""}` }, svg("title", {}, tip));
        put(g, blob(s.cells, { class: "hr-sfill", fill: def.color, stroke: def.color }));
        for (const k of s.cells) shapeAt[k] = { cells: s.cells, color: color(s.owner) };
        const [x, y] = middle(s.cells);
        put(g, svg("text", { x, y: y + 1, class: "hr-icon" }, def.icon || def.name.slice(0, 2)));
        if (idle) put(g, svg("line", { x1: x - 14, y1: y + 12, x2: x + 14, y2: y - 12, class: "hr-strike" }));
        if (s.maxHp && s.hp < s.maxHp) {
          put(g, svg("rect", { x: x - 16, y: y + 14, width: 32, height: 5, class: "hr-hpback" }),
            svg("rect", { x: x - 16, y: y + 14, width: 32 * s.hp / s.maxHp, height: 5, class: "hr-hpbar" }));
        }
        put(structG, g);
      }
      // Construction sites: the structure's colour, faded, with turns of work done.
      const working = new Set((priv && priv.building?.works) || []);
      for (const [cid, x] of Object.entries(game.sites || {})) {
        const def = content.structures[x.type];
        if (!def) continue;
        const [mx, my] = middle(x.cells);
        for (const k of x.cells) shapeAt[k] = { cells: x.cells, color: color(x.owner) };
        let tip = `${def.name} under construction (${nameOf(x.owner)}): ${x.done}/${x.turns} turns, ${x.builders} builder${x.builders > 1 ? "s" : ""} a turn`;
        if (x.owner === you) tip += working.has(cid) ? "\nBuilders at work this turn." : x.done < x.turns ? "\nWaiting: not enough idle people." : "";
        put(structG, svg("g", { class: "hr-struct hr-site" }, svg("title", {}, tip),
          blob(x.cells, { class: "hr-site-cell", fill: def.color, stroke: def.color }),
          svg("text", { x: mx, y: my + 1, class: "hr-icon" }, def.icon || def.name.slice(0, 2)),
          svg("text", { x: mx, y: my + 17, class: "hr-site-text" }, `${x.done}/${x.turns}`)));
      }

      // Units (yours that have an order this turn, or a standing order, greyed out).
      const ordered = new Set(priv?.ordered || []);
      for (const [uid, u] of Object.entries(game.units)) {
        const def = content.units[u.type];
        const [x, y] = center(u.at);
        const g = svg("g", { class: u.owner === you ? `hr-unit hr-mine${ordered.has(uid) ? " hr-ordered" : ""}` : "hr-unit" },
          svg("title", {}, `${def?.name || u.type} (${nameOf(u.owner)}) hp ${u.hp}/${u.maxHp}`),
          svg("circle", { cx: x, cy: y, r: UNIT_R, fill: color(u.owner) }),
          def?.art ? svg("image", { href: ART_DIR + "units/" + encodeURIComponent(def.art), x: x - UNIT_R, y: y - UNIT_R, width: 2 * UNIT_R, height: 2 * UNIT_R, class: "hr-art" })
            : svg("text", { x, y: y + 1, class: "hr-uicon" }, def?.icon || u.type.slice(0, 2)));
        if (u.maxHp <= 6) {
          const x0 = x - (u.maxHp - 1) * 3.5;
          for (let i = 0; i < u.maxHp; i++) put(g, svg("circle", { cx: x0 + i * 7, cy: y + SIZE * 0.62, r: 2.6, class: i < u.hp ? "hr-pip on" : "hr-pip" }));
        } else {
          put(g, svg("rect", { x: x - 14, y: y + SIZE * 0.55, width: 28, height: 4, class: "hr-hpback" }),
            svg("rect", { x: x - 14, y: y + SIZE * 0.55, width: 28 * u.hp / u.maxHp, height: 4, class: "hr-hpbar" }));
        }
        put(unitG, g);
      }

      drawHover();

      // Your pending orders.
      if (!priv) return;
      const o = priv.orders, mine = color(you);
      for (const b of o.builds) {
        const def = content.structures[b.type];
        put(orderG, b.cells.map((k) => hexAt(k, SIZE * 0.9, { fill: def?.color || mine, "fill-opacity": 0.35, stroke: mine, "stroke-width": 2.5, "stroke-dasharray": "5 4" })));
        const [x, y] = middle(b.cells);
        put(orderG, svg("text", { x, y: y + 1, class: "hr-icon hr-ghosttext" }, def?.icon || ""));
      }
      for (const c of o.claims || []) {
        put(orderG, hexAt(c.at, SIZE * 0.8, { fill: mine, "fill-opacity": 0.25, stroke: mine, "stroke-width": 2.5, "stroke-dasharray": "4 4" }),
          svg("text", { x: center(c.at)[0], y: center(c.at)[1] + 1, class: "hr-icon hr-ghosttext" }, "⚑"));
      }
      for (const [uid, path] of Object.entries(o.moves)) {
        const u = game.units[uid];
        if (!u) continue;
        const ks = [u.at, ...path.filter((k, i) => !(i === 0 && k === u.at))];
        const ps = ks.map(center);
        put(orderG, svg("polyline", { points: ps.map((p) => p.join(",")).join(" "), class: "hr-path" }));
        if (ps.length > 1) {
          const [x1, y1] = ps[ps.length - 2], [x2, y2] = ps[ps.length - 1];
          const a = Math.atan2(y2 - y1, x2 - x1);
          const back = (off) => `${(x2 - 11 * Math.cos(a + off)).toFixed(1)},${(y2 - 11 * Math.sin(a + off)).toFixed(1)}`;
          put(orderG, svg("polygon", { points: `${x2.toFixed(1)},${y2.toFixed(1)} ${back(0.5)} ${back(-0.5)}`, class: "hr-arrow" }));
        }
      }
      for (const [uid, a] of Object.entries(priv.auto || {})) {  // Travel orders: the rest of the way, dashed
        const u = game.units[uid];
        if (!u || !a.goal) continue;
        const path = o.moves[uid] || [];
        const [x1, y1] = center(path.length ? path[path.length - 1] : u.at), [x2, y2] = center(a.goal);
        put(orderG, svg("line", { x1, y1, x2, y2, class: "hr-path hr-travel" }), svg("text", { x: x2, y: y2 + 1, class: "hr-icon hr-ghosttext" }, "⚑"));
      }
      for (const [uid, at] of Object.entries(o.shots)) {
        const u = game.units[uid];
        if (!u) continue;
        const [x1, y1] = center(u.at), [x2, y2] = center(at);
        put(orderG, svg("line", { x1, y1, x2, y2, class: "hr-shot" }), svg("circle", { cx: x2, cy: y2, r: 7, class: "hr-shotmark" }));
      }
      for (const uid of o.holds) {
        const u = game.units[uid];
        if (!u) continue;
        const [x, y] = center(u.at);
        put(orderG, svg("path", { d: "M0,-8 L7,-5 L6,3 L0,9 L-6,3 L-7,-5 Z", transform: `translate(${x + 14} ${y - 14})`, class: "hr-hold" }));
      }
      for (const [uid, rot] of Object.entries(o.found)) {
        const u = game.units[uid], th = content.structures.town_hall;
        if (!u || !th) continue;
        const foot = th.rotations[rot].map((d) => add(u.at, d));
        put(orderG, foot.map((k) => hexAt(k, SIZE * 0.9, { fill: "#f1c84b", "fill-opacity": 0.25, stroke: "#f1c84b", "stroke-width": 2.5, "stroke-dasharray": "5 4" })));
        const [x, y] = middle(foot);
        put(orderG, svg("text", { x, y: y + 1, class: "hr-icon hr-ghosttext" }, th.icon || "TH"));
      }
    }

    function setHighlights(next) {
      for (const k of Object.keys(hlClass)) if (!(k in next)) { hl[k]?.setAttribute("class", "hr-hlcell"); delete hlClass[k]; }
      for (const [k, c] of Object.entries(next)) {
        if (hlClass[k] === c || !hl[k]) continue;
        hl[k].setAttribute("class", `hr-hlcell hr-hl-${c}`);
        hlClass[k] = c;
      }
      // "sel" cells are only filled; the selection (a unit's cell, or a whole structure) gets one
      // outline round its outside edge, with no lines between its own cells.
      const sel = Object.keys(next).filter((k) => next[k] === "sel" && hl[k]);
      fill(selG, borders(sel, (n) => next[n] === "sel", { class: "hr-sel-line" }, (SIZE - 1) / SIZE));
    }

    function setGhost(g) {
      fill(ghostG);
      if (!g) return;
      const cls = g.ok ? "hr-ghost-ok" : "hr-ghost-bad";
      put(ghostG, g.cells.filter((k) => all.has(k)).map((k) => hexAt(k, SIZE * 0.92, { class: cls })));
      if (g.label && all.has(g.cells[0])) { const [x, y] = middle(g.cells); put(ghostG, svg("text", { x, y: y + 1, class: "hr-icon" }, g.label)); }
    }

    function flash(items) {
      for (const { at, kind } of items) {
        if (!all.has(at)) continue;
        const [x, y] = center(at);
        const c = svg("circle", { cx: x, cy: y, r: SIZE * 0.7, class: `hr-flash hr-flash-${kind}` });
        put(flashG, c);
        setTimeout(() => c.remove(), 3200);
      }
    }

    function centre(k) {
      if (!k) return;
      const rect = element.getBoundingClientRect();
      const [x, y] = center(k);
      view.x = rect.width / 2 - x * view.k; view.y = rect.height / 2 - y * view.k;
      applyView();
    }
    function fit() { view.k = 0.9; view.x = element.clientWidth / 2; view.y = element.clientHeight / 2; applyView(); }

    // Smooth pan/zoom to `target` ({x, y, k}) over `ms` (0 = jump). Resolves when it gets there, or
    // as soon as another glide starts.
    let anim = null, settle = null;
    function glide(target, ms) {
      cancelAnimationFrame(anim);
      settle?.();
      const from = { ...view };
      return new Promise((resolve) => {
        settle = () => { settle = null; resolve(); };
        if (!ms) { Object.assign(view, target); applyView(); settle(); return; }
        const t0 = performance.now();
        const frame = (now) => {
          const p = Math.min(1, (now - t0) / ms), e = p < 0.5 ? 2 * p * p : 1 - (2 - 2 * p) ** 2 / 2;
          for (const c of ["x", "y", "k"]) view[c] = from[c] + (target[c] - from[c]) * e;
          applyView();
          if (p < 1) anim = requestAnimationFrame(frame); else settle?.();
        };
        anim = requestAnimationFrame(frame);
      });
    }
    // Glide so the middle of `keys` is in the middle of the screen at zoom k.
    function focus(keys, k, ms) {
      const [x, y] = middle(keys);
      return glide({ k, x: element.clientWidth / 2 - x * k, y: element.clientHeight / 2 - y * k }, ms);
    }
    // Rings round the cells of the combat being shown (replay.js); [] clears them.
    function mark(keys) {
      fill(markG, keys.filter((k) => all.has(k)).map((k) => hexAt(k, SIZE - 3, { class: "hr-mark" })));
    }

    applyView();
    return { draw, setHighlights, setGhost, flash, centre, fit, focus, mark, getView: () => ({ ...view }), setView: glide };
  }

  window.HexMap = { create, util: { parse, key, add, neighbors, dist, center, DIRS } };
})();
