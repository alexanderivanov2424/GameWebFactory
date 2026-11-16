/*
 * Hex Realms HUD: the panels around the map (top bar, players, selection, orders, trade, build menu), built from state.
 * No rules here. Each function replaces its element's children, so call it on every render.
 *
 * HexHud.topbar(el, ctx)      turn, timer, resources, people, population, housing, End turn
 * HexHud.players(el, ctx)     players: colour, name, score, done, public resources
 * HexHud.selection(el, ctx)   the selected unit, structure or site, with its actions
 * HexHud.orders(el, ctx)      pending builds, recruits, research, construction sites
 * HexHud.trade(el, ctx)       market give/get selects
 * HexHud.build(el, ctx)       build menu buttons (hover one: its structure card beside it)
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
  // Output and workers, e.g. "+3 🪵, −1 👥 (−1 👥)": the actual amounts (green / red = more / less than the base),
  // then the base amounts in brackets. at = {res, jobs, terrain} where it stands (or would); without it only the base.
  const order = (r) => { const i = Object.keys(RES).indexOf(r); return i < 0 ? 99 : i; };
  const amount = (r, n) => `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n)} ${resIcon(r)}`;
  const withJobs = (res, jobs) => ({ ...(res || {}), ...(jobs ? { people: -jobs } : {}) });
  function baseOf(d, terrain = null) {
    const t = d.onTerrain || {};
    return withJobs(Object.keys(t).length ? t[terrain] || (terrain ? {} : null) : d.produce, d.jobs);
  }
  function baseText(d) {
    const t = Object.entries(d.onTerrain || {});
    const sorted = (res) => Object.entries(res).filter(([, n]) => n).sort((a, b) => order(a[0]) - order(b[0]));
    const items = t.length ? [t.map(([k, out]) => `${sorted(out).map(([r, n]) => amount(r, n)).join(" ")} on ${k}`).join(" or ")] : [];
    items.push(...sorted(baseOf(d) || withJobs({}, d.jobs)).map(([r, n]) => amount(r, n)));
    return items.length ? `(${items.join(", ")})` : "";
  }
  const resListText = (d) => baseText(d);
  function resListEl(d, at = null) {
    const base = baseText(d);
    if (!at) return base ? [base] : [];
    const want = baseOf(d, at.terrain) || {}, have = withJobs(at.res, at.jobs ?? d.jobs);
    const keys = [...new Set([...Object.keys(want), ...Object.keys(have)])].filter((r) => want[r] || have[r]).sort((a, b) => order(a) - order(b));
    const items = keys.map((r) => { const n = have[r] || 0, b = want[r] || 0;
      return el("span", { className: n > b ? "pos" : n < b ? "neg" : "" }, amount(r, n)); });
    return [...items.flatMap((x, i) => [i ? ", " : null, x]), base ? el("span", { className: "muted" }, ` ${base}`) : null];
  }
  // What a structure does and where it may go, read from its content (the server's rules decide).
  function structInfo(content, d) {
    const stats = [];
    if (d.housing) stats.push(`Housing ${d.housing}`);
    const stored = (content.goods || []).map((r) => [r, (d.storage || 0) + ((d.store || {})[r] || 0)]).filter(([, n]) => n);
    if (stored.length) stats.push(`Stores ${stored.map(([r, n]) => `${n} ${resIcon(r)}`).join(", ")}`);
    if (d.trade) stats.push(`Trade ${d.trade}:1`);
    if ((d.recruits || []).length) stats.push(`Trains ${names(content, "units", d.recruits)}`);
    if (d.heals) stats.push("Heals units on or next to it");
    if (d.shoots) stats.push(`Shoots ${plural(d.shoots, "die")} (range ${d.range})`);
    if (d.score) stats.push(`+${d.score} score`);
    if (d.blocks) stats.push(HexText.structure.blocks);
    if (d.outside) stats.push(HexText.structure.outside);
    for (const b of d.boost || []) stats.push(`+${b.add} to what each ${b.type ? content.structures[b.type]?.name || b.type : `${content.tags?.[b.tag]?.name || b.tag} structure`} next to it makes, while it works`);
    const hp = d.hp ? `HP ${d.hp}${d.defense ? ` · defense ${d.defense}` : ""}` : "Can't be attacked";
    const terrains = names(content, "terrain", d.terrain || []) + (d.coast ? " · touching water" : "");
    const build = `${costText(d.cost)} · 🔨 ${d.hammers} (each idle person builds 1 🔨 a turn)`;
    // Neighbour bonuses as bullets "+2 🌾 for [Farm]": kind "tag" / "type" / "terrain" (perAdjacent), "free" (freeNear: no workers).
    const adjacent = (d.perAdjacent || []).flatMap((a) => Object.entries(a.gain || {}).map(([res, n]) =>
      ({ n, res, max: a.max, needs: a.needs || 0, kind: a.tag ? "tag" : a.type ? "type" : a.unique ? "unique" : "terrain", id: a.tag || a.type || a.terrain || "unique" })));
    if (d.freeNear && d.jobs) adjacent.push({ n: -d.jobs, res: "people", kind: "free", id: d.freeNear });
    for (const [t, gain] of Object.entries(d.perCell || {}))  // "+1 🪨 on each [Hills]": per own cell on that terrain
      for (const [res, n] of Object.entries(gain)) adjacent.push({ n, res, kind: "cell", id: t });
    // One bullet per chip: "+1 🌾 −1 👥 for [Water]" (a terrain bonus and freeNear on the same terrain share one).
    const groups = new Map();
    for (const b of adjacent) {
      const k = `${b.kind === "free" ? "terrain" : b.kind}:${b.id}:${b.needs || 0}`;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k).push(b);
    }
    return { text: HexText.structures[d.id] || "", res: resListText(d), stats, hp, terrains, build, tags: d.tags || [], adjacent: [...groups.values()] };
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
  // A chip naming a structure type (its colour) or a terrain (its map colour), like a tag's pip.
  const chip = (name, color) => el("span", { className: "hr-pip", style: `background:${color}` }, name);
  // One bullet: every amount for the same chip (see structInfo's adjacent groups), with each rule in the hover title.
  function adjacentLine(content, group) {
    const { kind, id } = group[0];
    const terrain = content.terrain?.[id]?.name || id, type = content.structures?.[id];
    const label = kind === "tag" ? pip(content, id) : kind === "type" ? chip(type?.name || id, type?.color || "#666")
      : kind === "unique" ? chip(HexText.structure.adjacent.uniqueChip, "#666") : chip(terrain, HexMap.util.colors[id] || "#666");
    const t = HexText.structure.adjacent;
    const title = (b) => {
      const amount = [b.n > 0 ? "+" : "−", Math.abs(b.n), resName(b.res).toLowerCase()];
      if (b.needs) return t.needs(...amount, b.needs, b.kind === "tag" ? `of your ${content.tags?.[id]?.name || id} structures`
        : b.kind === "type" ? `of your ${type?.name || id}s` : b.kind === "unique" ? "different types of your structures"
        : `${terrain.toLowerCase()} cells with nothing built on them`);
      return b.kind === "cell" ? t.cell(...amount, terrain.toLowerCase())
        : b.kind === "free" ? t.free(terrain.toLowerCase())
        : b.kind === "tag" ? t.tag(...amount, content.tags?.[id]?.name || id, b.max)
        : b.kind === "type" ? t.type(...amount, type?.name || id, b.max)
        : b.kind === "unique" ? t.unique(...amount, b.max) : t.terrain(...amount, terrain.toLowerCase(), b.max);
    };
    const amounts = group.flatMap((b, i) => [i ? " " : null,
      el("span", { className: b.n > 0 ? "pos" : "neg" }, `${b.n > 0 ? "+" : "−"}${Math.abs(b.n)} ${resIcon(b.res)}`)]);
    const needs = group.find((b) => b.needs)?.needs;
    return el("li", { title: group.map(title).join("\n") }, ...amounts, kind === "cell" ? " on each " : ` for ${needs ? `${needs} ` : ""}`, label);
  }

  function structCard(content, d, hp, at = null) {
    const si = structInfo(content, d);
    return el("div", { className: "hr-scard" }, structPicture(d), el("div", { className: "hr-shp" }, hp || si.hp),
      si.tags.length ? el("div", { className: "hr-pips" }, si.tags.map((t) => pip(content, t))) : null,
      si.text ? el("div", { className: "hr-stext" }, si.text) : null,
      si.res || at ? el("div", { className: "hr-sres", title: HexText.structure.resTitle }, ...resListEl(d, at)) : null,
      el("ul", { className: "hr-sstats" }, si.adjacent.map((b) => adjacentLine(content, b)), si.stats.map((t) => el("li", {}, t))));
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

  // The structure card shown beside a build button while it's hovered (one floating element).
  let popCard = null;
  function showCard(button, card) {
    popCard ||= document.body.appendChild(el("div", { className: "hr-panel hr-popcard" }));
    fill(popCard, card);
    popCard.hidden = false;
    const b = button.getBoundingClientRect(), h = popCard.offsetHeight;
    popCard.style.right = `${window.innerWidth - b.left + 8}px`;
    popCard.style.top = `${Math.max(8, Math.min(b.top, window.innerHeight - h - 8))}px`;
  }
  const hideCard = () => { if (popCard) popCard.hidden = true; };

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
      const food = r === "food";  // food isn't stored: show what's left after everyone eats (no brackets)
      const shown = food ? net : priv.res[r] || 0;
      const full = capped !== undefined && shown >= capped;
      const flat = (ctx.content.flat || []).includes(r);  // what working structures give now, minus advances bought
      return withDelta(r, el("span", { className: `hr-chip hr-res-${r}${full ? " full" : ""}${ctx.ui.resView === r ? " on" : ""}`, onclick: () => ctx.act.resView(r) },
        el("span", { className: "hr-ricon" }, resIcon(r)), " ", el("b", { className: food && net < 0 ? "neg" : "" }, String(shown)), capped !== undefined ? el("small", {}, `/${capped}`) : null,
        flat || food ? null : el("span", { className: net < 0 ? "neg" : net > 0 ? "pos" : "" }, ` (${signed(net)})`)));
    });
    const done = priv.done;
    const end = btn(done ? "Waiting for others… (undo)" : "End turn", () => ctx.act.send({ action: "done", done: !done }), { cls: done ? "waiting" : "endturn" });
    fill(box, 
      el("span", { className: "hr-turn" }, `Turn ${game.turn} / ${game.turnLimit}`),
      game.turnSeconds > 0 ? el("span", { id: "hr-timer", className: "hr-timer" }) : null,
      el("span", { className: "hr-chips" }, chips),
      withDelta("people", el("span", { className: `hr-people${ctx.ui.resView === "people" ? " on" : ""}`, onclick: () => ctx.act.resView("people"), title: HexText.hud.people(rep.idle, priv.pop + rep.soldiers, rep.workers, rep.builders, rep.soldiers) },
        el("span", { className: "hr-ricon" }, resIcon("people")), " idle ", el("b", {}, String(rep.idle)),
        starving ? el("span", { className: "neg", title: HexText.hud.starving }, ` ⚠ starving: ${starving}`) : null)),
      withDelta("population", el("span", { className: `hr-people${ctx.ui.resView === "population" ? " on" : ""}`, onclick: () => ctx.act.resView("population"), title: HexText.hud.population(priv.pop + rep.soldiers, priv.pop, rep.soldiers, rep.popNet ? signed(rep.popNet) : "") },
        el("span", { className: "hr-ricon" }, resIcon("population")), " population ", el("b", {}, String(priv.pop + rep.soldiers)),
        el("span", { className: rep.popNet < 0 ? "neg" : rep.popNet > 0 ? "pos" : "" }, ` (${signed(rep.popNet || 0)})`))),
      withDelta("housing", el("span", { className: `hr-people${priv.pop + rep.soldiers >= rep.housing ? " full" : ""}${ctx.ui.resView === "housing" ? " on" : ""}`, onclick: () => ctx.act.resView("housing"), title: HexText.hud.housing(rep.housing, priv.pop + rep.soldiers) },
        el("span", { className: "hr-ricon" }, resIcon("housing")), " cap ", el("b", {}, String(rep.housing)))),
      withDelta("turns", null),
      btn("Jobs off", () => ctx.act.send({ action: "staff", on: false }), { cls: "small", title: HexText.hud.jobsOff }),
      btn("Jobs on", () => ctx.act.send({ action: "staff", on: true }), { cls: "small", title: HexText.hud.jobsOn }),
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
        el("div", { className: "hr-psub", title: `Start of this turn: ${["gold", "wood", "stone", "metal"].map((k) => `${resName(k)} ${r[k] ?? 0}`).join(", ")}, ${resName("people")} ${p.pop ?? 0}` },
          ["gold", "wood", "stone", "metal"].map((k) => `${resIcon(k)}${r[k] ?? 0}`).join(" ") + ` · ${resIcon("people")}${p.pop ?? 0} · ${(p.advances || []).length} adv`));
    }));
  }

  // A unit's stats as chips: attack, defence, move, hp, range and siege if any, then food eaten per turn.
  const UNIT_STATS = [["attack", "🗡️"], ["defense", "🛡️"], ["move", "👣"], ["hp", "❤️"], ["range", "🏹"], ["siege", "💥"]];
  function unitStats(def, hp) {
    return el("div", { className: "hr-ustats" }, UNIT_STATS.filter(([k]) => (k === "range" ? def.range : k === "siege" ? def.siege > 1 : true))
      .map(([k, icon]) => el("span", { className: "hr-chip hr-ustat", title: HexText.unit.stats[k] }, `${icon} `, el("b", {}, String(k === "hp" && hp ? hp : def[k])))),
      ((food) => el("span", { className: "hr-chip hr-ustat", title: HexText.unit.stats.food },
        el("b", {}, food ? `−${food}` : "0"), ` ${resIcon("food")}`))(def.upkeep?.food || 0));
  }

  function selection(box, ctx) {
    const { game, priv, content, ui, act } = ctx;
    const sel = ui.sel;
    if (!sel) return fill(box, el("h3", {}, "Selection"), el("p", { className: "muted small" }, HexText.unit.empty));
    if (sel.kind === "unit") {
      const u = game.units[sel.id], def = u && content.units[u.type];
      if (!def) return fill(box);
      const own = u.owner === ctx.you, o = priv.orders;
      const kids = [el("h3", {}, `${def.name} `, nameSpan(game, u.owner)), unitStats(def, `${u.hp}/${u.maxHp}`)];
      if (own) {
        const auto = priv.auto?.[sel.id] || null, mode = auto?.mode;
        const S = HexText.unit;
        const standing = mode === "travel" ? S.standing.travel(auto.goal) : S.standing[mode];
        const pending = mode ? S.standing.note(standing) : o.moves[sel.id] ? S.pending.moving(o.moves[sel.id][o.moves[sel.id].length - 1]) : o.shots[sel.id] ? S.pending.shooting(o.shots[sel.id])
          : sel.id in o.found ? S.pending.founding : o.holds.includes(sel.id) ? S.pending.holding : S.idle;
        const hold = o.holds.includes(sel.id) && !mode;
        const found = priv.found[sel.id] || [];
        // A command deselects the unit; Clear orders keeps it selected.
        const command = (msg) => { act.send(msg); act.select(null); };
        const autoBtn = (m, label) => btn(mode === m ? `${label} (on)` : label, () => command({ action: "auto", unit: sel.id, mode: m }), { cls: mode === m ? "on" : "", title: S[m].title });
        // Each action has a short description beside it.
        const action = (b, text) => b && [b, el("span", { className: "small muted" }, text)];
        const row = el("div", { className: "hr-actions" },
          action(btn(hold ? "Hold (on)" : "Hold", () => command({ action: "hold", unit: sel.id }), { cls: hold ? "on" : "", title: S.hold.title }),
            S.hold.desc),
          game.fog && !def.settler ? action(autoBtn("explore", "Explore"), S.explore.desc) : null,
          def.attack > 0 ? action(autoBtn("fight", "Fight"), S.fight.desc) : null,  // units with no attack never attack
          def.attack > 0 ? action(autoBtn("pillage", "Pillage"), S.pillage.desc) : null,
          def.range ? action(btn("Shoot", () => act.setMode({ type: "shoot", unit: sel.id }), { cls: ui.mode?.type === "shoot" ? "on" : "", title: S.shoot.title(def.range) }),
            S.shoot.desc(def.range)) : null,
          def.settler ? action(btn("Found city", () => act.setMode({ type: "found", unit: sel.id, rot: found[0] }), { disabled: !found.length, cls: ui.mode?.type === "found" ? "on" : "", title: found.length ? S.found.title : S.found.none }),
            found.length ? S.found.desc : S.found.none) : null,
          action(btn("Clear orders", () => act.send({ action: "move", unit: sel.id, to: u.at })), S.clear.desc),
          action(btn("Disband", () => { if (confirm(S.disband.confirm(def.name))) act.send({ action: "disband", unit: sel.id }); }, { cls: "danger" }),
            S.disband.desc));
        kids.push(el("p", { className: "hr-pending" }, pending), row);
      }
      return fill(box, ...kids);
    }
    if (sel.kind === "site") return site(box, ctx);
    const s = game.structures[sel.id], def = s && content.structures[s.type];
    if (!def) return fill(box);
    const own = s.owner === ctx.you;
    const kids = [el("h3", {}, `${def.name} `, nameSpan(game, s.owner)),
      structCard(content, def, s.maxHp ? `HP ${s.hp}/${s.maxHp}${def.defense ? ` · defense ${def.defense}` : ""}` : null,
        own ? { res: output(ctx, sel.id), jobs: priv.jobs?.[sel.id], terrain: game.cells[s.at] } : null)];
    if (def.jobs || Object.keys(def.produce || {}).length) {
      kids.push(el("p", { className: `small ${s.working ? "pos" : "neg"}` }, s.working ? HexText.structure.working : s.active === false ? HexText.structure.off : HexText.structure.noWorkers));
    }
    if (own) {
      const recruits = priv.recruit[sel.id] || {};
      for (const [ut, why] of Object.entries(recruits)) {
        const ud = content.units[ut];
        if (!ud) continue;
        const auto = priv.train?.[sel.id] === ut, noTrain = priv.trainable?.[sel.id]?.[ut] || "";
        kids.push(el("div", { className: "hr-recruit" },
          btn(`Recruit ${ud.name}`, () => act.send({ action: "recruit", structure: sel.id, kind: ut }), { disabled: !!why, title: why || HexText.units[ut] || "" }),
          ud.settler ? null : btn(auto ? "Auto ✓" : "Auto", () => act.send({ action: "train", structure: sel.id, kind: auto ? null : ut }),
            { cls: `small${auto ? " on" : ""}`, disabled: !auto && !!noTrain, title: noTrain || HexText.structure.autoTrain(ud.name) }),
          el("span", { className: "small" }, costText(ud.cost)),
          unitStats(ud), why ? el("div", { className: "muted small" }, why) : null));
      }
      const row = el("div", { className: "hr-btnrow" },
        def.jobs > 0 ? btn(s.active === false ? "Switch on" : "Switch off", () => act.send({ action: "toggle", structure: sel.id }), { title: HexText.structure.switchTitle }) : null,
        s.type !== "town_hall" ? btn("Demolish", () => { if (confirm(HexText.structure.demolishConfirm(def.name))) act.send({ action: "demolish", structure: sel.id }); }, { cls: "danger", title: HexText.structure.demolishTitle }) : null);
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
      own ? el("p", { className: "muted small" }, HexText.structure.siteHelp) : null,
      own ? btn("Demolish", () => act.send({ action: "demolish", structure: ui.sel.id }), { cls: "danger", title: HexText.structure.siteDemolish }) : null);
  }

  // Names only. Hover a row: its cells light up on the map; click: zoom there (and select the site or recruiting structure).
  function orders(box, ctx) {
    const { priv, content, game, act } = ctx;
    const o = priv.orders;
    const named = (d, id) => `${d?.icon ? `${d.icon} ` : ""}${d?.name || id}`;
    // [label, cells on the map or null, [kind, id] to select on click or null, cancel, cancel's title]
    const rows = [
      ...o.builds.map((b) => [named(content.structures[b.type], b.type), b.cells, null, () => act.send({ action: "cancel", order: b.id }), HexText.hud.cancelOrder]),
      ...o.recruits.map((r) => [named(content.units[r.type], r.type) + (r.auto ? HexText.structure.autoOrder : ""), game.structures[r.at]?.cells,
        game.structures[r.at] ? ["structure", r.at] : null, () => act.send({ action: "cancel", order: r.id }), HexText.hud.cancelOrder]),
      ...o.research.map((r) => [content.advances[r.advance]?.name || r.advance, null, null, () => act.send({ action: "cancel", order: r.id }), HexText.hud.cancelOrder]),
    ];
    const sites = Object.entries(game.sites || {}).filter(([, x]) => x.owner === ctx.you).map(([cid, x]) =>
      [named(content.structures[x.type], x.type), x.cells, ["site", cid], () => act.send({ action: "demolish", structure: cid }), HexText.hud.cancelSite]);
    const row = ([label, cells, select, cancel, title]) => el("div", {
      className: `row hr-order${cells ? " hr-order-map" : ""}`,
      onmouseenter: cells ? () => act.hoverCells(cells) : null, onmouseleave: cells ? () => act.hoverCells(null) : null,
      onclick: cells ? (e) => { if (e.target.closest("button")) return; if (select) act.select(...select); act.zoomTo(cells); } : null,
    }, el("span", { className: "small" }, label), el("span", { className: "spacer" }), btn("✕", () => { act.hoverCells(null); cancel(); }, { cls: "small", title }));
    fill(box, el("h3", {}, "Orders"), rows.length ? rows.map(row) : el("p", { className: "muted small" }, HexText.hud.noOrders),
      sites.length ? el("h3", {}, "Construction") : null, sites.map(row));
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
    hideCard();  // its button is about to be replaced
    const mine = new Set(me.advances || []);
    const buildable = Object.entries(content.structures).filter(([id, d]) => id !== "town_hall" && (!d.requires || mine.has(d.requires)));
    const cats = Object.entries(content.categories || {}).filter(([c]) => buildable.some(([, d]) => d.category === c));
    const pick = (c) => { ui.buildCat = ui.buildCat === c ? null : c; act.setMode(ui.mode?.type === "build" ? null : ui.mode); };
    const tabs = el("div", { className: "hr-cats" }, cats.map(([c, label]) =>
      el("button", { className: `hr-cat${ui.buildCat === c ? " on" : ""}`, onclick: () => pick(c) }, label)));
    const items = buildable.filter(([, d]) => d.category === ui.buildCat).map(([id, d]) => {
      const poor = !canPay(ctx, d.cost);
      const si = structInfo(content, d);
      const card = () => [el("h3", {}, `${d.icon || ""} ${d.name}`), poor ? el("p", { className: "neg small" }, HexText.hud.cantAfford) : null,
        structCard(content, d), el("p", { className: "small" }, `Build: ${si.build}`), el("p", { className: "small muted" }, `On: ${si.terrains}`)];
      const active = ui.mode?.type === "build" && ui.mode.kind === id;
      // Not `disabled` when you can't afford it: disabled buttons get no hover events in some browsers.
      return el("button", { className: `hr-build${active ? " on" : ""}${poor ? " poor" : ""}`,
        onmouseenter: (e) => showCard(e.currentTarget, card()), onmouseleave: hideCard,
        onclick: () => (poor ? null : active ? act.setMode(null) : act.setMode({ type: "build", kind: id, rot: ui.lastRot || 0 })) },
        el("span", { className: "hr-bicon" }, d.icon || "▪"), el("span", { className: "hr-bname" }, d.name), el("span", { className: "hr-bcost small" }, costText(d.cost)));
    });
    fill(box, tabs,
      ui.buildCat ? el("div", { className: "hr-buildgrid" }, items) : el("p", { className: "muted small" }, HexText.hud.pickCategory),
      el("p", { className: "muted small" }, HexText.hud.buildHelp));
  }


  window.HexHud = { topbar, players, selection, orders, build, structCard, fmt: { costText, canPay, nameSpan, btn, cap, setResources, resIcon, resName, structInfo, resListEl } };
})();
