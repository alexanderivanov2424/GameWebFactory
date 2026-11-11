/*
 * Hex Realms: the HUD panels around the map, all built from the state (no rules here).
 *
 *   HexHud.topbar(el, ctx)      turn, countdown (#hr-timer, ticked by game.js), resources (+net), people and
 *                               builders, Jobs off / Jobs on (every structure with workers), End turn
 *   HexHud.players(el, ctx)     colour, name, score, done tick, out, public resource snapshot
 *   HexHud.selection(el, ctx)   the selected unit / structure / construction site: stats, orders,
 *                               Recruit/Hold/Shoot/Found/Disband/Switch off/Demolish
 *   HexHud.orders(el, ctx)      your pending builds / recruits / research, each with a cancel button, and your
 *                               construction sites (progress, whether builders work there this turn, demolish)
 *   HexHud.trade(el, ctx)       give/get selects (only when the market rate is > 0)
 *   HexHud.build(el, ctx)       one button per buildable structure (starts build mode)
 *   HexHud.fmt                  small text helpers shared with panels.js (cost, nameSpan, resource icons);
 *                               fmt.setResources(content.resourceInfo) first (game.js does, each render)
 *
 * ctx = { game, priv, you, me (public player entry), content, ui, act } where ui is the page's
 * persistent UI state ({sel, mode, trade}) and act = { send(msg), select(kind, id), setMode(mode), centre(key) }.
 * Every function replaces the children of its element, so call them on each render.
 */
