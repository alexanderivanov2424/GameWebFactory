/*
 * DOM panels: top bar (cycle, day bar, pause/speed, colony resources), left toolbar (tools,
 * priority, build menu, overlays), right panel (players, colonists, hover info, log).
 *   DC.panels.build(game)    builds the toolbar once (needs state.game.defs); safe to call again
 *   DC.panels.refresh()      updates everything from DC.lobby.state (game.js calls it at ~4 Hz)
 * Only AppDom.el / textContent: player names never go through innerHTML.
 */
(() => {
  const DC = (window.DC = window.DC || {});
  const { $, el } = AppDom;
  const sigs = new Map(); // container id -> signature of what it shows
  let built = false;

  const game = () => DC.lobby.state && DC.lobby.state.game;
  const isPlayer = () => Boolean(DC.lobby.me() && DC.lobby.me().player);
  const elName = (g, id) => (g.defs.elements[id] ? g.defs.elements[id].name : id);
  const data = (node, key, value) => { node.dataset[key] = value; return node; };
  const kgText = (kg) => (kg >= 100 ? Math.round(kg) : Math.round(kg * 10) / 10) + " kg";
  const costText = (g, cost) => Object.entries(cost || {}).map(([k, v]) => `${elName(g, k)} ${v}`).join(", ");

  // Rebuild `box` only when its signature changed (keeps buttons clickable between refreshes).
  function fill(id, sig, make) {
    const s = typeof sig === "string" ? sig : JSON.stringify(sig);
    if (sigs.get(id) === s) return;
    sigs.set(id, s);
    const box = $(id);
    box.replaceChildren(...make());
  }

  function toolButton(label, key, title) {
    return data(el("button", { className: "t", textContent: label, title,
      onclick: () => DC.tools.setTool(key) }), "tool", key);
  }

  function build(g) {
    if (built || !g || !g.defs) return;
    built = true;
    const T = DC.tools;
    $("tools").replaceChildren(
      toolButton("Inspect (I)", "inspect", "Look at things; no orders"),
      toolButton("Dig (G)", "dig", "Drag a rectangle to mark cells for digging"),
      toolButton("Cancel (C)", "cancel", "Drag a rectangle to cancel orders there"),
      toolButton("Deconstruct (X)", "deconstruct", "Drag a rectangle to take buildings apart"),
      toolButton("Priority (P)", "priority", "Drag a rectangle to set its priority"),
    );
    $("prios").replaceChildren(...[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) =>
      data(el("button", { className: "t", textContent: String(n),
        title: "Priority " + n + " (9 first)", onclick: () => T.setPrio(n) }), "prio", String(n))));
    const groups = {};
    for (const [id, d] of Object.entries(g.defs.buildings)) {
      if (d.buildable === false) continue;
      (groups[d.category || "other"] ||= []).push([id, d]);
    }
    const info = $("buildinfo");
    const showInfo = (id) => {
      const d = id && g.defs.buildings[id];
      info.textContent = d ? `${d.name} ${d.w}x${d.h}: ${d.description || ""} Cost: ${costText(g, d.cost)}.` : "";
    };
    const menu = $("buildmenu");
    menu.replaceChildren(...Object.entries(groups).map(([cat, list]) =>
      el("details", { open: cat === "base" },
        el("summary", {}, cat),
        ...list.map(([id, d]) => data(el("button", {
          className: "t", title: `${d.description || ""} (cost: ${costText(g, d.cost)})`,
          style: "display:block;width:100%;text-align:left;margin:2px 0",
          onclick: () => T.setBuilding(id),
          onmouseenter: () => showInfo(id), onmouseleave: () => showInfo(T.state.building),
        }, `${d.name} (${d.w}x${d.h})`, el("span", { className: "cost" }, costText(g, d.cost))), "building", id)))));
    $("overlays").replaceChildren(...DC.render.OVERLAYS.map((o) => data(el("button", {
      className: "t", textContent: o === "none" ? "None" : o[0].toUpperCase() + o.slice(1),
      onclick: () => { DC.view.overlay = o; DC.panels.refresh(); },
    }), "overlay", o)), el("div", { id: "ovlegend", className: "muted", style: "font-size:0.7rem;margin-top:4px" }));
    T.onChange(() => { showInfo(T.state.building); refresh(); });
    $("pause").onclick = () => {
      const gg = game();
      if (gg && isPlayer()) DC.tools.send({ action: "pause", paused: !gg.clock.paused });
    };
    $("speeds").replaceChildren(...[1, 2, 3].map((n) => data(el("button", { className: "t", textContent: n + "x",
      style: "margin-left:2px",
      onclick: () => isPlayer() && DC.tools.send({ action: "speed", speed: n }) }), "speed", String(n))));
    $("end").onclick = () => DC.lobby.sendGame({ action: "end" });
  }

  function mark(root, attr, value) {
    for (const b of root.querySelectorAll(`[data-${attr}]`)) b.classList.toggle("on", b.dataset[attr] === String(value));
  }

  function bar(value, max, good) {
    const f = Math.max(0, Math.min(1, value / max));
    const hue = good ? 120 * f : 120 * (1 - f);
    return el("div", { className: "bar", title: `${Math.round(value)} / ${max}` },
      el("div", { style: `width:${f * 100}%;background:hsl(${hue},65%,45%)` }));
  }

  function topbar(g) {
    const c = g.clock;
    const t = c.time % g.cycleLength;
    $("cycle").textContent = `Cycle ${c.cycle}`;
    $("daybar").firstChild.style.width = (100 * t / g.cycleLength).toFixed(1) + "%";
    $("pause").textContent = c.paused ? "Resume" : "Pause";
    $("pause").classList.toggle("on", c.paused);
    mark($("speeds"), "speed", c.speed);
    const res = Object.entries(g.colony).sort((a, b) => elName(g, a[0]).localeCompare(elName(g, b[0])));
    fill("res", res, () => res.map(([id, kg]) => el("span", { className: "r" },
      el("span", { className: "sw", style: `background:${(g.defs.elements[id] || {}).color || "#888"}` }),
      `${elName(g, id)} ${kgText(kg)}`)));
  }

  function sidePanels(g, state) {
    fill("plist", Object.entries(g.players).map(([id, p]) => [id, p.name, p.color]), () =>
      Object.entries(g.players).map(([id, p]) => el("div", {},
        el("span", { className: "sw", style: `background:${p.color}` }), " ", p.name, id === state.you ? " (you)" : "")));
    const dupes = Object.entries(g.dupes);
    fill("dupes", dupes, () => dupes.length === 0 ? [el("div", { className: "muted" }, "No colonists alive.")] :
      dupes.map(([id, d]) => el("div", { className: "dupe" },
        el("div", {}, el("span", { className: "nm" }, d.name), d.sick ? el("span", { className: "sick" }, " SICK") : ""),
        el("div", { className: "bars", title: "Breath, food, bladder, stress, health" },
          bar(d.breath, 100, true), bar(d.kcal, 4000, true), bar(d.bladder, 100, false),
          bar(d.stress, 100, false), bar(d.health, 100, true)),
        el("div", { className: "muted" }, d.task || "idle",
          d.carry ? ` · carrying ${kgText(d.carry.kg)} ${elName(g, d.carry.el)}` : ""))));
    const keys = Object.keys(g.log).map(Number).sort((a, b) => b - a);
    fill("log", keys.map((k) => g.log[k]), () => keys.map((k) => el("div", {}, g.log[k])));
    hover(g, state);
  }

  function buildingsAt(g, x, y) {
    const out = [];
    for (const [id, b] of Object.entries(g.buildings)) {
      const d = g.defs.buildings[b.t];
      if (d && x >= b.x && x < b.x + d.w && y >= b.y && y < b.y + d.h) out.push([id, b, d]);
    }
    return out;
  }

  function hover(g, state) {
    const h = DC.view.hover || DC.view.last;
    const cell = state.private && state.private.cell;
    const parts = [];
    if (h && cell && cell.x === h[0] && cell.y === h[1]) {
      const e = g.defs.elements[cell.el];
      parts.push({ cell: [cell.x, cell.y, e ? e.name : cell.el, cell.kg, cell.temp, cell.germs, cell.decor] });
    } else if (h) parts.push({ cell: [h[0], h[1]] });
    if (h) for (const [id, b, d] of buildingsAt(g, h[0], h[1])) parts.push({ id, b, d });
    const me = state.you;
    fill("hover", [parts.map((p) => p.cell || [p.id, p.b]), me], () => {
      if (!h) return [el("div", { className: "muted" }, "Point at the map.")];
      return parts.map((p) => {
        if (p.cell) {
          const c = p.cell;
          return el("div", {}, c.length < 3 ? `Cell ${c[0]}, ${c[1]}` :
            `Cell ${c[0]}, ${c[1]}: ${c[2]}, ${c[3]} kg, ${c[4]} °C, germs ${c[5]}, decor ${c[6]}`);
        }
        const { id, b, d } = p;
        const rows = [el("div", {}, el("b", {}, d.name), b.b ? " (built)" : ` (site ${b.p}%)`)];
        if (b.need) rows.push(el("div", {}, "Need: " + Object.entries(b.need).map(([k, v]) => `${elName(g, k)} ${v} kg`).join(", ")));
        if (b.st) rows.push(el("div", {}, "Status: " + b.st));
        if (b.store) rows.push(el("div", {}, "Store: " + Object.entries(b.store).map(([k, v]) => `${elName(g, k)} ${v} kg`).join(", ")));
        if (b.b && d.power && d.power.use) rows.push(el("div", {}, b.pw ? "Powered" : "No power"));
        if (b.b && d.kind !== "none") rows.push(el("div", {}, b.on ? "On" : "Off"));
        if (g.players[b.by]) rows.push(el("div", { className: "muted" }, "Placed by " + g.players[b.by].name + ` (priority ${b.prio})`));
        if (b.dc) rows.push(el("div", {}, "Marked for deconstruction"));
        return el("div", { style: "margin-top:6px" }, ...rows);
      });
    });
    // The on/off button lives in its own box, rebuilt only when its target or label changes,
    // so a status text changing every tick can't swallow the click.
    const sw = parts.find((p) => p.b && p.b.b && p.d.kind !== "none");
    fill("hoverActions", sw && isPlayer() ? [sw.id, sw.b.on] : null, () => !(sw && isPlayer()) ? [] :
      [el("button", { className: "t", textContent: sw.b.on ? "Turn off" : "Turn on",
        onclick: () => DC.tools.send({ action: "toggle", building: sw.id }) })]);
  }

  function legend() {
    const o = DC.view.overlay;
    const texts = { none: "", gas: "Gas overlay: colour = gas, brightness = amount.", temp: "Temperature: blue (cold) to red (hot).",
      germ: "Germs: darker to brighter green = more.", decor: "Decor: red (ugly) to green (pretty).",
      power: "Power: wires and power buildings (yellow dots = power ports).",
      plumbing: "Plumbing: pipes and ports (blue = in, orange = out)." };
    const box = $("ovlegend");
    if (box && box.textContent !== texts[o]) box.textContent = texts[o];
  }

  function refresh() {
    const state = DC.lobby && DC.lobby.state;
    const g = state && state.game;
    if (!g || !g.defs || state.phase === "lobby") return;
    build(g);
    topbar(g);
    sidePanels(g, state);
    mark($("tools"), "tool", DC.tools.state.tool);
    mark($("prios"), "prio", DC.tools.state.prio);
    mark($("buildmenu"), "building", DC.tools.state.tool === "build" ? DC.tools.state.building : "");
    mark($("overlays"), "overlay", DC.view.overlay);
    legend();
    $("end").hidden = state.phase !== "playing" || !DC.lobby.isHost();
    const fin = state.phase === "finished";
    $("result").hidden = !fin;
    $("result").textContent = fin ? (state.result && state.result.reason) || "The colony has ended." : "";
  }

  DC.panels = { build, refresh };
})();
