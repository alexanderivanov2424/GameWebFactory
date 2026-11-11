/*
 * Hex Realms: the pannable, zoomable SVG hex map (terrain, territory, structures, roads, units,
 * your pending orders, highlights, build ghost, event flashes). No game rules here.
 *
 *   const map = HexMap.create(element, { onCell(key), onHover(key|null), onRightClick(key) });
 *   map.draw(game, you, priv)   rebuild the dynamic layers from state (terrain only if the map changed)
 *   map.setHighlights({key: "reach"|"attack"|"range"|"sel"})   toggle classes on pre-made cell overlays
 *   map.setGhost({cells, ok, label} | null)   footprint preview under the mouse (small, rebuilt per hover)
 *   map.flash([{at, kind}])     brief pulsing markers (battle/siege cells)
 *   map.centre(key)             pan to a cell;  map.fit() resets the zoom
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
  const DIRS = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]]; // DIRS[i] faces angle 60*i
  const COLORS = {
    grass: "#5c9a47", plains: "#b3b46f", desert: "#d8bf7c", forest: "#2f6d3c",
    hills: "#8c7b55", mountain: "#8a8f9b", water: "#3a6ea6",
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
  const hexAt = (k, s, attrs) => { const [x, y] = center(k); return svg("polygon", { points: pts(x, y, s), ...attrs }); };

  // Edge i of a cell faces DIRS[i] and joins corners i and i+1: lines where the neighbour isn't in `same`.
  function borders(cells, same, attrs) {
    const lines = [];
    for (const k of cells) {
      const [x, y] = center(k);
      neighbors(k).forEach((n, i) => {
        if (same(n)) return;
        const [x1, y1] = corner(x, y, i, SIZE), [x2, y2] = corner(x, y, i + 1, SIZE);
        lines.push(svg("line", { x1: x1.toFixed(1), y1: y1.toFixed(1), x2: x2.toFixed(1), y2: y2.toFixed(1), ...attrs }));
      });
    }
    return lines;
  }

  function glyph(terrain, x, y) {
    const a = { class: "hr-glyph" };
    if (terrain === "forest") return svg("path", { ...a, d: `M${x - 9},${y + 6} l5,-11 l5,11 z M${x + 1},${y + 8} l6,-13 l6,13 z` });
    if (terrain === "hills") return svg("path", { ...a, d: `M${x - 14},${y + 6} q7,-16 14,0 q7,-11 14,0` });
    if (terrain === "mountain") return svg("path", { ...a, d: `M${x - 14},${y + 9} l9,-20 l5,9 l4,-6 l9,17 z` });
    if (terrain === "water") return svg("path", { ...a, d: `M${x - 12},${y} q3,-5 6,0 t6,0 t6,0 M${x - 8},${y + 9} q3,-5 6,0 t6,0` });
    if (terrain === "desert") return svg("path", { ...a, d: `M${x - 8},${y - 4} h1 M${x + 6},${y + 3} h1 M${x - 2},${y + 9} h1 M${x + 3},${y - 8} h1`, "stroke-width": 2.5 });
    return null;
  }

  function create(element, handlers = {}) {
    const root = svg("svg", { class: "hr-svg" });
    const world = svg("g");
    const layer = (name) => { const g = svg("g", { class: `hr-${name}` }); put(world, g); return g; };
    const terrainG = layer("terrain"), territoryG = layer("territory"), structG = layer("structs"), hlG = layer("hl");
    const orderG = layer("orders"), unitG = layer("units"), ghostG = layer("ghost"), flashG = layer("flashes");
    hlG.style.pointerEvents = "none";
    put(root, world);
    fill(element, root);

    let view = { x: 0, y: 0, k: 0.9 };
    let cells = null, lastKey = null, hl = {}, hlClass = {};
    let hover = null, drag = null, moved = false;
    const applyView = () => world.setAttribute("transform", `translate(${view.x.toFixed(1)} ${view.y.toFixed(1)}) scale(${view.k.toFixed(3)})`);

    function cellAt(event) {
      const rect = element.getBoundingClientRect();
      const x = (event.clientX - rect.left - view.x) / view.k, y = (event.clientY - rect.top - view.y) / view.k;
      const fq = (SQ3 / 3 * x - y / 3) / SIZE, fr = (2 / 3 * y) / SIZE, fs = -fq - fr;
      let q = Math.round(fq), r = Math.round(fr), s = Math.round(fs);
      const dq = Math.abs(q - fq), dr = Math.abs(r - fr), ds = Math.abs(s - fs);
      if (dq > dr && dq > ds) q = -r - s; else if (dr > ds) r = -q - s;
      const k = key(q, r);
      return cells && k in cells ? k : null;
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
      if (k !== hover) { hover = k; handlers.onHover?.(k); }
    });
    element.addEventListener("mouseleave", () => { if (hover !== null) { hover = null; handlers.onHover?.(null); } });
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

    function buildStatic(game) {
      fill(terrainG); fill(hlG); hl = {}; hlClass = {};
      for (const [k, terrain] of Object.entries(game.cells)) {
        const [x, y] = center(k);
        put(terrainG, svg("polygon", { points: pts(x, y), fill: COLORS[terrain] || "#777", class: "hr-cell" }), glyph(terrain, x, y));
        hl[k] = svg("polygon", { points: pts(x, y, SIZE - 1) });
        put(hlG, hl[k]);
      }
    }

    function draw(game, you, priv) {
      const gkey = game.seats.join() + game.radius;
      if (game.cells !== cells) {
        const first = lastKey !== gkey;
        cells = game.cells; lastKey = gkey;
        buildStatic(game);
        if (first) { fit(); }
      }
      const players = game.players, content = game.content;
      const color = (pid) => players[pid]?.color || "#888";
      const nameOf = (pid) => players[pid]?.name || pid;
      for (const g of [territoryG, structG, orderG, unitG]) fill(g);

      // Territory: faint tint plus a coloured border where it meets another owner.
      for (const pid of game.seats) {
        const mine = Object.keys(game.territory).filter((k) => game.territory[k] === pid);
        put(territoryG, mine.map((k) => hexAt(k, SIZE, { fill: color(pid), "fill-opacity": 0.16 })),
          borders(mine, (n) => game.territory[n] === pid, { stroke: color(pid), "stroke-width": 3, "stroke-opacity": 0.8, "stroke-linecap": "round" }));
      }

      // Structures.
      const cellStruct = {};
      for (const [sid, s] of Object.entries(game.structures)) for (const c of s.cells) cellStruct[c] = sid;
      const reasonFor = (sid, s, def) => {
        if (s.active === false) return "Switched off.";
        return "Not working: no free workers.";
      };
      const stranded = new Set((priv && priv.report.stranded) || []);
      const roads = [];
      for (const [sid, s] of Object.entries(game.structures)) {
        const def = content.structures[s.type];
        if (!def) continue;
        if (s.type === "road") { roads.push(s); continue; }
        const c = color(s.owner);
        const needsWork = (def.jobs > 0) || Object.keys(def.produce || {}).length > 0;
        const idle = !s.working && needsWork;
        let tip = `${def.name} (${nameOf(s.owner)})`;
        if (s.maxHp) tip += ` hp ${s.hp}/${s.maxHp}`;
        if (idle) tip += `\n${reasonFor(sid, s, def)}`;
        const cut = stranded.has(sid);
        if (cut) tip += "\nNo road network leads to a store: its goods wait here (one turn's worth).";
        const g = svg("g", { class: `hr-struct${idle ? " hr-idle" : ""}${cut ? " hr-stranded" : ""}` }, svg("title", {}, tip));
        put(g, s.cells.map((k) => hexAt(k, SIZE * 0.97, { fill: c, "fill-opacity": 0.88 })));
        const own = new Set(s.cells);
        put(g, borders(s.cells, (n) => own.has(n), { stroke: "#10131a", "stroke-width": 3, "stroke-linecap": "round" }));
        const [x, y] = center(s.at);
        put(g, svg("text", { x, y: y + 1, class: "hr-icon" }, def.icon || def.name.slice(0, 2)));
        if (idle) put(g, svg("line", { x1: x - 14, y1: y + 12, x2: x + 14, y2: y - 12, class: "hr-strike" }));
        if (s.maxHp && s.hp < s.maxHp) {
          put(g, svg("rect", { x: x - 16, y: y + 14, width: 32, height: 5, class: "hr-hpback" }),
            svg("rect", { x: x - 16, y: y + 14, width: 32 * s.hp / s.maxHp, height: 5, class: "hr-hpbar" }));
        }
        put(structG, g);
      }
      for (const s of roads) {
        const k = s.at;
        const links = neighbors(k).filter((n) => cellStruct[n] && game.structures[cellStruct[n]].owner === s.owner
          && (game.structures[cellStruct[n]].type !== "road" || n > k));
        const [x, y] = center(k);
        const g = svg("g", { class: "hr-road" }, svg("title", {}, `Road (${nameOf(s.owner)})`));
        for (const n of links) { const [nx, ny] = center(n); put(g, svg("line", { x1: x, y1: y, x2: nx, y2: ny, stroke: color(s.owner), class: "hr-road-edge" })); }
        for (const n of links) { const [nx, ny] = center(n); put(g, svg("line", { x1: x, y1: y, x2: nx, y2: ny, class: "hr-road-line" })); }
        put(g, svg("circle", { cx: x, cy: y, r: 8, stroke: color(s.owner), class: "hr-road-dot" }));
        put(structG, g);
      }

      // Units.
      for (const [uid, u] of Object.entries(game.units)) {
        const def = content.units[u.type];
        const [x, y] = center(u.at);
        const g = svg("g", { class: u.owner === you ? "hr-unit hr-mine" : "hr-unit" },
          svg("title", {}, `${def?.name || u.type} (${nameOf(u.owner)}) hp ${u.hp}/${u.maxHp}`),
          svg("circle", { cx: x, cy: y, r: SIZE * 0.42, fill: color(u.owner) }),
          svg("text", { x, y: y + 1, class: "hr-uicon" }, def?.icon || u.type.slice(0, 2)));
        if (u.maxHp <= 6) {
          const x0 = x - (u.maxHp - 1) * 3.5;
          for (let i = 0; i < u.maxHp; i++) put(g, svg("circle", { cx: x0 + i * 7, cy: y + SIZE * 0.62, r: 2.6, class: i < u.hp ? "hr-pip on" : "hr-pip" }));
        } else {
          put(g, svg("rect", { x: x - 14, y: y + SIZE * 0.55, width: 28, height: 4, class: "hr-hpback" }),
            svg("rect", { x: x - 14, y: y + SIZE * 0.55, width: 28 * u.hp / u.maxHp, height: 4, class: "hr-hpbar" }));
        }
        put(unitG, g);
      }

      // Your pending orders.
      if (!priv) return;
      const o = priv.orders, mine = color(you);
      for (const b of o.builds) {
        const def = content.structures[b.type];
        put(orderG, b.cells.map((k) => hexAt(k, SIZE * 0.9, { fill: mine, "fill-opacity": 0.25, stroke: mine, "stroke-width": 2.5, "stroke-dasharray": "5 4" })));
        const [x, y] = center(b.at);
        put(orderG, svg("text", { x, y: y + 1, class: "hr-icon hr-ghosttext" }, def?.icon || ""));
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
        const [x, y] = center(foot[0]);
        put(orderG, svg("text", { x, y: y + 1, class: "hr-icon hr-ghosttext" }, th.icon || "TH"));
      }
    }

    function setHighlights(next) {
      for (const k of Object.keys(hlClass)) if (!(k in next)) { hl[k]?.removeAttribute("class"); delete hlClass[k]; }
      for (const [k, c] of Object.entries(next)) {
        if (hlClass[k] === c || !hl[k]) continue;
        hl[k].setAttribute("class", `hr-hl-${c}`);
        hlClass[k] = c;
      }
    }

    function setGhost(g) {
      fill(ghostG);
      if (!g) return;
      const cls = g.ok ? "hr-ghost-ok" : "hr-ghost-bad";
      put(ghostG, g.cells.filter((k) => cells && k in cells).map((k) => hexAt(k, SIZE * 0.92, { class: cls })));
      if (g.label && g.cells[0] in (cells || {})) { const [x, y] = center(g.cells[0]); put(ghostG, svg("text", { x, y: y + 1, class: "hr-icon" }, g.label)); }
    }

    function flash(items) {
      for (const { at, kind } of items) {
        if (!cells || !(at in cells)) continue;
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

    applyView();
    return { draw, setHighlights, setGhost, flash, centre, fit };
  }

  window.HexMap = { create, util: { parse, key, add, neighbors, dist, center, DIRS } };
})();
