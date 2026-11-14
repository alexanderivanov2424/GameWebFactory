/*
 * Bastion: BastionPanels, the panels around the board. game.js owns the state and what the
 * player is doing and passes a context; this file draws:
 *
 *   const panels = BastionPanels.create(ctx)
 *     ctx: { state(), game(), priv(), you(), icon(key), amounts(obj), nameOf(pid), send(message),
 *            playing(), selection(), setTrade(trade), showDeck(pid) }
 *   panels.status()          round, the phase chips (Setup / Place / Resolve / Plan) and what to do now
 *   panels.details(x, y)     the right-hand top panel: the hovered tile (terrain, structure, owner,
 *                            build tokens, what it does, the unit on it, what a unit of yours
 *                            would do there now); null: a hint
 *   panels.prompt()          the panel below it: your resolution prompt ("Spend X to make Y?"
 *                            with one button per answer), the Trade form while a Trade card is
 *                            selected, or what the selected card needs; hidden otherwise
 *   panels.seats()           the player list: colour, name, done / prompts left, resource bar,
 *                            units / soldiers (free / all), decrees, and a Deck button each
 *   panels.market()          the two market halves (blueprints, actions): Buy and Reshuffle
 *   panels.log()             the chronicle, newest first
 *   panels.cardEl(id, {off, selected})   a card face (hand, market, deck window)
 *   panels.deckWindow(pid)   fill the deck window with that player's cards
 */
