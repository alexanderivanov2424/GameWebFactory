/*
 * Hex Realms: the HUD panels around the map, all built from the state (no rules here).
 *
 *   HexHud.topbar(el, ctx)      turn, countdown (#hr-timer, ticked by game.js), resources (+net), people (current:
 *                               jobs / building / units / idle), housing (the cap) and growth (rate, this turn's
 *                               gain, Growth off / on) as chips, Jobs off / Jobs on
 *                               (every structure with workers), End turn; clicking a resource, people or housing
 *                               toggles the map's resource view (act.resView, ui.resView)
 *   HexHud.players(el, ctx)     colour, name, score, done tick, out, public resource snapshot
 *   HexHud.selection(el, ctx)   the selected unit / structure / construction site: stats, orders,
 *                               Recruit/Hold/Shoot/Found/Disband/Switch off/Demolish, automatic recruiting
 *   HexHud.orders(el, ctx)      your pending builds / recruits / research, each with a cancel button, and your
 *                               construction sites (progress, whether builders work there this turn, demolish)
 *   HexHud.trade(el, ctx)       give/get selects (only when the market rate is > 0)
 *   HexHud.build(el, ctx)       one button per buildable structure (starts build mode)
 *   HexHud.fmt                  small text helpers shared with panels.js (cost, nameSpan, resource icons);
 *                               fmt.setResources(content.resourceInfo) first (game.js does, each render)
 *   HexHud.fmt.structInfo(content, def)  {text, stats: [text], hp: text, terrains: text, build: text,
 *                               tags: [id], byTag: [{n, res, tag}] (perAdjacent per neighbour with a tag)}: a
 *                               structure described from its content fields (build menu tooltip, placing panel)
 *   HexHud.structCard(content, def, hp?)  the structure card: a small picture of the footprint, HP below it
 *                               (hp: live "HP 5/15" text for a placed one), its tags as pips, then every
 *                               effect ("−1 🍞 for [Industrial]" lines for tag bonuses). The placing hint's
 *                               right-hand section and the top of a selected structure's panel
 *   Top bar deltas: each resource / people / housing chip has an empty .hr-delta.hr-delta-<key> below it
 *                   (plus one for "turns" at the end), filled by game.js while placing a structure
 *
 * ctx = { game, priv, you, me (public player entry), content, ui, act } where ui is the page's
 * persistent UI state ({sel, mode, trade, resView}) and act = { send(msg), select(kind, id), setMode(mode), centre(key), resView(res) }.
 * Every function replaces the children of its element, so call them on each render.
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
  // What a structure does and where it may go, read from its content (the server's rules decide).
  function structInfo(content, d) {
    const stats = [];
    if (Object.keys(d.produce || {}).length && !Object.keys(d.onTerrain || {}).length) stats.push(`Makes ${costText(d.produce)} a turn`);
    if (d.jobs) stats.push(`Needs ${plural(d.jobs, "worker")}`);
    if (d.housing) stats.push(`Housing ${d.housing}`);
    if (d.storage) stats.push(`Stores ${d.storage} of each good`);
    if (Object.keys(d.store || {}).length) stats.push(`Stores ${costText(d.store)}`);
    if (d.growth) stats.push(`Growth +${d.growth}`);
    if (d.trade) stats.push(`Trade ${d.trade}:1`);
    if ((d.recruits || []).length) stats.push(`Trains ${names(content, "units", d.recruits)}`);
    if (d.heals) stats.push("Heals units on or next to it");
    if (d.shoots) stats.push(`Shoots ${plural(d.shoots, "die")} (range ${d.range})`);
    if (d.score) stats.push(`+${d.score} score`);
    const hp = d.hp ? `HP ${d.hp}${d.defense ? ` · defense ${d.defense}` : ""}` : "Can't be attacked";
    const terrains = names(content, "terrain", d.terrain || []) + (d.coast ? " · touching water" : "");
    const build = `${costText(d.cost)}, ${plural(d.buildTurns, "turn")} of work by ${plural(d.builders, "idle person")} each`;
    const byTag = (d.perAdjacent || []).filter((a) => a.tag).flatMap((a) => Object.entries(a.gain || {}).map(([res, n]) => ({ n, res, tag: a.tag })));
    return { text: d.text || "", stats, hp, terrains, build, tags: d.tags || [], byTag };
  }

  // A small picture of a structure's footprint (unturned) in its colour, its icon in the middle.
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

  function structCard(content, d, hp) {
    const si = structInfo(content, d);
    return el("div", { className: "hr-scard" }, structPicture(d), el("div", { className: "hr-shp" }, hp || si.hp),
      si.tags.length ? el("div", { className: "hr-pips" }, si.tags.map((t) => pip(content, t))) : null,
      si.text ? el("div", { className: "hr-stext" }, si.text) : null,
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

  // A chip with an (empty) delta line under it, filled while placing a structure.
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
      return withDelta(r, el("span", { className: `hr-chip hr-res-${r}${full ? " full" : ""}${ctx.ui.resView === r ? " on" : ""}`, onclick: () => ctx.act.resView(r), title: `${VIEW_TIP}${resName(r)}: income ${rep.income[r] || 0}, upkeep ${rep.upkeep[r] || 0}${r === "gold" && rep.land ? ` (${rep.land} cells of bought land)` : ""}${capped !== undefined ? `, storage ${capped}` : ""}${(rep.wasted || {})[r] ? `, ${rep.wasted[r]} won't fit in your stores at the end of the turn (lost)` : ""}` },
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
        starving ? el("span", { className: "neg", title: "Not enough food (in your stores plus this turn's production) to feed everyone: whoever can't eat dies at the end of the turn, units first (newest first), then people." }, ` ⚠ starving: ${starving}`) : null)),
      withDelta("housing", el("span", { className: `hr-people${priv.pop + rep.soldiers >= rep.housing ? " full" : ""}${ctx.ui.resView === "housing" ? " on" : ""}`, onclick: () => ctx.act.resView("housing"), title: `Click: show on the map which structures give housing.\nHousing ${rep.housing}: the population cap. Your people and the people in your units (${priv.pop + rep.soldiers}) must fit in it to grow.` },
        el("span", { className: "hr-ricon" }, resIcon("housing")), " cap ", el("b", {}, String(rep.housing)))),
      withDelta("growth", el("span", { className: `hr-people${ctx.ui.resView === "growth" ? " on" : ""}`, onclick: () => ctx.act.resView("growth"),
        title: `Click: show on the map which structures give growth.\nGrowth ${rep.growthRate}: people you can gain a turn, with free housing and enough food left at the end of the turn to feed them.${rep.growth ? `\nThis turn: +${rep.growth}.` : `\nNo growth this turn: ${rep.growthWhy}`}` },
        el("span", { className: "hr-ricon" }, resIcon("growth")), " ", rep.growthOff ? el("b", { className: "muted" }, "off") : el("b", { className: rep.growth ? "pos" : "" }, `+${rep.growth}`))),
      btn(rep.growthOff ? "Growth on" : "Growth off", () => ctx.act.send({ action: "growth", on: !!rep.growthOff }),
        { cls: `small${rep.growthOff ? " on" : ""}`, title: rep.growthOff ? "Let your population grow again." : "Stop your population growing (kept across turns until you turn it back on)." }),
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

  // A unit's stats as small chips like the resources: attack, defence, movement, health (hp: "5/8" for a
  // unit on the map), then range and siege when it has them.
  const UNIT_STATS = [["attack", "⚔️", "Attack: dice it rolls when it attacks"], ["defense", "🛡️", "Defence: dice it rolls when attacked"],
    ["move", "👣", "Movement: steps a turn"], ["hp", "❤️", "Health"], ["range", "🏹", "Range: shoots this far instead of moving"],
    ["siege", "💥", "Siege: damage per hit on structures"]];
  function unitStats(def, hp) {
    return el("div", { className: "hr-ustats" }, UNIT_STATS.filter(([k]) => (k === "range" ? def.range : k === "siege" ? def.siege > 1 : true))
      .map(([k, icon, title]) => el("span", { className: "hr-chip hr-ustat", title }, `${icon} `, el("b", {}, String(k === "hp" && hp ? hp : def[k])))));
  }

  function selection(box, ctx) {
    const { game, priv, content, ui, act } = ctx;
    const sel = ui.sel;
    if (!sel) return fill(box, el("h3", {}, "Selection"), el("p", { className: "muted small" }, "Click one of your units or structures to command it, or any enemy to inspect it."));
    if (sel.kind === "unit") {
      const u = game.units[sel.id], def = u && content.units[u.type];
      if (!def) return fill(box);
      const own = u.owner === ctx.you, o = priv.orders;
      const kids = [el("h3", {}, `${def.name} `, nameSpan(game, u.owner)), unitStats(def, `${u.hp}/${u.maxHp}`), def.text ? el("p", { className: "small" }, def.text) : null];
      if (own) {
        const auto = priv.auto?.[sel.id] || null, mode = auto?.mode;
        const standing = { explore: "Exploring (walks on its own each turn)", fight: "Fighting (attacks the nearest enemy unit it sees; holds when none)",
          pillage: "Pillaging (attacks the nearest enemy structure it sees, fighting enemy units that come close first; holds when none)",
          travel: `Travelling to ${auto?.goal} over several turns` };
        const pending = mode ? `${standing[mode]}; any other order stops it` : o.moves[sel.id] ? `Moving to ${o.moves[sel.id][o.moves[sel.id].length - 1]}` : o.shots[sel.id] ? `Shooting at ${o.shots[sel.id]}`
          : sel.id in o.found ? "Founding a city" : o.holds.includes(sel.id) ? "Holding position" : "No orders";
        const hold = o.holds.includes(sel.id) && !mode;
        const found = priv.found[sel.id] || [];
        // A command deselects the unit (Clear orders keeps it selected to give a new one).
        const command = (msg) => { act.send(msg); act.select(null); };
        const autoBtn = (m, label, title) => btn(mode === m ? `${label} (on)` : label, () => command({ action: "auto", unit: sel.id, mode: m }), { cls: mode === m ? "on" : "", title });
        const row = el("div", { className: "hr-btnrow" },
          btn(hold ? "Hold (on)" : "Hold", () => command({ action: "hold", unit: sel.id }), { cls: hold ? "on" : "", title: "Roll one extra defence die this turn instead of moving." }),
          game.fog && !def.settler ? autoBtn("explore", "Explore", "Walk around on its own every turn to clear the fog, until you give it another order.") : null,
          !def.settler ? autoBtn("fight", "Fight", "Every turn, attack the nearest enemy unit you can see (hold when there's none), until you give it another order.") : null,
          !def.settler ? autoBtn("pillage", "Pillage", "Every turn, attack the nearest enemy structure you can see, but fight enemy units that come close first (hold when there's nothing), until you give it another order.") : null,
          def.range ? btn("Shoot", () => act.setMode({ type: "shoot", unit: sel.id }), { cls: ui.mode?.type === "shoot" ? "on" : "", title: `Shoot a unit or structure up to ${def.range} cells away.` }) : null,
          def.settler ? btn("Found city", () => act.setMode({ type: "found", unit: sel.id, rot: found[0] }), { disabled: !found.length, cls: ui.mode?.type === "found" ? "on" : "", title: found.length ? "Found a Town Hall here." : "Can't found a city here." }) : null,
          btn("Clear orders", () => act.send({ action: "move", unit: sel.id, to: u.at })),
          btn("Disband", () => { if (confirm(`Disband this ${def.name}?`)) act.send({ action: "disband", unit: sel.id }); }, { cls: "danger" }));
        kids.push(el("p", { className: "hr-pending" }, pending), row,
          el("p", { className: "muted small" }, "Click a highlighted cell to move there (red = attack), or any cell further away to walk there over several turns. Click the unit again to clear its orders (when it stands on a structure, that selects the structure; use Clear orders)."));
      }
      return fill(box, ...kids);
    }
    if (sel.kind === "site") return site(box, ctx);
    const s = game.structures[sel.id], def = s && content.structures[s.type];
    if (!def) return fill(box);
    const own = s.owner === ctx.you;
    const kids = [el("h3", {}, `${def.name} `, nameSpan(game, s.owner)),
      structCard(content, def, s.maxHp ? `HP ${s.hp}/${s.maxHp}${def.defense ? ` · defense ${def.defense}` : ""}` : null)];
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
          unitStats(ud), why ? el("div", { className: "muted small" }, why) : null));
      }
      const auto = priv.autoRecruit?.[sel.id];
      if (auto) kids.push(autoRecruit(ctx, sel.id, auto, Object.keys(recruits)));
      const row = el("div", { className: "hr-btnrow" },
        def.jobs > 0 ? btn(s.active === false ? "Switch on" : "Switch off", () => act.send({ action: "toggle", structure: sel.id }), { title: "Switched-off structures don't use workers." }) : null,
        s.type !== "town_hall" ? btn("Demolish", () => { if (confirm(`Demolish this ${def.name}? No refund, and goods stored in it are lost.`)) act.send({ action: "demolish", structure: sel.id }); }, { cls: "danger", title: "Remove it now (no refund)." }) : null);
      kids.push(row);
    }
    fill(box, ...kids);
  }

  // A military structure's automatic recruiting: which unit every turn (or Off), and the standing order its units get.
  function autoRecruit(ctx, sid, auto, kinds) {
    const { game, content, act } = ctx;
    const send = () => act.send({ action: "autorecruit", structure: sid, kind: kind.value || null, order: order.value || null });
    const kind = el("select", { onchange: send, title: "Recruit this unit every turn on its own, when you can pay and have people without a job." },
      el("option", { value: "", selected: !auto.kind }, "Off"),
      kinds.map((ut) => el("option", { value: ut, selected: auto.kind === ut }, content.units[ut]?.name || ut)));
    const modes = [["", "No order"], ...(game.fog ? [["explore", "Explore"]] : []), ["fight", "Fight"], ["pillage", "Pillage"]];
    const order = el("select", { onchange: send, title: "The standing order every unit trained here starts with (also ones you recruit by hand)." },
      modes.map(([m, label]) => el("option", { value: m, selected: (auto.order || "") === m }, label)));
    return el("div", { className: "hr-autorecruit" },
      el("div", { className: "row small" }, "Recruit every turn", el("span", { className: "spacer" }), kind),
      el("div", { className: "row small" }, "New units", el("span", { className: "spacer" }), order),
      el("p", { className: "muted small" }, "Skips a turn when it can't pay or no one is free (it never takes people from jobs)."));
  }

  function siteText(ctx, cid, x) {
    const works = (ctx.priv.building?.works || []).includes(cid);
    return `${x.done}/${x.turns} turns, ${resIcon("people")} −${x.builders} — ${x.done >= x.turns ? "finishing (blocked by an enemy unit)" : works ? "building this turn" : "waiting for idle people"}`;
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
      ...o.builds.map((b) => { const n = content.structures[b.type]?.builders || 0;
        return [b.id, `Build ${content.structures[b.type]?.name || b.type} (${resIcon("people")} −${n})`, b.cost]; }),
      ...o.recruits.map((r) => [r.id, `${r.auto ? "Auto-recruit" : "Recruit"} ${content.units[r.type]?.name || r.type} at ${content.structures[game.structures[r.at]?.type]?.name || "?"}`, r.cost]),
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
      const si = structInfo(content, d);
      const tagText = si.byTag.map((b) => `${b.n > 0 ? "+" : "−"}${Math.abs(b.n)} ${resIcon(b.res)} for ${content.tags?.[b.tag]?.name || b.tag}`);
      const tags = si.tags.map((t) => content.tags?.[t]?.name || t).join(", ");
      const info = [tags ? `[${tags}]` : "", si.text, ...tagText, si.stats.join(". "), si.hp, `Build: ${si.build}`, `On: ${si.terrains}`].filter(Boolean).join("\n");
      const active = ui.mode?.type === "build" && ui.mode.kind === id;
      return el("button", { className: `hr-build${active ? " on" : ""}`, disabled: !!why || poor, title: `${why ? `${why}\n` : poor ? "Can't afford\n" : ""}${info}`,
        onclick: () => (active ? act.setMode(null) : act.setMode({ type: "build", kind: id, rot: ui.lastRot || 0 })) },
        el("span", { className: "hr-bicon" }, d.icon || "▪"), el("span", { className: "hr-bname" }, d.name), el("span", { className: "hr-bcost small" }, why || costText(d.cost)));
    });
    const claiming = ui.mode?.type === "claim", claimCost = content.claim?.cost || {};
    const claim = btn(claiming ? "Extending territory… (Esc)" : `Extend territory (${costText(claimCost)})`,
      () => act.setMode(claiming ? null : { type: "claim" }),
      { cls: claiming ? "on" : "", disabled: !claiming && !canPay(ctx, claimCost), title: `Buy an explored cell next to your land, one at a time; it's yours at once (not next to an enemy unit). Bought land costs ${content.claim?.upkeep ?? 1} gold a turn per cell (unpaid cells are given up, farthest first) and is weak: an enemy unit on or next to it, being cut off from your cities' free land, or another realm's Town Hall reaching it make it nobody's.` });
    fill(box, el("div", { className: "hr-btnrow" }, claim), tabs,
      ui.buildCat ? el("div", { className: "hr-buildgrid" }, items) : el("p", { className: "muted small" }, "Pick a category, then a structure."),
      el("p", { className: "muted small" }, "Click the map to place it. R or right-click turns it, Esc cancels. It goes anywhere inside your territory and becomes a construction site that idle people build over a few turns. Goods go straight to your stores."));
  }

  window.HexHud = { topbar, players, selection, orders, trade, build, structCard, fmt: { costText, canPay, nameSpan, btn, cap, setResources, resIcon, resName, structInfo } };
})();
