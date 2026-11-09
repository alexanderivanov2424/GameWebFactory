/*
 * Bastion: BastionPanels, the page's read-mostly panels. game.js owns the state and what the
 * player is doing (selection, tile tool, picks) and passes a context; this file draws:
 *
 *   const panels = BastionPanels.create(ctx)
 *     ctx: { state(), game(), priv(), you(), icon(key), amounts(obj), affordable(cost), nameOf(pid),
 *            send(message), myTurn(), placing(), mine(target), placeOf(target), tileStock(kind),
 *            unitClick(target, event), takeBack(target), resolve(target, {tool, from}) }
 *   panels.status()      the status bar: round, phase, enemy timing, keep, stockpile (wheat 🌾,
 *                        bread 🍞...), soldiers, population, hungry, next upkeep, road / wall
 *                        stock, carriages
 *   panels.roundBar()    what to do now (units to place / to resolve), the turn order with who is
 *                        ready or acting, and the Hauling pool (a click target)
 *   panels.foes()        enemy cards: attacks (▶ next), ways to beat it, Strike / Bonfire buttons,
 *                        and the Fighting pool on enemies units may fight
 *   panels.market()      the 6 offers (blueprints with their bundle, "House ×3") and Reroll
 *   panels.log()         the chronicle, newest first
 *   panels.inspector(uid, {tool, selection, pick, hover})   the side panel's inspector: the tile
 *                        tool, the blueprint in hand, an open pick (work with / without a tool,
 *                        or which building a haul takes from: buttons that resolve), the building
 *                        under the mouse (output and bonuses, link, unit there this round, preview,
 *                        population, store, damage) or an enemy tile
 *   panels.cardEl(id, {off, selected, marked})   a card face (hand, deck window)
 *   panels.kindInfo(kind) / panels.partsList(parts)   building details (inspector)
 * Pools ("haul", "fight<i>") show each player's units as coloured tokens; one-unit targets are
 * drawn on the board (board.js).
 */