const BastionPanels = (() => {
  const { $, el } = AppDom;
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const PHASES = [["setup", "Setup"], ["place", "Place"], ["resolve", "Resolve"], ["plan", "Plan"]];
  const TERRAIN = { ".": "Grass", F: "Forest", M: "Mountain", "~": "Water" };

  function create(ctx) {
    const { game, priv, you, icon, amounts, nameOf } = ctx;

    // --- cards ------------------------------------------------------------------------------

    function cardEl(cardId, { off = false, selected = false } = {}) {
      const card = game().cards[cardId];
      const kind = card.kind === "build" ? game().kinds[card.structure] : null;
      const node = el("div", { className: `pcard ${card.kind}${off ? " off" : ""}${selected ? " sel" : ""}` });
      node.append(el("div", { className: "name", textContent: card.name }));
      node.append(el("div", { className: "kind", textContent: { build: "Blueprint", action: "Action", curse: "Curse" }[card.kind] }));
      if (kind) node.append(el("span", { className: "icon", textContent: kind.icon || "" }));
      const cost = card.kind === "curse" ? card.pay : card.cost;
      if (cost && Object.keys(cost).length) node.append(el("div", { className: "cost", textContent: `Cost: ${amounts(cost)}` }));
      node.append(el("div", { className: "text", textContent: card.text }));
      return node;
    }

    function deckWindow(pid) {
      const seat = game().seats[pid];
      if (!seat) return;
      $("deck-title").textContent = pid === you() ? "Your deck" : `${seat.name}'s deck`;
      const counts = {};
      for (const id of seat.deck) counts[id] = (counts[id] || 0) + 1;
      $("deck-note").textContent = `${plural(seat.deck.length, "card")} · ${seat.hand} in hand · ${seat.draw} to draw · ${seat.discard} discarded`;
      $("deck-cards").replaceChildren(...Object.entries(counts).map(([id, n]) => {
        const node = cardEl(id);
        if (n > 1) node.querySelector(".name").textContent += ` ×${n}`;
        return node;
      }));
    }

    // --- status -------------------------------------------------------------------------------

    function todo() {
      const g = game();
      const s = ctx.state();
      if (s.phase === "finished") return "The game is over.";
      const seat = g.seats[you()];
      if (g.phase === "setup") {
        if (!g.setup) return "";
        const what = g.kinds[g.setup.kind].name;
        return g.setup.pid === you() ? `Click an outlined tile to place your ${what}.` : `${nameOf(g.setup.pid)} is placing their ${what}.`;
      }
      if (!seat) return "You're watching.";
      if (g.phase === "place") {
        if (seat.ready) return "Done: waiting for the others (click Not done to change your placements).";
        return `Click outlined tiles to place units (${seat.free} free${seat.soldiers ? `, ${seat.freeSoldiers} soldiers` : ""}); right-click takes one back. Then Done.`;
      }
      if (g.phase === "resolve") {
        return seat.prompts ? "Answer your prompts on the right." : "Waiting for the others to answer their prompts.";
      }
      if (seat.ready) return "Done: waiting for the others (click Not done to keep planning).";
      return "Play cards (decrees 📜 + resources), buy from the market below the board, then Done.";
    }

    function status() {
      const g = game();
      const chips = PHASES.filter(([id]) => id !== "setup" || g.phase === "setup")
        .map(([id, label]) => el("span", { className: `phase${g.phase === id ? " now" : ""}`, textContent: label }));
      $("status").replaceChildren(
        el("span", { className: "round", textContent: g.round ? `Round ${g.round}` : "Setup" }),
        ...chips,
        el("span", { className: "todo", textContent: todo() }),
      );
    }

    // --- details (hovered tile) ------------------------------------------------------------------

    function details(x, y) {
      const box = $("details");
      const g = game();
      if (x === null || x === undefined) {
        box.replaceChildren(el("h3", {}, "Details"), el("div", { className: "muted" }, "Hover a tile to see what's there."));
        return;
      }
      const key = `${x},${y}`;
      const parts = [];
      const s = Object.values(g.structures).find((t) => t.x === x && t.y === y);
      const unit = (g.units || {})[key];
      const place = ((priv() || {}).places || {})[key];
      if (s) {
        const info = g.kinds[s.kind];
        parts.push(el("h3", {}, `${info.icon} ${info.name}`));
        const owner = el("div", {}, el("span", { className: "dot", style: `background:${g.colors[s.owner] || "#888"}` }), ` ${nameOf(s.owner)}`);
        parts.push(owner);
        if (s.tokens) parts.push(el("div", { className: "warn" }, `Planned: ${plural(s.tokens, "build token")} left (each unit placed here removes one).`));
        parts.push(el("div", {}, info.text));
        if (info.requires.length) parts.push(el("div", { className: "muted" }, `Must be ${info.requires.join(", ")}.`));
      } else {
        const road = g.roads[key];
        parts.push(el("h3", {}, road !== undefined ? `${g.kinds.road.icon} Road` : TERRAIN[g.terrain[y][x]] || "Grass"));
        if (road !== undefined) parts.push(el("div", {}, `${nameOf(road)}'s road. ${g.kinds.road.text}`));
        else if (g.terrain[y][x] === "F") parts.push(el("div", {}, "A unit here gathers 1 wood."));
        else if (g.terrain[y][x] === "M") parts.push(el("div", {}, "A unit here gathers 1 stone."));
        else if (g.terrain[y][x] === ".") parts.push(el("div", {}, "A unit here builds a road or scavenges (1/3 nothing, 1/3 wood, 1/3 stone)."));
      }
      if (unit) {
        const kind = unit.soldier ? "soldier" : "unit";
        const how = unit.new ? "placed this round" : "stationed here";
        parts.push(el("div", { className: "unit-line" }, `${unit.soldier ? "⚔️" : "🧍"} ${nameOf(unit.pid)}'s ${kind} (${how})`));
      }
      if (place) parts.push(el("div", { className: "preview" }, `Your ${place.soldier ? "soldier" : "unit"} here: ${place.text}`));
      parts.push(el("div", { className: "muted small" }, `Tile ${x}, ${y}`));
      box.replaceChildren(...parts);
    }

    // --- prompt / card panel -----------------------------------------------------------------------

    function tradeForm(sel) {
      const g = game();
      const others = Object.keys(g.seats).filter((pid) => pid !== you());
      const nodes = [el("h3", {}, "🤝 Trade"), el("div", {}, "Give another player 3 different resources (1 each) or 2 of the same resource.")];
      if (!others.length) {
        nodes.push(el("div", { className: "warn" }, "Nobody else to trade with."));
        return nodes;
      }
      if (!sel.to || !g.seats[sel.to]) sel.to = others[0];
      nodes.push(el("div", { className: "choices row" }, ...others.map((pid) => {
        const b = el("button", { className: `small${sel.to === pid ? " green" : " plain"}`, textContent: nameOf(pid) });
        b.addEventListener("click", () => ctx.setTrade({ ...sel, to: pid }));
        return b;
      })));
      const mine = g.seats[you()].stock;
      const grid = el("div", { className: "gift" });
      for (const r of g.resources) {
        const n = sel.give[r] || 0;
        const minus = el("button", { className: "small plain", textContent: "−", disabled: n <= 0 });
        const plus = el("button", { className: "small plain", textContent: "+", disabled: n >= Math.min(2, mine[r] || 0) });
        minus.addEventListener("click", () => ctx.setTrade({ ...sel, give: { ...sel.give, [r]: n - 1 } }));
        plus.addEventListener("click", () => ctx.setTrade({ ...sel, give: { ...sel.give, [r]: n + 1 } }));
        grid.append(el("div", { className: "gift-row" }, el("span", {}, `${icon(r)} ${r} (${mine[r] || 0})`), minus, el("b", {}, String(n)), plus));
      }
      nodes.push(grid);
      const counts = Object.values(sel.give).filter((n) => n > 0).sort();
      const valid = counts.join(",") === "1,1,1" || counts.join(",") === "2";
      const give = el("button", { className: "green", textContent: valid ? `Give ${amounts(sel.give)} to ${nameOf(sel.to)}` : "Give", disabled: !valid });
      give.addEventListener("click", () => {
        const gift = Object.fromEntries(Object.entries(sel.give).filter(([, n]) => n > 0));
        ctx.send({ action: "play", uid: sel.uid, to: sel.to, give: gift });
        ctx.setTrade(null);
      });
      const cancel = el("button", { className: "plain small", textContent: "Cancel" });
      cancel.addEventListener("click", () => ctx.setTrade(null));
      nodes.push(el("div", { className: "row" }, give, cancel));
      return nodes;
    }

    function prompt() {
      const box = $("prompt");
      const g = game();
      const p = priv();
      const sel = ctx.selection();
      let nodes = null;
      if (p && p.prompt && g.phase === "resolve") {
        const q = p.prompt;
        nodes = [el("h3", {}, `❓ ${q.title}`)];
        if (q.left > 1) nodes.push(el("div", { className: "muted" }, `${q.left - 1} more after this one.`));
        nodes.push(el("div", { className: "choices" }, ...q.options.map((o) => {
          const b = el("button", { className: `wide${o.ok ? " green" : " plain"}`, textContent: o.label, disabled: !o.ok, title: o.why || "" });
          b.addEventListener("click", () => ctx.send({ action: "answer", option: o.id }));
          return b;
        })));
        const why = q.options.filter((o) => !o.ok).map((o) => o.why).join(" · ");
        if (why) nodes.push(el("div", { className: "warn" }, why));
      } else if (sel && sel.trade) {
        nodes = tradeForm(sel);
      } else if (sel) {
        const card = g.cards[sel.card];
        nodes = [el("h3", {}, card.name), el("div", {}, card.kind === "build"
          ? "Click an outlined tile to plan it there (right-click or Esc cancels)."
          : "Click one of your outlined buildings (right-click or Esc cancels).")];
      } else if (g.phase === "resolve" && g.seats[you()]) {
        nodes = [el("h3", {}, "Resolution"), el("div", { className: "muted" }, "Your prompts are answered: waiting for the others.")];
      }
      box.hidden = !nodes;
      if (nodes) box.replaceChildren(...nodes);
    }

    // --- players --------------------------------------------------------------------------------

    function seats() {
      const g = game();
      $("seats").replaceChildren(el("h3", {}, "Players"), ...Object.entries(g.seats).map(([pid, seat]) => {
        let flag = "";
        if (g.phase === "setup") flag = g.setup && g.setup.pid === pid ? "placing…" : "";
        else if (g.phase === "resolve") flag = seat.prompts ? `${plural(seat.prompts, "prompt")} left` : "✓ answered";
        else flag = seat.ready ? "✓ done" : "";
        const deck = el("button", { className: "plain small", textContent: `Deck (${seat.deck.length})` });
        deck.addEventListener("click", () => ctx.showDeck(pid));
        const bar = el("div", { className: "resbar" }, ...g.resources.map((r) => el("span", {
          className: `res${seat.stock[r] ? "" : " zero"}`, title: r, textContent: `${icon(r)}${seat.stock[r] || 0}`,
        })));
        const people = el("div", { className: "resbar" },
          el("span", { className: "res", title: "Units: free / all (each eats 1 food a round)", textContent: `${icon("units")}${seat.free}/${seat.units}` }),
          el("span", { className: `res${seat.soldiers ? "" : " zero"}`, title: "Soldiers: free / all (each eats 1 food a round)", textContent: `${icon("soldiers")}${seat.freeSoldiers}/${seat.soldiers}` }),
          el("span", { className: `res${seat.decrees ? "" : " zero"}`, title: "Royal decrees left this planning phase", textContent: `${icon("decrees")}${seat.decrees}` }),
          el("span", { className: "res muted", title: "Cards in hand", textContent: `🂠${seat.hand}` }),
        );
        return el("div", { className: `seat${pid === you() ? " you" : ""}` },
          el("div", { className: "seat-head" },
            el("span", { className: "dot", style: `background:${seat.color}` }),
            el("b", {}, seat.name + (pid === you() ? " (you)" : "")),
            el("span", { className: "flag", textContent: flag }),
            el("span", { className: "spacer" }), deck),
          bar, people);
      }));
    }

    // --- market ---------------------------------------------------------------------------------

    function market() {
      const g = game();
      const seat = g.seats[you()];
      const p = priv();
      const can = ctx.playing() && g.phase === "plan" && seat && !seat.ready;
      const halves = [["blueprints", "Blueprints"], ["actions", "Actions"]];
      $("market").replaceChildren(...halves.map(([half, label]) => {
        const used = Boolean(p && (p.reshuffled || []).includes(half));
        const gold = seat ? seat.stock.gold || 0 : 0;
        const reshuffle = el("button", {
          className: "small plain", textContent: used ? "Reshuffled" : `Reshuffle (${g.reshuffleCost}${icon("gold")})`,
          disabled: !can || used || gold < g.reshuffleCost,
          title: "Deal this half anew: once per round, for gold",
        });
        reshuffle.addEventListener("click", () => ctx.send({ action: "reshuffle", market: half }));
        const offers = (g.market[half] || []).map((id, slot) => {
          const card = g.cards[id];
          const node = cardEl(id, { off: !can || gold < card.price });
          const buy = el("button", { className: "small green buy", textContent: `Buy ${card.price}${icon("gold")}`, disabled: !can || gold < card.price });
          buy.addEventListener("click", () => ctx.send({ action: "buy", market: half, slot }));
          node.append(buy);
          return node;
        });
        return el("div", { className: "half" },
          el("div", { className: "half-head" }, el("h3", {}, label), reshuffle),
          el("div", { className: "offers" }, ...offers));
      }));
    }

    function log() {
      const g = game();
      $("log").replaceChildren(...[...g.log].reverse().map((entry) => el("p", {},
        el("span", { className: "r" }, entry.round ? `R${entry.round} ` : ""), entry.text)));
    }

    return { status, details, prompt, seats, market, log, cardEl, deckWindow };
  }

  return { create };
})();
