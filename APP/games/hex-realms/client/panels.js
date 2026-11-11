/*
 * Hex Realms: the research panel and the last-turn report (events as readable lines, plus the history log).
 *
 *   HexPanels.advances(el, ctx)   every advance: cost, prerequisites, text, owned tick, queued, Research button
 *   HexPanels.report(el, ctx)     game.events (last resolution) with dice faces, then game.log
 *   HexPanels.flashCells(game)    [{at, kind}] for the map's event markers
 *
 * ctx is the one built in game.js (see hud.js). Event shapes come from logic/combat.py, match.py, economy.py.
 */
(() => {
  const { el, fill } = AppDom;
  const { costText, canPay, nameSpan, btn } = HexHud.fmt;

  function advances(box, ctx) {
    const { content, me, priv, act } = ctx;
    const owned = new Set(me.advances || []);
    const queued = new Set(priv.orders.research.map((r) => r.advance));
    fill(box, Object.entries(content.advances).map(([id, a]) => {
      const missing = a.after.filter((x) => !owned.has(x));
      const why = owned.has(id) ? "" : queued.has(id) ? "" : missing.length ? `Research ${missing.map((x) => content.advances[x]?.name || x).join(", ")} first`
        : !canPay(ctx, a.cost) ? "Can't afford" : "";
      return el("div", { className: `hr-adv${owned.has(id) ? " owned" : ""}` },
        el("div", { className: "row" }, el("b", {}, owned.has(id) ? "✓ " : "", a.name), el("span", { className: "spacer" }), el("span", { className: "small" }, costText(a.cost))),
        el("div", { className: "small muted" }, a.text),
        a.after.length ? el("div", { className: "small muted" }, `After: ${a.after.map((x) => content.advances[x]?.name || x).join(", ")}`) : null,
        owned.has(id) ? null : queued.has(id) ? el("div", { className: "small pos" }, "Queued") : btn("Research", () => act.send({ action: "research", advance: id }), { disabled: !!why, title: why }));
    }));
  }

  const die = (x, need) => el("span", { className: `hr-die${x >= need ? " hit" : ""}` }, String(x));
  const dice = (roll, need) => el("span", { className: "hr-dice" }, (roll || []).map((x) => die(x, need)));

  function report(box, ctx) {
    const { game, content, you } = ctx;
    const unitName = (t) => content.units[t]?.name || t;
    const structName = (t) => content.structures[t]?.name || t;
    const needAt = (at) => (content.terrain[game.cells[at]]?.cover ? 5 : 4);
    const who = (s) => el("span", {}, nameSpan(game, s.owner), ` ${unitName(s.type)}`);
    const where = (at) => (at ? el("a", { className: "hr-cell-link", onclick: () => ctx.act.centre(at), title: "Show on the map" }, ` @${at}`) : null);
    const line = (...kids) => el("div", { className: "hr-ev" }, ...kids);
    const evs = Object.keys(game.events || {}).sort((a, b) => a - b).map((i) => game.events[i]);
    const lines = [];
    for (const e of evs) {
      switch (e.t) {
        case "battle": {
          const rounds = e.rounds.map(([ra, rb], i) => el("div", { className: "hr-round" }, `R${i + 1} `, dice(ra, needAt(e.b.at)), " vs ", dice(rb, needAt(e.a.at))));
          lines.push(line(el("b", {}, "Battle "), who(e.a), " attacks ", who(e.b), where(e.b.at), rounds,
            e.dead.length ? el("div", { className: "neg small" }, `Dead: ${e.dead.map((u) => (u === e.a.unit ? unitName(e.a.type) : unitName(e.b.type))).join(", ")}`) : el("div", { className: "muted small" }, "Both survive.")));
          break;
        }
        case "shot":
          lines.push(line(el("b", {}, "Shot "), who(e.a), " fires at ", e.b ? who(e.b) : `${structName(e.stype)}`, where(e.at || e.b?.at), " ", dice(e.roll, e.b ? needAt(e.b.at) : 4),
            e.b ? (e.dead.length ? el("span", { className: "neg" }, " dead") : ` ${e.hits} hit${e.hits === 1 ? "" : "s"}`) : ` ${e.damage} damage`));
          break;
        case "siege":
          lines.push(line(el("b", {}, "Siege "), who(e.a), ` assaults ${structName(e.stype)} of `, nameSpan(game, e.owner), where(e.at), " ", dice(e.roll, 4),
            ` ${e.damage} damage; defenders `, dice(e.back, 4), e.dead.length ? el("span", { className: "neg" }, " attacker dead") : null));
          break;
        case "tower":
          lines.push(line(el("b", {}, "Tower "), nameSpan(game, e.owner), " tower fires at ", who(e.b), where(e.b.at), " ", dice(e.roll, needAt(e.b.at)), e.dead.length ? el("span", { className: "neg" }, " dead") : ` ${e.hits} hit${e.hits === 1 ? "" : "s"}`));
          break;
        case "destroyed":
          lines.push(line(el("b", { className: "neg" }, "Destroyed "), nameSpan(game, e.owner), ` ${structName(e.type)}`, e.by ? [" by ", nameSpan(game, e.by)] : null, where(e.at)));
          break;
        case "built": lines.push(line("Built ", nameSpan(game, e.owner), ` ${structName(e.type)}`, where(e.at))); break;
        case "failed":
          if (e.owner === you) lines.push(line(el("span", { className: "neg" }, "Failed: "), `${content.structures[e.what]?.name || unitName(e.what)} — ${e.why}`, where(e.at)));
          break;
        case "recruited": lines.push(line("Recruited ", nameSpan(game, e.owner), ` ${unitName(e.type)}`, where(e.at))); break;
        case "founded": lines.push(line(el("b", {}, "Founded "), nameSpan(game, e.owner), " a new city", where(e.at))); break;
        case "research": lines.push(line("Researched ", nameSpan(game, e.owner), ` ${content.advances[e.advance]?.name || e.advance}`)); break;
        case "starve": lines.push(line(el("span", { className: "neg" }, "Famine "), nameSpan(game, e.owner), " ran out of food")); break;
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

  window.HexPanels = { advances, report, flashCells };
})();
