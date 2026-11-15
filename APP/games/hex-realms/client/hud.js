/*
 * Hex Realms HUD: the panels around the map (top bar, players, selection, orders, trade, build menu), built from state.
 * No rules here. Each function replaces its element's children, so call it on every render.
 *
 * HexHud.topbar(el, ctx)      turn, timer, resources, people, population, housing, End turn
 * HexHud.players(el, ctx)     players: colour, name, score, done, public resources
 * HexHud.selection(el, ctx)   the selected unit, structure or site, with its actions
 * HexHud.orders(el, ctx)      pending builds, recruits, research, construction sites
 * HexHud.trade(el, ctx)       market give/get selects
 * HexHud.build(el, ctx)       build menu buttons
 * HexHud.structCard(content, def, hp?, res?)  structure card (footprint, text, output, effects)
 * HexHud.fmt                  text helpers shared with panels.js (costs, icons, structInfo, resListEl); call setResources first
 * ctx = { game, priv, you, me, content, ui, act }; game.js fills the top bar's .hr-delta-<key> slots
 */
(() => {
  const { el, svg, fill } = AppDom;
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  let RES = {};  // {res: {name, icon}} from the content
  const setResources = (info) => { RES = info || {}; };
  const resIcon = (r) => RES[r]?.icon || r;
  const resName = (r) => RES[r]?.name || cap(r);
  const costText = (cost) => Object.entries(cost || {}).map(([r, n]) => `${n}${resIcon(r)}`).join(" ") || "free";
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const names = (content, kind, ids) => ids.map((id) => content[kind][id]?.name || id).join(", ");
  // Output and jobs as one list, e.g. "(+1 🪵, −1 👥)"; res is a real or previewed output, else the base output.
  const order = (r) => { const i = Object.keys(RES).indexOf(r); return i < 0 ? 99 : i; };
  const resItems = (res) => Object.entries(res || {}).filter(([, n]) => n).sort((a, b) => order(a[0]) - order(b[0]))
    .map(([r, n]) => [`${n > 0 ? "+" : "−"}${Math.abs(n)} ${resIcon(r)}`, n > 0 ? "pos" : "neg"]);
  function resList(d, res = null) {
    const terrain = Object.entries(d.onTerrain || {});
    let items;
    if (res || !terrain.length) items = resItems(res || d.produce);
    else items = [[terrain.map(([t, out]) => `${resItems(out).map((i) => i[0]).join(" ")} on ${t}`).join(" or "), "pos"]];
    if (d.jobs) items.push([`−${d.jobs} ${resIcon("people")}`, "neg"]);
    return items;
  }
  const resListText = (d, res = null) => { const items = resList(d, res); return items.length ? `(${items.map((i) => i[0]).join(", ")})` : ""; };
  const resListEl = (d, res = null) => {
    const items = resList(d, res);
    return items.length ? ["(", ...items.flatMap(([t, cls], i) => [i ? ", " : null, el("span", { className: cls }, t)]), ")"] : [];
  };
  // What a structure does and where it may go, read from its content (the server's rules decide).
  function structInfo(content, d) {
    const stats = [];
    if (d.housing) stats.push(`Housing ${d.housing}`);
    if (d.storage) stats.push(`Stores ${d.storage} of each good`);
    if (Object.keys(d.store || {}).length) stats.push(`Stores ${costText(d.store)}`);
    if (d.trade) stats.push(`Trade ${d.trade}:1`);
    if ((d.recruits || []).length) stats.push(`Trains ${names(content, "units", d.recruits)}`);
    if (d.heals) stats.push("Heals units on or next to it");
    if (d.shoots) stats.push(`Shoots ${plural(d.shoots, "die")} (range ${d.range})`);
    if (d.score) stats.push(`+${d.score} score`);
    const hp = d.hp ? `HP ${d.hp}${d.defense ? ` · defense ${d.defense}` : ""}` : "Can't be attacked";
    const terrains = names(content, "terrain", d.terrain || []) + (d.coast ? " · touching water" : "");
    const build = `${costText(d.cost)} · 🔨 ${d.hammers} (each idle person builds 1 🔨 a turn)`;
    const byTag = (d.perAdjacent || []).filter((a) => a.tag).flatMap((a) => Object.entries(a.gain || {}).map(([res, n]) => ({ n, res, tag: a.tag })));
    return { text: HexText.structures[d.id] || "", res: resListText(d), stats, hp, terrains, build, tags: d.tags || [], byTag };
  }

  // Footprint picture (unturned) in the structure's colour, with its icon.
  function structPicture(d, px = 64) {
    const { center, key } = HexMap.util, s = 30;
    const cs = d.cells.map(([q, r]) => center(key(q, r)));
    const corners = ([x, y]) => Array.from({ length: 6 }, (_, i) => {
      const a = (Math.PI / 180) * (60 * i - 30);
      return [x + s * Math.cos(a), y + s * Math.sin(a)];
    });
    const all = cs.flatMap(corners);
    const xs = all.map((p) => p[0]), ys = all.map((p) => p[1]);
    const [x0, y0, x1, y1] = [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
    const mid = [cs.reduce((a, p) => a + p[0], 0) / cs.length, cs.reduce((a, p) => a + p[1], 0) / cs.length];
    return svg("svg", { viewBox: `${(x0 - 2).toFixed(1)} ${(y0 - 2).toFixed(1)} ${(x1 - x0 + 4).toFixed(1)} ${(y1 - y0 + 4).toFixed(1)}`, width: px, height: px, class: "hr-spic" },
      ...cs.map((c) => svg("polygon", { points: corners(c).map((p) => p.map((v) => v.toFixed(1)).join(",")).join(" "), fill: d.color || "#888", stroke: "#10131a", "stroke-width": 2 })),
      svg("text", { x: mid[0].toFixed(1), y: mid[1].toFixed(1), "font-size": 34, "text-anchor": "middle", "dominant-baseline": "central" }, d.icon || ""));
  }

  const pip = (content, tag) => {
    const t = content.tags?.[tag] || { name: tag, color: "#666" };
    return el("span", { className: "hr-pip", style: `background:${t.color}` }, t.name);
  };
  const tagLine = (content, b) => el("li", { title: `${b.n > 0 ? "+" : "−"}${Math.abs(b.n)} ${resName(b.res).toLowerCase()} for each of your ${content.tags?.[b.tag]?.name || b.tag} structures next to it` },
    el("span", { className: b.n > 0 ? "pos" : "neg" }, `${b.n > 0 ? "+" : "−"}${Math.abs(b.n)} ${resIcon(b.res)}`), " for ", pip(content, b.tag));

  function structCard(content, d, hp, res = null) {
    const si = structInfo(content, d);
    return el("div", { className: "hr-scard" }, structPicture(d), el("div", { className: "hr-shp" }, hp || si.hp),
      si.tags.length ? el("div", { className: "hr-pips" }, si.tags.map((t) => pip(content, t))) : null,
      si.text ? el("div", { className: "hr-stext" }, si.text) : null,
      si.res ? el("div", { className: "hr-sres", title: "What it makes (+) and uses (−) a turn while it works; 👥 = the people working in it." }, ...resListEl(d, res)) : null,
      el("ul", { className: "hr-sstats" }, si.byTag.map((b) => tagLine(content, b)), si.stats.map((t) => el("li", {}, t))));
  }
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
  const VIEW_TIP = "Click: show on the map what makes and uses it each turn.\n";

  // A chip with an empty delta line below it, filled by game.js while placing.
  const withDelta = (key, chip) => el("span", { className: "hr-dcol" }, chip, el("span", { className: `hr-delta hr-delta-${key}` }));

  function topbar(box, ctx) {
    const { game, priv } = ctx;
    const rep = priv.report;
    const st = rep.starve || {};
    const starving = [st.units ? `${st.units} unit${st.units === 1 ? "" : "s"}` : "", st.people ? `${st.people} ${st.people === 1 ? "person" : "people"}` : ""].filter(Boolean).join(", ");
    const chips = ctx.content.resources.map((r) => {
      const net = rep.net[r] || 0;
      const capped = rep.caps[r];
      const full = capped !== undefined && priv.res[r] >= capped;
      return withDelta(r, el("span", { className: `hr-chip hr-res-${r}${full ? " full" : ""}${ctx.ui.resView === r ? " on" : ""}`, onclick: () => ctx.act.resView(r), title: `${VIEW_TIP}${resName(r)}: income ${rep.income[r] || 0}, upkeep ${rep.upkeep[r] || 0}${r === "gold" && rep.land ? ` (${rep.land} cells of bought land)` : ""}${capped !== undefined ? `, storage ${capped}` : ""}${r === "food" ? `.\nEveryone eats this turn's production first, then your stores. Production left over becomes new people while housing has room; only the rest goes into your stores. In brackets: how your stored food changes this turn` : ""}${(rep.wasted || {})[r] ? `, ${rep.wasted[r]} won't fit in your stores at the end of the turn (lost)` : ""}` },
        el("span", { className: "hr-ricon" }, resIcon(r)), " ", el("b", {}, String(priv.res[r])), capped !== undefined ? el("small", {}, `/${capped}`) : null,
        el("span", { className: net < 0 ? "neg" : net > 0 ? "pos" : "" }, ` (${signed(net)})`)));
    });
    const done = priv.done;
    const end = btn(done ? "Waiting for others… (undo)" : "End turn", () => ctx.act.send({ action: "done", done: !done }), { cls: done ? "waiting" : "endturn" });
    fill(box, 
      el("span", { className: "hr-turn" }, `Turn ${game.turn} / ${game.turnLimit}`),
      game.turnSeconds > 0 ? el("span", { id: "hr-timer", className: "hr-timer" }) : null,
      el("span", { className: "hr-chips" }, chips),
      withDelta("people", el("span", { className: `hr-people${ctx.ui.resView === "people" ? " on" : ""}`, onclick: () => ctx.act.resView("people"), title: `Click: show on the map where your people are (green idle, red in jobs / units, blue building).\n${rep.idle} idle. Population ${priv.pop + rep.soldiers}: ${rep.workers} in jobs, ${rep.builders} building, ${rep.soldiers} in units (and recruits), ${rep.idle} idle.` },
        el("span", { className: "hr-ricon" }, resIcon("people")), " idle ", el("b", {}, String(rep.idle)),
        starving ? el("span", { className: "neg", title: "This turn's food production plus your stored food can't feed everyone: whoever can't eat dies at the end of the turn, units first (newest first), then people." }, ` ⚠ starving: ${starving}`) : null)),
      withDelta("population", el("span", { className: `hr-people${ctx.ui.resView === "population" ? " on" : ""}`, onclick: () => ctx.act.resView("population"), title: `Click: show on the map how many people live in each structure that gives housing (living / housing).\nPopulation ${priv.pop + rep.soldiers}: ${priv.pop} people and ${rep.soldiers} in units (and recruits).\nIt grows to match your food production: production left after everyone eats becomes new people at once while housing has room. When production falls short, your stored food feeds everyone; once that runs out, whoever can't eat dies, units first.${rep.popNet ? `\nEnd of this turn: ${signed(rep.popNet)}.` : ""}` },
        el("span", { className: "hr-ricon" }, resIcon("population")), " population ", el("b", {}, String(priv.pop + rep.soldiers)),
        el("span", { className: rep.popNet < 0 ? "neg" : rep.popNet > 0 ? "pos" : "" }, ` (${signed(rep.popNet || 0)})`))),
      withDelta("housing", el("span", { className: `hr-people${priv.pop + rep.soldiers >= rep.housing ? " full" : ""}${ctx.ui.resView === "housing" ? " on" : ""}`, onclick: () => ctx.act.resView("housing"), title: `Click: show on the map which structures give housing.\nHousing ${rep.housing}: the population cap. Your people and the people in your units (${priv.pop + rep.soldiers}) must fit in it: no new people join once it's full.` },
        el("span", { className: "hr-ricon" }, resIcon("housing")), " cap ", el("b", {}, String(rep.housing)))),
      withDelta("turns", null),
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

  // A unit's stats as chips: attack, defence, move, hp, range and siege if any, then food eaten per turn.
  const UNIT_STATS = [["attack", "⚔️", "Attack: dice it rolls when it attacks"], ["defense", "🛡️", "Defence: dice it rolls when attacked"],
    ["move", "👣", "Movement: steps a turn"], ["hp", "❤️", "Health"], ["range", "🏹", "Range: shoots this far instead of moving"],
    ["siege", "💥", "Siege: damage per hit on structures"]];
  function unitStats(def, hp) {
    return el("div", { className: "hr-ustats" }, UNIT_STATS.filter(([k]) => (k === "range" ? def.range : k === "siege" ? def.siege > 1 : true))
      .map(([k, icon, title]) => el("span", { className: "hr-chip hr-ustat", title }, `${icon} `, el("b", {}, String(k === "hp" && hp ? hp : def[k])))),
      ((food) => el("span", { className: "hr-chip hr-ustat", title: "Food it eats each turn (from this turn's food production)" },
        el("b", {}, food ? `−${food}` : "0"), ` ${resIcon("food")}`))(def.upkeep?.food || 0));
  }

  function selection(box, ctx) {
    const { game, priv, content, ui, act } = ctx;
    const sel = ui.sel;
    if (!sel) return fill(box, el("h3", {}, "Selection"), el("p", { className: "muted small" }, "Click one of your units or structures to command it, or any enemy to inspect it."));
    if (sel.kind === "unit") {
      const u = game.units[sel.id], def = u && content.units[u.type];
      if (!def) return fill(box);
      const own = u.owner === ctx.you, o = priv.orders;
      const kids = [el("h3", {}, `${def.name} `, nameSpan(game, u.owner)), unitStats(def, `${u.hp}/${u.maxHp}`)];
      if (own) {
        const auto = priv.auto?.[sel.id] || null, mode = auto?.mode;
        const standing = { explore: "Exploring (walks on its own each turn)", fight: "Fighting (attacks the nearest enemy unit it sees; holds when none)",
          pillage: "Pillaging (attacks the nearest enemy structure it sees, fighting enemy units that come close first; holds when none)",
          travel: `Travelling to ${auto?.goal} over several turns` };
        const pending = mode ? `${standing[mode]}; any other order stops it` : o.moves[sel.id] ? `Moving to ${o.moves[sel.id][o.moves[sel.id].length - 1]}` : o.shots[sel.id] ? `Shooting at ${o.shots[sel.id]}`
          : sel.id in o.found ? "Founding a city" : o.holds.includes(sel.id) ? "Holding position" : "No orders";
        const hold = o.holds.includes(sel.id) && !mode;
        const found = priv.found[sel.id] || [];
        // A command deselects the unit; Clear orders keeps it selected.
        const command = (msg) => { act.send(msg); act.select(null); };
        const autoBtn = (m, label, title) => btn(mode === m ? `${label} (on)` : label, () => command({ action: "auto", unit: sel.id, mode: m }), { cls: mode === m ? "on" : "", title });
        // Each action has a short description beside it.
        const action = (b, text) => b && [b, el("span", { className: "small muted" }, text)];
        const row = el("div", { className: "hr-actions" },
          action(btn(hold ? "Hold (on)" : "Hold", () => command({ action: "hold", unit: sel.id }), { cls: hold ? "on" : "", title: "Roll one extra defence die this turn instead of moving." }),
            "Stay put this turn and defend with +1 die."),
          game.fog && !def.settler ? action(autoBtn("explore", "Explore", "Walk around on its own every turn to clear the fog, until you give it another order."),
            "Every turn: walk into the fog on its own.") : null,
          !def.settler ? action(autoBtn("fight", "Fight", "Every turn, attack the nearest enemy unit you can see (hold when there's none), until you give it another order."),
            "Every turn: attack the nearest enemy unit in sight.") : null,
          !def.settler ? action(autoBtn("pillage", "Pillage", "Every turn, attack the nearest enemy structure you can see, but fight enemy units that come close first (hold when there's nothing), until you give it another order."),
            "Every turn: attack the nearest enemy structure in sight.") : null,
          def.range ? action(btn("Shoot", () => act.setMode({ type: "shoot", unit: sel.id }), { cls: ui.mode?.type === "shoot" ? "on" : "", title: `Shoot a unit or structure up to ${def.range} cells away.` }),
            `Pick a target up to ${def.range} cells away instead of moving.`) : null,
          def.settler ? action(btn("Found city", () => act.setMode({ type: "found", unit: sel.id, rot: found[0] }), { disabled: !found.length, cls: ui.mode?.type === "found" ? "on" : "", title: found.length ? "Found a Town Hall here." : "Can't found a city here." }),
            found.length ? "Build a Town Hall where it stands." : "Can't found a city here.") : null,
          action(btn("Clear orders", () => act.send({ action: "move", unit: sel.id, to: u.at })), "Cancel this unit's orders (it stays put)."),
          action(btn("Disband", () => { if (confirm(`Disband this ${def.name}?`)) act.send({ action: "disband", unit: sel.id }); }, { cls: "danger" }),
            "Remove the unit; its people come home."));
        kids.push(el("p", { className: "hr-pending" }, pending), row);
      }
      return fill(box, ...kids);
    }
    if (sel.kind === "site") return site(box, ctx);
    const s = game.structures[sel.id], def = s && content.structures[s.type];
    if (!def) return fill(box);
    const own = s.owner === ctx.you;
    const kids = [el("h3", {}, `${def.name} `, nameSpan(game, s.owner)),
      structCard(content, def, s.maxHp ? `HP ${s.hp}/${s.maxHp}${def.defense ? ` · defense ${def.defense}` : ""}` : null, own ? output(ctx, sel.id) : null)];
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
          btn(`Recruit ${ud.name}`, () => act.send({ action: "recruit", structure: sel.id, kind: ut }), { disabled: !!why, title: why || HexText.units[ut] || "" }),
          el("span", { className: "small" }, costText(ud.cost)),
          unitStats(ud), why ? el("div", { className: "muted small" }, why) : null));
      }
      const row = el("div", { className: "hr-btnrow" },
        def.jobs > 0 ? btn(s.active === false ? "Switch on" : "Switch off", () => act.send({ action: "toggle", structure: sel.id }), { title: "Switched-off structures don't use workers." }) : null,
        s.type !== "town_hall" ? btn("Demolish", () => { if (confirm(`Demolish this ${def.name}? No refund, and goods stored in it are lost.`)) act.send({ action: "demolish", structure: sel.id }); }, { cls: "danger", title: "Remove it now (no refund)." }) : null);
      kids.push(row);
      if (def.trade) kids.push(tradePanel(ctx, sel.id, def));
      if (s.type === "town_hall") kids.push(el("div", { className: "hr-btnrow" }, claimButton(ctx)));
    }
    fill(box, ...kids);
  }

  // A placed structure's real output per turn, from the report's flows (positive entries).
  const output = (ctx, sid) => Object.fromEntries(ctx.priv.report.flows
    .filter(([id, r, n, , tag]) => id === sid && n > 0 && !tag && ctx.content.resources.includes(r)).map(([, r, n]) => [r, n]));

  function siteText(ctx, cid, x) {
    const n = ctx.priv.building?.works?.[cid] || 0;
    return `${x.done}/${x.hammers} 🔨 — ${x.done >= x.hammers ? "finishing (blocked by an enemy unit)" : n ? `+${n} 🔨 this turn (${resIcon("people")} −${n})` : "waiting for idle people"}`;
  }

  function site(box, ctx) {
    const { game, content, ui, act } = ctx;
    const x = game.sites[ui.sel.id], def = x && content.structures[x.type];
    if (!def) return fill(box);
    const own = x.owner === ctx.you;
    fill(box, el("h3", {}, `${def.name} (under construction) `, nameSpan(game, x.owner)),
      el("p", { className: "small" }, own ? siteText(ctx, ui.sel.id, x) : `${x.done}/${x.hammers} 🔨 done.`),
      own ? el("p", { className: "muted small" }, "Each idle person (no job) builds 1 🔨 a turn, oldest site first. Switch structures off to free people.") : null,
      own ? btn("Demolish", () => act.send({ action: "demolish", structure: ui.sel.id }), { cls: "danger", title: "Take the site down and get its cost back." }) : null);
  }

  function orders(box, ctx) {
    const { priv, content, game, act } = ctx;
    const o = priv.orders;
    const rows = [
      ...o.builds.map((b) => { const n = priv.building?.orders?.[b.id] || 0;
        return [b.id, `Build ${content.structures[b.type]?.name || b.type} (🔨 ${content.structures[b.type]?.hammers || 1}, ${n ? `${resIcon("people")} −${n}` : "no idle people yet"})`, b.cost]; }),
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

  // A trade structure's standing trade: `def.trade` of one resource for 1 of another, every turn.
  function tradePanel(ctx, sid, def) {
    const { priv, content, ui, act } = ctx;
    const on = priv.trades?.[sid];
    const draft = on || ui.trade[sid] || { give: "wood", get: "gold" };
    const send = (t) => act.send({ action: "trade", structure: sid, ...t });
    const pick = (key) => {
      const select = el("select", { onchange: () => {
        const t = { ...draft, [key]: select.value };
        ui.trade[sid] = t;
        if (on && t.give !== t.get) send(t);
        act.select("structure", sid);
      } }, content.tradeGoods.map((r) => el("option", { value: r, selected: r === draft[key] }, `${resIcon(r)} ${resName(r)}`)));
      return select;
    };
    const made = priv.report.trades.some(([id]) => id === sid);
    return el("div", { className: "hr-trade", title: HexText.trade.help(def.trade) }, el("h3", {}, "Trade"),
      el("div", { className: "row" }, `Give ${def.trade}`, pick("give"), "for 1", pick("get")),
      el("div", { className: "row" },
        btn(on ? "Stop trade" : "Enable trade", () => send(on ? { give: null } : draft), { cls: on ? "on" : "", disabled: !on && draft.give === draft.get }),
        on ? el("span", { className: `small ${made ? "pos" : "neg"}` }, made ? HexText.trade.on : HexText.trade.off) : null));
  }

  function claimButton(ctx) {
    const { content, ui, act } = ctx;
    const claiming = ui.mode?.type === "claim";
    return btn(claiming ? "Extending territory… (Esc)" : `Extend territory (${costText(content.claim.cost)})`,
      () => act.setMode(claiming ? null : { type: "claim" }),
      { cls: claiming ? "on" : "", disabled: !claiming && !canPay(ctx, content.claim.cost), title: HexText.claim.help(content.claim) });
  }

  // Only structures you have unlocked; one category open at a time (clicking it again closes it).
  function build(box, ctx) {
    const { content, me, ui, act } = ctx;
    const mine = new Set(me.advances || []);
    const buildable = Object.entries(content.structures).filter(([id, d]) => id !== "town_hall" && (!d.requires || mine.has(d.requires)));
    const cats = Object.entries(content.categories || {}).filter(([c]) => buildable.some(([, d]) => d.category === c));
    const pick = (c) => { ui.buildCat = ui.buildCat === c ? null : c; act.setMode(ui.mode?.type === "build" ? null : ui.mode); };
    const tabs = el("div", { className: "hr-cats" }, cats.map(([c, label]) =>
      el("button", { className: `hr-cat${ui.buildCat === c ? " on" : ""}`, onclick: () => pick(c) }, label)));
    const items = buildable.filter(([, d]) => d.category === ui.buildCat).map(([id, d]) => {
      const poor = !canPay(ctx, d.cost);
      const si = structInfo(content, d);
      const tagText = si.byTag.map((b) => `${b.n > 0 ? "+" : "−"}${Math.abs(b.n)} ${resIcon(b.res)} for ${content.tags?.[b.tag]?.name || b.tag}`);
      const tags = si.tags.map((t) => content.tags?.[t]?.name || t).join(", ");
      const info = [tags ? `[${tags}]` : "", si.text, si.res, ...tagText, si.stats.join(". "), si.hp, `Build: ${si.build}`, `On: ${si.terrains}`].filter(Boolean).join("\n");
      const active = ui.mode?.type === "build" && ui.mode.kind === id;
      return el("button", { className: `hr-build${active ? " on" : ""}`, disabled: poor, title: `${poor ? "Can't afford\n" : ""}${info}`,
        onclick: () => (active ? act.setMode(null) : act.setMode({ type: "build", kind: id, rot: ui.lastRot || 0 })) },
        el("span", { className: "hr-bicon" }, d.icon || "▪"), el("span", { className: "hr-bname" }, d.name), el("span", { className: "hr-bcost small" }, costText(d.cost)));
    });
    fill(box, tabs,
      ui.buildCat ? el("div", { className: "hr-buildgrid" }, items) : el("p", { className: "muted small" }, "Pick a category, then a structure."),
      el("p", { className: "muted small" }, "Click the map to place it. R or right-click turns it, Esc cancels. It goes anywhere inside your territory and becomes a construction site that idle people build over a few turns. Goods go straight to your stores."));
  }


  window.HexHud = { topbar, players, selection, orders, build, structCard, fmt: { costText, canPay, nameSpan, btn, cap, setResources, resIcon, resName, structInfo, resListEl } };
})();