(() => {
  const { el, fill } = AppDom;
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  let RES = {};  // {res: {name, icon}} from the content
  const setResources = (info) => { RES = info || {}; };
  const resIcon = (r) => RES[r]?.icon || r;
  const resName = (r) => RES[r]?.name || cap(r);
  const costText = (cost) => Object.entries(cost || {}).map(([r, n]) => `${n}${resIcon(r)}`).join(" ") || "free";
  const canPay = (ctx, cost) => Object.entries(cost || {}).every(([r, n]) => (ctx.priv.res[r] || 0) >= n);
  const nameSpan = (game, pid) => {
    const p = game.players[pid];
    return el("span", { className: "hr-pname", style: `color:${p?.color || "#ccc"}` }, p?.name || pid || "?");
  };
  const signed = (n) => (n > 0 ? `+${n}` : `${n}`);
  const btn = (text, onclick, opts = {}) => {
    const b = el("button", { className: `hr-btn ${opts.cls || ""}`, onclick, disabled: !!opts.disabled, title: opts.title || "" }, text);
    return b;
  };
  const stat = (label, value) => el("span", { className: "hr-stat" }, `${label} `, el("b", {}, String(value)));

  function topbar(box, ctx) {
    const { game, priv } = ctx;
    const rep = priv.report;
    const chips = ctx.content.resources.map((r) => {
      const net = rep.net[r] || 0;
      const capped = rep.caps[r];
      const full = capped !== undefined && priv.res[r] >= capped;
      return el("span", { className: `hr-chip hr-res-${r}${full ? " full" : ""}`, title: `${resName(r)}: income ${rep.income[r] || 0}, upkeep ${rep.upkeep[r] || 0}${capped !== undefined ? `, storage ${capped}` : ""}${(rep.wasted || {})[r] ? `, ${rep.wasted[r]} won't fit in your stores (lost)` : ""}` },
        el("span", { className: "hr-ricon" }, resIcon(r)), " ", el("b", {}, String(priv.res[r])), capped !== undefined ? el("small", {}, `/${capped}`) : null,
        el("span", { className: net < 0 ? "neg" : net > 0 ? "pos" : "" }, ` (${signed(net)})`));
    });
    const done = priv.done;
    const end = btn(done ? "Waiting for others… (undo)" : "End turn", () => ctx.act.send({ action: "done", done: !done }), { cls: done ? "waiting" : "endturn" });
    fill(box, 
      el("span", { className: "hr-turn" }, `Turn ${game.turn} / ${game.turnLimit}`),
      game.turnSeconds > 0 ? el("span", { id: "hr-timer", className: "hr-timer" }) : null,
      el("span", { className: "hr-chips" }, chips),
      el("span", { className: "hr-people", title: `Population ${priv.pop}, housing ${rep.housing}: ${rep.workers} in jobs, ${rep.builders} building, ${rep.idle} idle.${rep.growth ? "" : `\nNo growth this turn: ${rep.growthWhy}`}` },
        el("span", { className: "hr-ricon" }, resIcon("people")), " ", el("b", {}, String(priv.pop)), ` / ${rep.housing} (jobs ${rep.workers}`,
        rep.builders ? `, building ${rep.builders}` : "", `, idle ${rep.idle})`,
        rep.growth ? el("span", { className: "pos" }, ` growth +${rep.growth}`) : null),
      btn("Jobs off", () => ctx.act.send({ action: "staff", on: false }), { cls: "small", title: "Switch off every structure with workers: they become idle and build your construction sites." }),
      btn("Jobs on", () => ctx.act.send({ action: "staff", on: true }), { cls: "small", title: "Switch every structure with workers back on." }),
      el("span", { className: "spacer" }), end);
  }

  function players(box, ctx) {
    const { game } = ctx;
    fill(box, el("h3", {}, "Realms"), game.seats.map((pid) => {
      const p = game.players[pid];
      const r = p.res || {};
      return el("div", { className: `hr-player${p.alive ? "" : " out"}${pid === ctx.you ? " me" : ""}` },
        el("div", { className: "row" },
          el("span", { className: "hr-dot", style: `background:${p.color}` }), nameSpan(game, pid), pid === ctx.you ? el("span", { className: "muted small" }, " (you)") : (game.bots || []).includes(pid) ? el("span", { className: "muted small" }, " (bot)") : null,
          el("span", { className: "spacer" }),
          !p.alive ? el("span", { className: "hr-outtag" }, "out") : p.done ? el("span", { className: "hr-tick", title: "Ended their turn" }, "✓") : null,
          el("b", { title: "Score" }, String(p.score))),
        el("div", { className: "hr-psub", title: `Start of this turn: ${["gold", "food", "wood", "stone", "metal"].map((k) => `${resName(k)} ${r[k] ?? 0}`).join(", ")}, ${resName("people")} ${p.pop ?? 0}` },
          ["gold", "food", "wood", "stone", "metal"].map((k) => `${resIcon(k)}${r[k] ?? 0}`).join(" ") + ` · ${resIcon("people")}${p.pop ?? 0} · ${(p.advances || []).length} adv`));
    }));
  }

  function unitStats(def) {
    return el("div", { className: "hr-stats" }, stat("atk", def.attack), stat("def", def.defense), stat("hp", def.hp), stat("move", def.move),
      def.range ? stat("range", def.range) : null, def.siege > 1 ? stat("siege", def.siege) : null);
  }

  function selection(box, ctx) {
    const { game, priv, content, ui, act } = ctx;
    const sel = ui.sel;
    if (!sel) return fill(box, el("h3", {}, "Selection"), el("p", { className: "muted small" }, "Click one of your units or structures to command it, or any enemy to inspect it."));
    if (sel.kind === "unit") {
      const u = game.units[sel.id], def = u && content.units[u.type];
      if (!def) return fill(box);
      const own = u.owner === ctx.you, o = priv.orders;
      const kids = [el("h3", {}, `${def.name} `, nameSpan(game, u.owner)), unitStats(def), el("p", { className: "small" }, `HP ${u.hp}/${u.maxHp}. ${def.text || ""}`)];
      if (own) {
        const exploring = (priv.exploring || []).includes(sel.id);
        const pending = exploring ? "Exploring (walks on its own each turn; any other order stops it)" : o.moves[sel.id] ? `Moving to ${o.moves[sel.id][o.moves[sel.id].length - 1]}` : o.shots[sel.id] ? `Shooting at ${o.shots[sel.id]}`
          : sel.id in o.found ? "Founding a city" : o.holds.includes(sel.id) ? "Holding position" : "No orders";
        const hold = o.holds.includes(sel.id);
        const found = priv.found[sel.id] || [];
        const row = el("div", { className: "hr-btnrow" },
          btn(hold ? "Hold (on)" : "Hold", () => act.send({ action: "hold", unit: sel.id }), { cls: hold ? "on" : "", title: "Roll one extra defence die this turn instead of moving." }),
          game.fog && !def.settler ? btn(exploring ? "Explore (on)" : "Explore", () => act.send({ action: "explore", unit: sel.id }), { cls: exploring ? "on" : "", title: "Walk around on its own every turn to clear the fog, until you give it another order." }) : null,
          def.range ? btn("Shoot", () => act.setMode({ type: "shoot", unit: sel.id }), { cls: ui.mode?.type === "shoot" ? "on" : "", title: `Shoot a unit or structure up to ${def.range} cells away.` }) : null,
          def.settler ? btn("Found city", () => act.setMode({ type: "found", unit: sel.id, rot: found[0] }), { disabled: !found.length, cls: ui.mode?.type === "found" ? "on" : "", title: found.length ? "Found a Town Hall here." : "Can't found a city here." }) : null,
          btn("Clear orders", () => act.send({ action: "move", unit: sel.id, to: u.at })),
          btn("Disband", () => { if (confirm(`Disband this ${def.name}?`)) act.send({ action: "disband", unit: sel.id }); }, { cls: "danger" }));
        kids.push(el("p", { className: "hr-pending" }, pending), row,
          el("p", { className: "muted small" }, "Click a highlighted cell to move there (red = attack). Click the unit again to clear."));
      }
      return fill(box, ...kids);
    }
    if (sel.kind === "site") return site(box, ctx);
    const s = game.structures[sel.id], def = s && content.structures[s.type];
    if (!def) return fill(box);
    const own = s.owner === ctx.you;
    const kids = [el("h3", {}, `${def.name} `, nameSpan(game, s.owner)),
      el("p", { className: "small" }, s.maxHp ? `HP ${s.hp}/${s.maxHp}. ` : "", def.text || "")];
    if (def.jobs || Object.keys(def.produce || {}).length) {
      kids.push(el("p", { className: `small ${s.working ? "pos" : "neg"}` }, s.working ? "Working." : s.active === false ? "Switched off." : "Not working: no free workers."));
    }
    if (own) {
      const store = priv.stores[sel.id];
      if (store) kids.push(el("p", { className: "small" }, `Holds ${Object.entries(store.cap).map(([r, n]) => `${r} ${store.stock[r] || 0}/${n}`).join(", ")}.`));
    }
    if (own) {
      const recruits = priv.recruit[sel.id] || {};
      for (const [ut, why] of Object.entries(recruits)) {
        const ud = content.units[ut];
        if (!ud) continue;
        kids.push(el("div", { className: "hr-recruit" },
          btn(`Recruit ${ud.name}`, () => act.send({ action: "recruit", structure: sel.id, kind: ut }), { disabled: !!why, title: why || ud.text || "" }),
          el("span", { className: "small" }, costText(ud.cost)),
          el("div", { className: "muted small" }, `atk ${ud.attack} def ${ud.defense} hp ${ud.hp} move ${ud.move}${ud.range ? ` range ${ud.range}` : ""}${why ? ` — ${why}` : ""}`)));
      }
      const row = el("div", { className: "hr-btnrow" },
        def.jobs > 0 ? btn(s.active === false ? "Switch on" : "Switch off", () => act.send({ action: "toggle", structure: sel.id }), { title: "Switched-off structures don't use workers." }) : null,
        s.type !== "town_hall" ? btn("Demolish", () => { if (confirm(`Demolish this ${def.name}? No refund, and goods stored in it are lost.`)) act.send({ action: "demolish", structure: sel.id }); }, { cls: "danger", title: "Remove it now (no refund)." }) : null);
      kids.push(row);
    }
    fill(box, ...kids);
  }

  function siteText(ctx, cid, x) {
    const works = (ctx.priv.building?.works || []).includes(cid);
    return `${x.done}/${x.turns} turns, ${x.builders} builder${x.builders > 1 ? "s" : ""} a turn — ${x.done >= x.turns ? "finishing (blocked by an enemy unit)" : works ? "building this turn" : "waiting for idle people"}`;
  }

  function site(box, ctx) {
    const { game, content, ui, act } = ctx;
    const x = game.sites[ui.sel.id], def = x && content.structures[x.type];
    if (!def) return fill(box);
    const own = x.owner === ctx.you;
    fill(box, el("h3", {}, `${def.name} (under construction) `, nameSpan(game, x.owner)),
      el("p", { className: "small" }, own ? siteText(ctx, ui.sel.id, x) : `${x.done}/${x.turns} turns of work done.`),
      own ? el("p", { className: "muted small" }, "Each turn of work needs its builders: people without a job, given to the oldest site first. Switch structures off to free them.") : null,
      own ? btn("Demolish", () => act.send({ action: "demolish", structure: ui.sel.id }), { cls: "danger", title: "Take the site down and get its cost back." }) : null);
  }

  function orders(box, ctx) {
    const { priv, content, game, act } = ctx;
    const o = priv.orders;
    const rows = [
      ...o.builds.map((b) => [b.id, `Build ${content.structures[b.type]?.name || b.type}`, b.cost]),
      ...(o.claims || []).map((c) => [c.id, `Claim land @${c.at}`, c.cost]),
      ...o.recruits.map((r) => [r.id, `Recruit ${content.units[r.type]?.name || r.type} at ${content.structures[game.structures[r.at]?.type]?.name || "?"}`, r.cost]),
      ...o.research.map((r) => [r.id, `Research ${content.advances[r.advance]?.name || r.advance}`, r.cost]),
    ];
    const sites = Object.entries(game.sites || {}).filter(([, x]) => x.owner === ctx.you);
    fill(box, el("h3", {}, "Orders"), rows.length ? rows.map(([id, text, cost]) =>
      el("div", { className: "row hr-order" }, el("span", { className: "small" }, text, el("span", { className: "muted" }, ` (${costText(cost)})`)),
        el("span", { className: "spacer" }), btn("✕", () => act.send({ action: "cancel", order: id }), { cls: "small", title: "Cancel and refund" }))) : el("p", { className: "muted small" }, "Nothing queued."),
      sites.length ? el("h3", {}, "Construction") : null,
      sites.map(([cid, x]) => el("div", { className: "row hr-order" },
        el("span", { className: "small", style: "cursor:pointer", onclick: () => act.select("site", cid) }, content.structures[x.type]?.name || x.type, el("span", { className: "muted" }, ` ${siteText(ctx, cid, x)}`)),
        el("span", { className: "spacer" }), btn("✕", () => act.send({ action: "demolish", structure: cid }), { cls: "small", title: "Demolish the site and get its cost back" }))));
  }

  function trade(box, ctx) {
    const rate = ctx.priv.report.tradeRate;
    box.hidden = !(rate > 0);
    if (box.hidden) return;
    const t = ctx.ui.trade;
    const resOpts = (value) => ["gold", "food", "wood", "stone", "metal"].map((r) => el("option", { value: r, selected: r === value }, `${resIcon(r)} ${resName(r)}`));
    const give = el("select", { onchange: () => { t.give = give.value; } }, resOpts(t.give));
    const get = el("select", { onchange: () => { t.get = get.value; } }, resOpts(t.get));
    fill(box, el("h3", {}, "Trade"), el("div", { className: "row" }, "give", give, "get", get),
      el("div", { className: "row" }, el("span", { className: "small muted" }, `Give ${rate} for 1`), el("span", { className: "spacer" }),
        btn("Trade", () => ctx.act.send({ action: "trade", give: t.give, get: t.get }), { disabled: t.give === t.get })));
  }

  function build(box, ctx) {
    const { content, me, ui, act } = ctx;
    const mine = new Set(me.advances || []);
    const buildable = Object.entries(content.structures).filter(([id]) => id !== "town_hall");
    const cats = Object.entries(content.categories || {}).filter(([c]) => buildable.some(([, d]) => d.category === c));
    // One category open at a time; clicking the open one closes it. Switching cancels a placement.
    const pick = (c) => { ui.buildCat = ui.buildCat === c ? null : c; act.setMode(ui.mode?.type === "build" ? null : ui.mode); };
    const tabs = el("div", { className: "hr-cats" }, cats.map(([c, label]) =>
      el("button", { className: `hr-cat${ui.buildCat === c ? " on" : ""}`, onclick: () => pick(c) }, label)));
    const items = buildable.filter(([, d]) => d.category === ui.buildCat).map(([id, d]) => {
      let why = "";
      if (d.requires && !mine.has(d.requires)) why = `Needs ${content.advances[d.requires]?.name || d.requires}`;
      const poor = !why && !canPay(ctx, d.cost);
      const info = [d.text, `Build: ${d.buildTurns} turn${d.buildTurns > 1 ? "s" : ""}, ${d.builders} builder${d.builders > 1 ? "s" : ""} each turn`, d.jobs ? `Jobs: ${d.jobs}` : "", Object.keys(d.produce || {}).length ? `Produces: ${costText(d.produce)}` : "", d.housing ? `Housing: ${d.housing}` : "",
        `Terrain: ${(d.terrain || []).map((t) => content.terrain[t]?.name || t).join(", ")}`, d.coast ? "Must touch water." : "", `${d.cells.length} cell${d.cells.length > 1 ? "s" : ""}`]
        .filter(Boolean).join("\n");
      const active = ui.mode?.type === "build" && ui.mode.kind === id;
      return el("button", { className: `hr-build${active ? " on" : ""}`, disabled: !!why || poor, title: `${why ? `${why}\n` : poor ? "Can't afford\n" : ""}${info}`,
        onclick: () => (active ? act.setMode(null) : act.setMode({ type: "build", kind: id, rot: ui.lastRot || 0 })) },
        el("span", { className: "hr-bicon" }, d.icon || "▪"), el("span", { className: "hr-bname" }, d.name), el("span", { className: "hr-bcost small" }, why || costText(d.cost)));
    });
    const claiming = ui.mode?.type === "claim", claimCost = content.claim?.cost || {};
    const claim = btn(claiming ? "Extending territory… (Esc)" : `Extend territory (${costText(claimCost)})`,
      () => act.setMode(claiming ? null : { type: "claim" }),
      { cls: claiming ? "on" : "", disabled: !claiming && !canPay(ctx, claimCost), title: "Claim an explored cell next to your land, with its free neighbours, at the end of the turn. Land is first come, first served; cells two realms reach at once go to nobody." });
    fill(box, el("div", { className: "hr-btnrow" }, claim), tabs,
      ui.buildCat ? el("div", { className: "hr-buildgrid" }, items) : el("p", { className: "muted small" }, "Pick a category, then a structure."),
      el("p", { className: "muted small" }, "Click the map to place it. R or right-click turns it, Esc cancels. It goes anywhere inside your territory and becomes a construction site that idle people build over a few turns. Goods go straight to your stores."));
  }

  window.HexHud = { topbar, players, selection, orders, trade, build, fmt: { costText, canPay, nameSpan, btn, cap, setResources, resIcon, resName } };
})();
