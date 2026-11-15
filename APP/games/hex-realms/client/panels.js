/*
 * Hex Realms: the tech tree (game.js shows it in a popup over the map) and the last-turn report (events as readable lines, plus the history log).
 *
 *   HexPanels.techTree(el, ctx, currency)   the advances bought with `currency` drawn as a tree (columns by
 *                                 prerequisite depth, lines prerequisite -> advance), each with its cost, text,
 *                                 status (researched / queued / ready / can't afford / locked) and Research button
 *   HexPanels.currencies(content)  the currencies advances are bought with (science, faith), one tab each
 *   HexPanels.report(el, ctx)     game.events (last resolution) with dice faces, then game.log
 *   HexPanels.flashCells(game)    [{at, kind}] for the map's event markers
 *
 * ctx is the one built in game.js (see hud.js). Event shapes come from logic/combat.py, match.py, economy.py.
 */
(() => {
  const { el, fill, svg } = AppDom;
  const { costText, canPay, nameSpan, btn } = HexHud.fmt;

  // Advances are bought with one currency (science or faith): the first key of their cost.
  const currencyOf = (a) => Object.keys(a.cost || {})[0] || "science";
  const currencies = (content) => {
    const found = new Set(Object.values(content.advances).map(currencyOf));
    return ["science", "faith", ...found].filter((c, i, all) => found.has(c) && all.indexOf(c) === i);
  };

  const NODE_W = 230, NODE_H = 132, GAP_X = 70, GAP_Y = 18;

  // The advances bought with `currency`, as a tree: columns by depth (one more than the deepest
  // prerequisite in the same tree), each advance placed level with (the middle of) its prerequisites
  // where there's room, and a line from each prerequisite to the advances it opens.
  function techTree(box, ctx, currency) {
    const { content, me, priv, act } = ctx;
    const A = content.advances;
    const owned = new Set(me.advances || []);
    const queued = new Set(priv.orders.research.map((r) => r.advance));
    const ids = Object.keys(A).filter((id) => currencyOf(A[id]) === currency);
    const inTree = new Set(ids);
    const parents = (id) => A[id].after.filter((x) => inTree.has(x));
    const depth = {};
    const depthOf = (id, seen = new Set()) => {
      if (id in depth) return depth[id];
      if (seen.has(id)) return 0;  // a loop in the content: don't recurse forever
      seen.add(id);
      const ps = parents(id);
      return (depth[id] = ps.length ? 1 + Math.max(...ps.map((p) => depthOf(p, seen))) : 0);
    };
    ids.forEach((id) => depthOf(id));
    const cols = [];
    for (const id of ids) (cols[depth[id]] ||= []).push(id);
    const row = {};
    for (const col of cols.filter(Boolean)) {
      const want = (id) => { const ps = parents(id); return ps.length ? ps.reduce((t, p) => t + row[p], 0) / ps.length : -1; };
      col.sort((a, b) => want(a) - want(b) || A[a].name.localeCompare(A[b].name));
      let next = 0;
      for (const id of col) { row[id] = Math.max(next, Math.round(want(id))); next = row[id] + 1; }
    }
    const pos = (id) => [depth[id] * (NODE_W + GAP_X), row[id] * (NODE_H + GAP_Y)];
    const width = Math.max(1, cols.length) * (NODE_W + GAP_X) - GAP_X;
    const height = (Math.max(0, ...Object.values(row)) + 1) * (NODE_H + GAP_Y) - GAP_Y;

    const links = ids.flatMap((id) => parents(id).map((p) => {
      const [px, py] = pos(p), [cx, cy] = pos(id);
      const x1 = px + NODE_W, y1 = py + NODE_H / 2, x2 = cx, y2 = cy + NODE_H / 2;
      return svg("path", { class: `hr-tlink${owned.has(p) ? " done" : ""}`, d: `M${x1},${y1} C${x1 + GAP_X / 2},${y1} ${x2 - GAP_X / 2},${y2} ${x2},${y2}` });
    }));
    const nodes = ids.map((id) => {
      const a = A[id], [x, y] = pos(id);
      const missing = a.after.filter((x) => !owned.has(x));
      const why = missing.length ? `Research ${missing.map((x) => A[x]?.name || x).join(", ")} first` : !canPay(ctx, a.cost) ? "Can't afford" : "";
      const status = owned.has(id) ? "owned" : queued.has(id) ? "queued" : missing.length ? "locked" : why ? "poor" : "ready";
      const other = a.after.filter((x) => !inTree.has(x));  // prerequisites from the other tree
      return el("div", { className: `hr-tnode ${status}`, style: `left:${x}px;top:${y}px;width:${NODE_W}px;height:${NODE_H}px` },
        el("div", { className: "row" }, el("b", {}, owned.has(id) ? "✓ " : "", a.name), el("span", { className: "spacer" }), el("span", { className: "small" }, costText(a.cost))),
        el("div", { className: "small muted hr-ttext" }, a.text),
        other.length ? el("div", { className: "small muted" }, `After: ${other.map((x) => A[x]?.name || x).join(", ")}`) : null,
        el("div", { className: "hr-tfoot" }, owned.has(id) ? el("span", { className: "small pos" }, "Researched")
          : queued.has(id) ? el("span", { className: "small pos" }, "Queued: learnt as the turn resolves")
          : btn("Research", () => act.send({ action: "research", advance: id }), { disabled: !!why, title: why }),
          !owned.has(id) && !queued.has(id) && why ? el("span", { className: "small muted" }, ` ${why}`) : null));
    });
    fill(box, el("div", { className: "hr-tree", style: `width:${width}px;height:${height}px` },
      svg("svg", { width, height }, links), nodes));
  }

  const die = (x, need) => el("span", { className: `hr-die${x >= need ? " hit" : ""}` }, String(x));
  const dice = (roll, need) => el("span", { className: "hr-dice" }, (roll || []).map((x) => die(x, need)));

  function report(box, ctx) {
    const { game, content, you } = ctx;
    const unitName = (t) => content.units[t]?.name || t;
    const structName = (t) => content.structures[t]?.name || t;
    const needOf = (s) => s.need || (content.terrain[game.cells[s.at]]?.cover ? 5 : 4);  // the roll that hits unit side s
    const who = (s) => el("span", {}, nameSpan(game, s.owner), ` ${unitName(s.type)}`);
    const where = (at) => (at ? el("a", { className: "hr-cell-link", onclick: () => ctx.act.centre(at), title: "Show on the map" }, ` @${at}`) : null);
    const line = (...kids) => el("div", { className: "hr-ev" }, ...kids);
    const evs = Object.keys(game.events || {}).sort((a, b) => a - b).map((i) => game.events[i]);
    const lines = [];
    for (const e of evs) {
      switch (e.t) {
        case "battle": {
          const rounds = e.rounds.map(([ra, rb], i) => el("div", { className: "hr-round" }, `R${i + 1} `, dice(ra, needOf(e.b)), " vs ", dice(rb, needOf(e.a))));
          lines.push(line(el("b", {}, "Battle "), who(e.a), " attacks ", who(e.b), where(e.b.at), rounds,
            e.dead.length ? el("div", { className: "neg small" }, `Dead: ${e.dead.map((u) => (u === e.a.unit ? unitName(e.a.type) : unitName(e.b.type))).join(", ")}`) : el("div", { className: "muted small" }, "Both survive.")));
          break;
        }
        case "shot":
          lines.push(line(el("b", {}, "Shot "), who(e.a), " fires at ", e.b ? who(e.b) : `${structName(e.stype)}`, where(e.at || e.b?.at), " ", dice(e.roll, e.b ? needOf(e.b) : 4),
            e.b ? (e.dead.length ? el("span", { className: "neg" }, " dead") : ` ${e.hits} hit${e.hits === 1 ? "" : "s"}`) : ` ${e.damage} damage`));
          break;
        case "siege":
          lines.push(line(el("b", {}, "Siege "), who(e.a), ` assaults ${structName(e.stype)} of `, nameSpan(game, e.owner), where(e.at), " ", dice(e.roll, 4),
            ` ${e.damage} damage; defenders `, dice(e.back, 4), e.dead.length ? el("span", { className: "neg" }, " attacker dead") : null));
          break;
        case "tower":
          lines.push(line(el("b", {}, "Tower "), nameSpan(game, e.owner), " tower fires at ", who(e.b), where(e.b.at), " ", dice(e.roll, needOf(e.b)), e.dead.length ? el("span", { className: "neg" }, " dead") : ` ${e.hits} hit${e.hits === 1 ? "" : "s"}`));
          break;
        case "destroyed":
          lines.push(line(el("b", { className: "neg" }, "Destroyed "), nameSpan(game, e.owner), ` ${structName(e.type)}`, e.by ? [" by ", nameSpan(game, e.by)] : null, where(e.at)));
          break;
        case "built": lines.push(line("Built ", nameSpan(game, e.owner), ` ${structName(e.type)}`, where(e.at))); break;
        case "site": lines.push(line("Started building ", nameSpan(game, e.owner), ` ${structName(e.type)}`, where(e.at))); break;
        case "failed":
          if (e.owner === you) lines.push(line(el("span", { className: "neg" }, "Failed: "), `${e.what === "claim" ? "Land claim" : content.structures[e.what]?.name || unitName(e.what)} — ${e.why}`, where(e.at)));
          break;
        case "recruited": lines.push(line("Recruited ", nameSpan(game, e.owner), ` ${unitName(e.type)}`, where(e.at))); break;
        case "founded": lines.push(line(el("b", {}, "Founded "), nameSpan(game, e.owner), " a new city", where(e.at))); break;
        case "research": lines.push(line("Researched ", nameSpan(game, e.owner), ` ${content.advances[e.advance]?.name || e.advance}`)); break;
        case "starve": lines.push(line(el("span", { className: "neg" }, "Famine "), nameSpan(game, e.owner), ` ran out of food: ${e.n || 1} ${(e.n || 1) === 1 ? "person" : "people"} starved`)); break;
        case "starved": lines.push(line(el("span", { className: "neg" }, "Famine "), nameSpan(game, e.owner), ` ${unitName(e.type)} starved`, where(e.at))); break;
        case "landLost": lines.push(line(el("span", { className: "neg" }, "Unpaid land "), nameSpan(game, e.owner), ` gave up ${e.n} cell${e.n === 1 ? "" : "s"} of bought land (not enough gold for its upkeep)`)); break;
        case "desert": lines.push(line(el("span", { className: "neg" }, "Desertion "), nameSpan(game, e.owner), ` ${unitName(e.type)} left`, where(e.at))); break;
        case "eliminated": lines.push(line(el("b", { className: "neg" }, "Eliminated "), nameSpan(game, e.owner))); break;
        default: break;
      }
    }
    const log = Object.keys(game.log || {}).sort((a, b) => a - b).map((i) => game.log[i]).slice(-20).reverse();
    fill(box, el("h3", {}, "Last turn"), lines.length ? lines : el("p", { className: "muted small" }, "Nothing happened."),
      el("h3", {}, "History"), log.length ? log.map((t) => el("div", { className: "small hr-log" }, t)) : el("p", { className: "muted small" }, "Empty."));
  }

  function flashCells(game) {
    const out = [];
    for (const i of Object.keys(game.events || {})) {
      const e = game.events[i];
      if (e.t === "battle") out.push({ at: e.b.at, kind: "battle" });
      else if (e.t === "siege" || e.t === "destroyed") out.push({ at: e.at, kind: "siege" });
      else if (e.t === "shot" || e.t === "tower") out.push({ at: e.b?.at || e.at, kind: "shot" });
    }
    return out;
  }

  window.HexPanels = { techTree, currencies, report, flashCells };
})();