const BastionPanels = (() => {
  const { $, el } = AppDom;
  const signed = (n) => (n > 0 ? `+${n}` : String(n));
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  function create(ctx) {
    const { game, icon, amounts } = ctx;
    const { priv, you, nameOf, myTurn, placeOf, tileStock, resolve } = ctx;
    const cardOf = (id) => game().cards[id];
    const isBuild = (id) => cardOf(id).kind === "build";
    // What the player is doing, as game.js passed it to inspector().
    let tool = null;
    let selection = null;
    let pick = null;
    let hover = null;

    // --- cards and building details --------------------------------------------------------

    function shapeEl(cells) {
      const w = Math.max(...cells.map((c) => c[0])) + 1;
      const h = Math.max(...cells.map((c) => c[1])) + 1;
      const filled = new Set(cells.map(([x, y]) => `${x},${y}`));
      const box = el("div", { className: "shape" });
      box.style.gridTemplateColumns = `repeat(${w}, 9px)`;
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) box.append(el("i", { className: filled.has(`${x},${y}`) ? "" : "e" }));
      return box;
    }

    function cardEl(cardId, { off = false, selected = false, marked = false } = {}) {
      const card = game().cards[cardId];
      const kind = card.kind === "build" ? game().kinds[card.structure] : null;
      const node = el("div", { className: `pcard ${card.kind}${off ? " off" : ""}${selected ? " sel" : ""}${marked ? " marked" : ""}` });
      node.append(el("div", { className: "name", textContent: card.name }));
      node.append(el("div", { className: "kind", textContent: { build: "Blueprint", action: "Action", curse: "Curse" }[card.kind] }));
      if (kind) {
        node.append(el("span", { className: "icon", textContent: kind.icon || "" }));
        node.append(shapeEl(kind.rotations[0]));
        node.title = kind.text;
      }
      node.append(el("div", { className: "text", textContent: card.text }));
      return node;
    }

    function partsList(parts) {
      return el("ul", { className: "parts" }, ...parts.map(([why, n]) =>
        el("li", { className: n < 0 ? "minus" : "plus" }, `${signed(n)} ${why}`)));
    }

    function kindInfo(kind) {
      const lines = [];
      if (kind.work) {
        const key = Object.keys(kind.work.makes)[0];
        const uses = Object.keys(kind.work.uses || {}).length ? `${amounts(kind.work.uses)} → ` : "";
        lines.push(el("div", {}, el("b", {}, "A unit working it: "), `${uses}${kind.work.makes[key]}${icon(key)}`));
      }
      if (kind.population) lines.push(el("div", {}, el("b", {}, "Home to "), plural(kind.population, "person").replace("persons", "people")));
      if (kind.requires && kind.requires.length) lines.push(el("div", {}, el("b", {}, "Must be "), kind.requires.join(", ")));
      if (kind.bonuses && kind.bonuses.length) {
        lines.push(el("div", {}, el("b", {}, "Likes / hates:")));
        lines.push(partsList(kind.bonuses));
      }
      if (Object.keys(kind.cost || {}).length) lines.push(el("div", {}, el("b", {}, "Cost: "), amounts(kind.cost)));
      if (kind.text) lines.push(el("div", { className: "muted" }, kind.text));
      return lines;
    }

    // --- status bar ---------------------------------------------------------------------------

    function phaseText() {
      const g = game();
      const s = ctx.state();
      if (s.phase === "finished") return "Game over";
      if (g.phase === "place") {
        if (!g.seats[ctx.you()]) return "Everyone is placing units";
        return g.ready[ctx.you()] ? "Ready: waiting for the others" : "Place your units";
      }
      if (!g.turn) return "End of the round";
      return g.turn === ctx.you() ? "Your turn" : `${ctx.nameOf(g.turn)}'s turn`;
    }

    function enemyText() {
      const g = game();
      const coming = Object.values(g.foes).filter((f) => f.state === "coming").map((f) => f.arrives);
      if (!coming.length) return `Every enemy is here: beat them all by the end of round ${g.deadline}`;
      const next = Math.min(...coming);
      const active = Object.values(g.foes).some((f) => f.state === "active");
      return active ? `Next enemy: round ${next}` : `Peace until round ${next}`;
    }

    const pill = (text, title, { zero = false, warn = false } = {}) =>
      el("span", { className: `pill${zero ? " zero" : ""}${warn ? " warn" : ""}`, title }, text);

    function status() {
      const g = game();
      const keep = el("span", { className: "pill", title: "The keep: at 0 the game is lost" }, "🏰 ",
        el("span", { className: "meter" }, el("span", { style: `width:${Math.round((100 * g.keep) / g.keepMax)}%` })),
        ` ${g.keep}/${g.keepMax}`);
      const stock = g.resources.map(([id, name, ic]) => pill(`${ic} ${g.stock[id] || 0}`, name, { zero: !g.stock[id] }));
      const u = g.upkeep || {};
      const eats = amounts({ bread: u.bread || 0, wheat: u.wheat || 0 }) || "nothing";
      const feeds = g.feeds || {};
      const road = g.kinds.road;
      const wall = g.kinds.wall;
      const batch = g.tileBatch;
      $("status").replaceChildren(
        el("span", { className: "round" }, `Round ${g.round}`),
        el("span", { className: "phase-now" }, phaseText()),
        el("span", { className: "phase" }, enemyText()),
        el("span", { className: "break" }),
        keep, ...stock,
        pill(`${icon("soldiers")} ${g.soldiers}`, "Soldiers (from barracks): spend them with Strike on an enemy card or by clicking an enemy tile", { zero: !g.soldiers }),
        el("span", { className: "sep" }),
        pill(`👥 ${g.population}`, "Population: people living in houses and the keep. Each round the fed ones become units."),
        pill(`😫 ${g.hungry} hungry`, "People the last upkeep couldn't feed: they don't become units this round.", { zero: !g.hungry, warn: g.hungry > 0 }),
        pill(`🍽️ next upkeep: ${eats}${u.hungry ? `, ${u.hungry} hungry` : ""}`,
          `What the city eats at the end of this round with the current stock (bread feeds ${feeds.bread}, wheat feeds ${feeds.wheat}; least food first).`,
          { warn: u.hungry > 0 }),
        el("span", { className: "sep" }),
        pill(`${road.icon} ${g.roadStock}`, `Road tiles in stock. With none left, the next road buys ${batch} for ${amounts(road.cost)}.`, { zero: !g.roadStock }),
        pill(`${wall.icon} ${g.wallStock}`, `Wall tiles in stock. With none left, the next wall buys ${batch} for ${amounts(wall.cost)}.`, { zero: !g.wallStock }),
        pill(`🛒 ${g.carriages}`, `Carriages: each round the first ${g.carriages} hauls carry ${g.haulSizes.big} goods instead of ${g.haulSizes.small}.`, { zero: !g.carriages }));
    }

    // --- round bar: what to do, turn order, Hauling pool --------------------------------------

    function tokens(by) {
      const g = game();
      const list = [];
      for (const [pid, n] of Object.entries(by || {})) {
        for (let i = 0; i < n; i++) {
          const t = el("span", { className: `token${pid === ctx.you() ? " mine" : ""}`, title: ctx.nameOf(pid) });
          t.style.background = g.colors[pid] || "#888";
          list.push(t);
        }
      }
      return list;
    }

    // A pool box ("haul" or "fight<i>"): click = place a unit (place phase) or resolve one (your turn).
    function poolEl(target, label, extra) {
      const g = game();
      const p = ctx.priv();
      const place = p && p.places ? p.places[target] : null;
      const mine = ctx.mine(target);
      const can = (ctx.placing() && place && (g.units[ctx.you()] || {}).free > 0) || (ctx.myTurn() && mine > 0);
      const box = el("div", { className: `pool${can ? " can" : ""}${ctx.myTurn() && mine ? " act" : ""}` });
      box.append(el("div", { className: "pool-head" }, el("b", {}, label), extra || ""));
      const by = g.placements[target] || {};
      const row = el("div", { className: "pool-units" }, ...tokens(by));
      if (!Object.keys(by).length) row.append(el("span", { className: "muted small" }, "no units"));
      box.append(row);
      let tip = place ? place.text + (place.why ? ` (${place.why})` : "") : "";
      if (ctx.placing() && place) tip = `Click: place a unit (Shift+click: all your free units) · ${tip}`;
      else if (ctx.myTurn() && mine) {
        const all = target.startsWith("fight") && mine > 1 ? ` (Shift+click: all ${mine})` : "";
        tip = place && place.why ? place.why : `Click: ${tip}${all}`;
      }
      box.title = tip;
      box.addEventListener("click", (e) => ctx.unitClick(target, e));
      if (ctx.placing() && mine) {
        const back = el("button", { className: "small plain", textContent: "Take back" });
        back.addEventListener("click", (e) => {
          e.stopPropagation();
          ctx.takeBack(target);
        });
        box.append(back);
      }
      return box;
    }

    function orderChip(pid, i) {
      const g = game();
      const seat = g.seats[pid];
      const units = g.units[pid] || { total: 0, free: 0, placed: 0 };
      let what;
      let cls = "";
      if (g.phase === "place") {
        if (g.ready[pid]) {
          what = "✓ ready";
          cls = " ready";
        } else what = units.free ? `${units.free} to place` : "placing…";
      } else {
        const at = g.order.indexOf(g.turn);
        if (pid === g.turn) {
          what = `▶ acting${units.placed ? ` (${plural(units.placed, "unit")})` : ""}`;
          cls = " now";
        } else if (at >= 0 && i < at) {
          what = "done";
          cls = " done";
        } else what = units.placed ? `waiting (${plural(units.placed, "unit")})` : "waiting";
      }
      const title = seat ? `${seat.name}: ${plural(units.total, "unit")} this round · ${seat.deck.length} cards in deck` : pid;
      return el("span", { className: `chip${cls}${pid === ctx.you() ? " you" : ""}`, title },
        el("span", { className: "dot", style: `background:${g.colors[pid] || "#888"}` }),
        `${i === 0 ? "★ " : ""}${ctx.nameOf(pid)}${pid === ctx.you() ? " (you)" : ""}: ${what}`);
    }

    function roundBar() {
      const g = game();
      const you = ctx.you();
      const mineUnits = g.units[you] || null;
      let head;
      if (ctx.state().phase === "finished") head = "The game is over.";
      else if (g.phase === "place") {
        if (!mineUnits) head = "The builders are placing their units.";
        else if (g.ready[you]) head = "You're ready. Waiting for the others…";
        else if (!mineUnits.total) head = "You have no units this round (the city is small or hungry): click Ready.";
        else if (mineUnits.free) head = `${plural(mineUnits.free, "unit")} to place: click an outlined building, Hauling, an enemy's Fighting pool or an enemy tile.`;
        else head = "All your units are placed: click Ready (click one of yours to take it back).";
      } else if (g.turn === you) {
        head = mineUnits && mineUnits.placed
          ? `Your turn: ${plural(mineUnits.placed, "unit")} to resolve (outlined): click one to make it act. Then play cards, buy, build and End turn.`
          : "Your turn: play cards, buy, build, then End turn.";
      } else head = g.turn ? `${ctx.nameOf(g.turn)} is acting.` : "";
      const order = el("div", { className: "order" }, el("span", { className: "muted small" }, "Turn order:"),
        ...g.order.map((pid, i) => orderChip(pid, i)));
      $("round-info").replaceChildren(el("div", { className: "head" }, head), order);
      const h = g.hauls || {};
      const sizes = h.queue && h.queue.length > 1 ? `: hauls carry ${h.queue.join(", ")} goods` : `: carries ${h.next} goods`;
      $("haul-pool").replaceChildren(poolEl("haul", "🛒 Hauling", el("span", { className: "muted small" }, sizes)));
    }

    // --- enemies ------------------------------------------------------------------------------

    function foes() {
      const g = game();
      const list = Object.entries(g.foes).sort((a, b) => Number(a[0]) - Number(b[0]));
      $("foes").replaceChildren(...list.map(([index, foe]) => foeEl(Number(index), foe)));
    }

    function foeEl(index, foe) {
      if (foe.state === "coming") {
        return el("div", { className: "foe coming" },
          el("div", {}, el("div", { className: "icon" }, "❔"), el("div", {}, `Arrives on round ${foe.arrives}`)));
      }
      if (foe.state === "defeated") {
        return el("div", { className: "foe defeated" },
          el("div", { className: "head" }, el("span", { className: "icon" }, foe.icon), foe.name), el("div", {}, "Beaten"));
      }
      const g = game();
      const node = el("div", { className: "foe" });
      node.append(el("div", { className: "head" }, el("span", { className: "icon" }, foe.icon), foe.name));
      node.append(el("div", { className: "hp" },
        el("span", { className: "meter foe" }, el("span", { style: `width:${Math.round((100 * foe.hp) / foe.maxHp)}%` })),
        `${foe.hp}/${foe.maxHp}`));
      if (foe.text) node.append(el("div", { className: "text" }, foe.text));
      const list = el("ol");
      foe.attacks.forEach((a, i) => list.append(el("li", { className: i === foe.next ? "next" : "", title: a.text },
        el("b", {}, a.name), `: ${a.text}`)));
      node.append(list);
      const beat = el("div", { className: "beat" }, el("b", {}, "Beat it: "));
      const d = foe.defeat;
      if (d.soldiers) {
        const left = Math.max(0, d.soldiers - (foe.strikes || 0));
        const most = Math.min(foe.hp, Math.floor((g.soldiers + (foe.strikes || 0)) / d.soldiers));
        beat.append(`${d.soldiers}${icon("soldiers")} (or fighting units) per damage.`);
        if (foe.strikes) beat.append(el("div", { className: "strikes" }, `Strikes so far: ${foe.strikes}/${d.soldiers} (${left} more for the next damage)`));
        beat.append(el("br"));
        beat.append(strikeButton(index, "soldiers", 1, `Strike (${left}${icon("soldiers")})`, g.soldiers >= left));
        if (most > 1) beat.append(strikeButton(index, "soldiers", most, `All in ×${most}`, true));
      }
      if (d.resources) {
        beat.append(el("div", {}, `${amounts(d.resources)} per damage.`));
        beat.append(strikeButton(index, "resources", 1, `Bonfire (${amounts(d.resources)})`, ctx.affordable(d.resources)));
      }
      if (d.cure) beat.append(el("div", {}, "Each building of its plague you cure deals 1 damage."));
      if (d.cards) beat.append(el("div", {}, "Each of its curse cards you pay off deals 1 damage."));
      if (d.raze) beat.append(el("div", {}, `Raze every ${foe.lair} tile on the board (units on the tile, or ${d.raze}${icon("soldiers")} each: click it).`));
      node.append(beat);
      if (foe.fight) node.append(poolEl(`fight${index}`, "⚔️ Fighting", el("span", { className: "muted small" }, " 1 strike per unit")));
      return node;
    }

    function strikeButton(foe, way, times, label, enabled) {
      const button = el("button", { className: "small", textContent: label });
      button.disabled = !enabled || !ctx.myTurn();
      button.addEventListener("click", () => ctx.send({ action: "strike", foe, way, times }));
      return button;
    }

    // --- market and log -----------------------------------------------------------------------

    function market() {
      const g = game();
      const reroll = $("reroll");
      reroll.textContent = `Reroll ${g.rerollCost}${icon("gold")}`;
      reroll.disabled = !ctx.myTurn() || g.stock.gold < g.rerollCost;
      $("market").replaceChildren(...g.market.map((cardId, slot) => {
        const card = g.cards[cardId];
        const kind = card.kind === "build" ? g.kinds[card.structure] : null;
        const bundle = card.bundle > 1 ? ` ×${card.bundle}` : "";
        const price = card.price || 0;
        const buy = el("button", { className: "small", textContent: `Buy ${price}${icon("gold")}` });
        buy.disabled = !ctx.myTurn() || g.stock.gold < price;
        buy.addEventListener("click", () => ctx.send({ action: "buy", slot }));
        const sub = kind ? `Blueprint${bundle ? ` (${card.bundle} copies)` : ""}: ${amounts(kind.cost)} to build. ${kind.text}` : card.text;
        return el("div", { className: "offer", title: sub },
          el("div", { className: "what" }, el("b", {}, `${kind ? `${kind.icon} ` : ""}${card.name}${bundle}`),
            el("span", {}, kind ? `Blueprint · builds for ${amounts(kind.cost) || "free"}` : card.text)), buy);
      }));
    }

    function log() {
      const g = game();
      const lines = [];
      for (let i = g.logCount - 1; i >= Math.max(0, g.logCount - 80); i--) {
        const entry = g.log[String(i)];
        if (entry) lines.push(el("p", {}, el("span", { className: "r" }, `R${entry.round} `), entry.text));
      }
      $("log").replaceChildren(...lines);
    }

    // The source a haul takes from by default: the most goods waiting (lowest uid on a tie).
    function biggestSource() {
      let best = null;
      let most = -1;
      for (const uid of Object.keys(priv().sources || {}).sort((a, b) => Number(a) - Number(b))) {
        const s = game().structures[uid];
        const n = s ? Object.values(s.store).reduce((a, b) => a + b, 0) : 0;
        if (n > most) {
          best = uid;
          most = n;
        }
      }
      return best;
    }

    // --- inspector -----------------------------------------------------------------------------

    const hint = (text) => el("div", { className: "muted small" }, text);

    function button(label, onClick, { cls = "small", disabled = false, title = "" } = {}) {
      const b = el("button", { className: cls, textContent: label, disabled, title });
      b.addEventListener("click", onClick);
      return b;
    }

    function pickPanel() {
      const g = game();
      if (pick.target === "haul") {
        const sources = priv().sources || {};
        const best = biggestSource();
        const list = Object.entries(sources).map(([uid, text]) => {
          const s = g.structures[uid];
          const kind = s ? g.kinds[s.kind] : { icon: "", name: "?" };
          return button(`${kind.icon} ${kind.name}: ${text}${uid === best ? " (biggest)" : ""}`,
            () => resolve("haul", { from: Number(uid) }), { cls: "small plain wide" });
        });
        const h = g.hauls || {};
        return [el("h3", {}, "🛒 Haul from where?"),
          el("div", {}, `This haul carries ${h.next} goods, biggest piles first, straight to the stockpile.`),
          el("div", { className: "choices" }, ...list),
          hint("Click an outlined building or a button · right-click or Esc: cancel")];
      }
      const s = g.structures[pick.target.slice(1)];
      const kind = s ? g.kinds[s.kind] : { icon: "", name: "Building" };
      const place = placeOf(pick.target) || { text: "", tool: "" };
      return [el("h3", {}, `${kind.icon} Work the ${kind.name}`),
        el("div", { className: "choices" },
          button(`Work: ${place.text}`, () => resolve(pick.target), { cls: "small green wide" }),
          button(`With a tool: ${place.tool}`, () => resolve(pick.target, { tool: true }),
            { cls: "small wide", disabled: !(g.stock.tools > 0), title: `A tool from the stockpile adds +${g.toolBoost}` })),
        hint(`You have ${g.stock.tools || 0}${icon("tools")} · Shift+click the building: with a tool · Esc: cancel`)];
    }

    function structurePanel(uid, s) {
      const g = game();
      const kind = g.kinds[s.kind];
      const target = `s${uid}`;
      const lines = [el("h3", {}, `${kind.icon} ${kind.name}`)];
      if (kind.work) {
        const key = Object.keys(kind.work.makes)[0];
        const uses = Object.keys(kind.work.uses || {}).length ? `uses ${amounts(kind.work.uses)}, ` : "";
        lines.push(el("div", {}, el("b", {}, `Output: +${s.output}${icon(key)}`), ` (${uses}${s.worked ? "worked this round" : "not worked yet"})`));
        if (s.parts) lines.push(partsList(s.parts));
        const link = {
          depot: "Next to a depot: goods reach the stockpile at once.",
          road: "Linked by road: goods wait in its store for a haul.",
          none: "Cut off: no road to the keep or a storage yard (it can't get inputs and can't be hauled from).",
        }[s.link];
        if (link) lines.push(el("div", {}, link));
        const holder = g.placements[target];
        lines.push(el("div", {}, holder ? `👤 ${holder === you() ? "Your" : `${nameOf(holder)}'s`} unit is here this round.`
          : s.worked ? "Worked this round." : "No unit here this round."));
        const place = placeOf(target);
        if (place) {
          lines.push(el("div", { className: "preview" }, `${g.phase === "place" ? "A unit here would make " : "Your unit makes "}${place.text}`,
            place.tool ? el("span", { className: "muted" }, ` · with a tool: ${place.tool}`) : ""));
          if (place.why) lines.push(el("div", { className: "minus" }, place.why));
        }
      }
      if (kind.population) lines.push(el("div", {}, `🏠 Home to ${kind.population} people.`));
      if (kind.income && Object.keys(kind.income).length) lines.push(el("div", {}, `Each round: +${amounts(kind.income)}`));
      if (Object.keys(s.store).length) lines.push(el("div", {}, `Stored: ${amounts(s.store)} (max ${g.storeCap}): a haul brings it in.`));
      if (s.plague) lines.push(el("div", { className: "minus" }, "🦠 Plagued: no unit can work it until cured."));
      if (s.frozen) lines.push(el("div", {}, "❄️ Frozen this round: no unit can work it."));
      if (s.ruined.length) lines.push(el("div", { className: "minus" }, `🔥 ${s.ruined.length} ruined tile(s): repair it before it can work.`));
      if (s.kind !== "keep") lines.push(el("div", { className: "muted" }, `Safe from raids: ${s.protected}/${s.cells.length} tiles`));
      if (kind.text) lines.push(el("div", { className: "muted" }, kind.text));
      return lines;
    }

    function inspector(uid, modes) {
      ({ tool, selection, pick, hover } = modes);
      const g = game();
      const box = $("inspector");
      if (tool) {
        let head;
        if (tool === "remove") {
          head = [el("h3", {}, "✖ Remove a road or wall"), el("div", {}, "Click an outlined tile to remove it. Free, nothing is refunded.")];
        } else {
          const kind = g.kinds[tool];
          const stock = tileStock(tool);
          head = [el("h3", {}, `${kind.icon} ${kind.name}`),
            el("div", {}, stock > 0 ? `${plural(stock, "tile")} in stock.`
              : `None in stock: the next one buys ${g.tileBatch} for ${amounts(kind.cost)}.`),
            ...kindInfo({ ...kind, cost: {} })];
        }
        box.replaceChildren(...head, hint("Keep clicking to do more · right-click or Esc: stop"));
        return;
      }
      if (selection && isBuild(selection.card)) {
        const kind = g.kinds[cardOf(selection.card).structure];
        box.replaceChildren(el("h3", {}, `${kind.icon} ${kind.name}`), ...kindInfo(kind),
          hint("R or mouse wheel: turn · right-click or Esc: cancel"));
        return;
      }
      if (pick) {
        box.replaceChildren(...pickPanel());
        return;
      }
      const s = uid ? g.structures[uid] : null;
      if (s) {
        box.replaceChildren(...structurePanel(uid, s));
        return;
      }
      const key = hover ? `${hover[0]},${hover[1]}` : null;
      const b = key ? g.blights[key] : null;
      if (b) {
        const foe = g.foes[String(b.foe)];
        const cost = b.lair && foe && foe.defeat ? foe.defeat.raze || 1 : 1;
        const holder = g.placements[`raze${key}`];
        box.replaceChildren(el("h3", {}, `${b.icon} ${b.name}`),
          el("div", {}, `Placed by the ${foe && foe.name ? foe.name : "enemy"}. Buildings next to it make 1 less.`),
          el("div", {}, `${b.lair ? "Its lair: razing every tile beats it. " : ""}Razing takes ${cost} strike${cost > 1 ? "s" : ""}`
            + ` (${b.strikes || 0} so far): a unit placed here is 1 strike, or spend soldiers (click it on your turn).`),
          el("div", {}, holder ? `👤 ${holder === you() ? "Your" : `${nameOf(holder)}'s`} unit is here this round.` : "No unit here this round."));
        return;
      }
      const tips = {
        place: "Click an outlined building, Hauling or an enemy's Fighting pool to place a unit; click one of yours to take it back. Hover a building to see what it would make.",
        act: myTurn() ? "Click one of your outlined units to make it act. Hover a building to see what it makes and why."
          : "Hover a building to see what it makes and why.",
      };
      box.replaceChildren(el("h3", {}, "Inspector"), el("div", { className: "muted" }, tips[g.phase] || tips.act));
    }

    return { status, roundBar, foes, market, log, inspector, cardEl, kindInfo, partsList };
  }

  return { create };
})();
