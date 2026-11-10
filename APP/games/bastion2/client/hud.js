/*
 * Bastion 2: Bastion2Hud, the panels around the map. game.js owns the state and what the player is
 * doing and passes a context; this file only draws.
 *
 *   const hud = Bastion2Hud.create(ctx)
 *     ctx: { game(), priv(), you(), seat(), send(message), nameOf(pid), selection(),
 *            startBundle(cell), hoverCell(key or null), showDeck(pid) }
 *   hud.cardEl(id, {off, temp, selected, picked, kept, why})   a card face (hand, play area, deck
 *                          window); resource cards show only their icon, once per point of value
 *   hud.amounts(obj)       "2🪵 1🧑"
 *   hud.uses()             left: your structures' actions (once a turn each; Bundle starts a pick)
 *   hud.market()           right: always-for-sale cards and the shop row, with Buy buttons
 *   hud.seats()            right: every player (colour, name, turn / done / setup, resources, a
 *                          Deck button)
 *   hud.log()              right: the chronicle, newest first
 *   hud.playArea()         bottom: played cards and pending builds as card faces (optional cards
 *                          as checkboxes, Take back), and the counters top right: permanent
 *                          resources (food n / storage, population free / total), a separator,
 *                          then this turn's temporary resources
 *   hud.actionsCircle()    bottom left: actions left this turn
 *   hud.deckWindow(pid)    fill the deck window: every card that player owns (+ your discard pile)
 */
const Bastion2Hud = (() => {
  const { $, el } = AppDom;
  const KIND_NAMES = { resource: "Resource", upkeep: "Upkeep", action: "Action", structure: "Structure" };

  function create(ctx) {
    const { game, priv, you, seat } = ctx;
    const icon = (key) => game().icons[key] || "";
    const amounts = (obj) => Object.entries(obj || {}).filter(([, n]) => n).map(([k, n]) => `${n}${icon(k)}`).join(" ");
    const cardName = (id) => (game().cards[id] || {}).name || id;

    function cardEl(id, { off = false, temp = false, selected = false, picked = false, kept = false, why = "" } = {}) {
      const card = game().cards[id];
      const cls = ["pcard", card.kind, off && "off", temp && "temp", selected && "sel", picked && "picked", kept && "kept"];
      const node = el("div", { className: cls.filter(Boolean).join(" "), title: why || `${card.name}: ${card.text}` });
      if (card.kind === "resource") {
        const many = card.value > 1 ? (card.value > 3 ? " many" : " some") : "";
        node.append(el("div", { className: `icons${many}` },
          Array.from({ length: card.value }, () => el("span", { textContent: card.icon || icon(card.resource) }))));
        return node;
      }
      node.append(el("div", { className: "name", textContent: card.name }));
      node.append(el("div", { className: "kind", textContent: `${KIND_NAMES[card.kind] || card.kind}${temp ? " · temporary" : ""}` }));
      node.append(el("div", { className: "icon", textContent: card.icon || "" }));
      if (card.kind === "structure" && card.cost) node.append(el("div", { className: "cost", textContent: `Build: ${amounts(card.cost) || "free"}` }));
      if (card.kind === "action" && card.actions) node.append(el("div", { className: "cost", textContent: `${card.actions}${icon("actions")}` }));
      node.append(el("div", { className: "text", textContent: card.text }));
      return node;
    }

    function uses() {
      const p = priv();
      const g = game();
      const list = Object.entries((p && p.uses) || {});
      if (!list.length) {
        $("uses").replaceChildren(el("span", { className: "muted small", textContent: "Structures with actions show up here once built (Quarry, Lumber Mill, Storage Yard…)." }));
        return;
      }
      const sel = ctx.selection();
      $("uses").replaceChildren(...list.map(([key, info]) => {
        const s = g.structures[key];
        const card = g.cards[s.kind];
        const action = card.action;
        const used = info.why === "Already used this turn.";
        const button = el("button", {
          className: `use plain${used ? " used" : ""}${sel && sel.mode === "bundle" && sel.cell === key ? " on" : ""}`,
          disabled: Boolean(info.why), title: info.why || action.text,
        },
        el("div", { className: "head" }, el("span", { textContent: `${card.icon} ${action.name}` }),
          el("span", { textContent: action.actions ? `${action.actions}${icon("actions")}` : "Free" })),
        el("div", { className: "sub", textContent: used ? `${card.name}: used this turn` : `${card.name}: ${action.text}` }));
        button.addEventListener("click", () => {
          if (action.bundle && action.bundle.length) ctx.startBundle(key);
          else ctx.send({ action: "use", x: Number(key.split(",")[0]), y: Number(key.split(",")[1]) });
        });
        button.addEventListener("mouseenter", () => ctx.hoverCell(key));
        button.addEventListener("mouseleave", () => ctx.hoverCell(null));
        return button;
      }));
    }

    function offer(id, why, onBuy) {
      const card = game().cards[id];
      const button = el("button", { textContent: "Buy", disabled: Boolean(why), title: why || `Costs ${game().buyActions} action` });
      button.addEventListener("click", onBuy);
      const node = el("div", { className: "offer", title: card.text },
        el("span", { className: "ico", textContent: card.icon }),
        el("div", { className: "body" }, el("b", { textContent: card.name }),
          el("span", { textContent: card.kind === "structure" ? `Build: ${amounts(card.cost) || "free"}` : KIND_NAMES[card.kind] })),
        priv() ? button : "");
      return node;
    }

    function market() {
      const g = game();
      const why = priv() ? priv().buy : "";
      const always = g.market.always.map((id) => offer(id, why, () => ctx.send({ action: "buy", card: id })));
      const shop = g.market.slots.map((id, slot) => (id
        ? offer(id, why, () => ctx.send({ action: "buy", slot }))
        : el("div", { className: "offer empty", textContent: "Sold out" })));
      $("market").replaceChildren(
        el("div", { className: "muted small", textContent: "Always for sale" }),
        el("div", { className: "offers" }, always),
        el("div", { className: "muted small", style: "margin-top: 8px", textContent: `Shop (${g.market.left} more in the shop deck)` }),
        el("div", { className: "offers" }, shop),
      );
    }

    function seats() {
      const g = game();
      $("seats").replaceChildren(...g.order.map((pid) => {
        const s = g.seats[pid];
        let flag = "";
        if (g.stage === "setup") flag = s.setup >= g.setupPieces.length ? "placed" : `placing ${s.setup}/${g.setupPieces.length}`;
        else if (g.mode === "order") flag = g.current === pid ? "their turn" : "";
        else flag = s.done ? "done" : "playing";
        const now = g.stage === "play" && (g.mode === "order" ? g.current === pid : !s.done);
        const dot = el("span", { className: "dot" });
        dot.style.background = s.color;
        const deck = el("button", { className: "plain small deck", textContent: "Deck", title: `See ${pid === you() ? "your" : `${s.name}'s`} deck` });
        deck.addEventListener("click", () => ctx.showDeck(pid));
        return el("div", { className: `seat${now ? " now" : ""}` },
          el("div", { className: "who" }, dot, el("span", { textContent: `${s.name}${pid === you() ? " (you)" : ""}` }),
            el("span", { className: "flag", textContent: flag }), deck),
          el("div", { textContent: `${icon("food")} ${s.food}/${s.foodCap} · ${icon("population")} ${Math.max(0, s.population - s.popUsed)}/${s.population} · ${icon("actions")} ${s.actions}` }),
          el("div", { className: "muted", textContent: `Hand ${s.hand} · draw ${s.draw} · discard ${s.discard} · ${s.deck} cards${amounts(s.temp) ? ` · now ${amounts(s.temp)}` : ""}` }));
      }));
    }

    function log() {
      const g = game();
      const lines = [];
      for (let i = g.logCount - 1; i >= 0; i--) {
        const entry = g.log[String(i)];
        if (!entry) break;
        const p = el("p", { textContent: entry.text });
        if (entry.pid && g.colors[entry.pid]) p.style.borderLeft = `3px solid ${g.colors[entry.pid]}`;
        if (entry.pid) p.style.paddingLeft = "5px";
        lines.push(p);
      }
      $("log").replaceChildren(...lines);
    }

    function playArea() {
      const g = game();
      const s = seat();
      const p = priv();
      const cards = [];
      if (s) {
        for (const id of s.play) cards.push(cardEl(id));
        for (const [key, plan] of Object.entries((p && p.pending) || {})) {
          const card = g.cards[plan.card];
          const node = cardEl(plan.card);
          node.classList.add("building");
          node.title = "Built at the end of your turn.";
          node.append(el("span", { className: "badge", textContent: "Building" }));
          const [x, y] = key.split(",").map(Number);
          const opts = el("div", { className: "opts" });
          (card.adds || []).forEach((add, index) => {
            if (!add.optional) return;
            const box = el("input", { type: "checkbox", checked: !plan.skip.includes(index), disabled: Boolean(p.turn) });
            box.addEventListener("change", () => ctx.send({ action: "choose", x, y, index, on: box.checked }));
            opts.append(el("label", { title: "Add this card to your discard pile when it's built" }, box, `+${cardName(add.card)}`));
          });
          if (!p.turn) {
            const back = el("button", { className: "plain small", textContent: "↶ Take back", title: "Refund it and return the card to your hand" });
            back.addEventListener("click", () => ctx.send({ action: "unbuild", x, y }));
            opts.append(back);
          }
          node.append(opts);
          node.addEventListener("mouseenter", () => ctx.hoverCell(key));
          node.addEventListener("mouseleave", () => ctx.hoverCell(null));
          cards.push(node);
        }
      }
      if (!cards.length) cards.push(el("span", { className: "muted small", textContent: "Play area: cards you play land here." }));
      $("played").replaceChildren(...cards);
      const counter = (key, value, title, dim) => el("div", { className: `counter${dim ? " zero" : ""}`, title },
        el("b", { textContent: `${icon(key)} ${value}` }));
      const perm = s ? [
        counter("food", `${s.food}/${s.foodCap}`, "Food (kept between turns, up to your food storage)", !s.food),
        counter("population", `${Math.max(0, s.population - s.popUsed)}/${s.population}`, "Population free this turn / total", s.popUsed >= s.population),
      ] : [];
      const temp = g.temporary.map((r) => {
        const n = (s && s.temp[r]) || 0;
        return counter(r, n, `${g.resources[r].name} this turn (cleared when your turn ends)`, !n);
      });
      $("counters").replaceChildren(
        el("div", { className: "row perm" }, perm),
        el("div", { className: "sep" }),
        el("div", { className: "row" }, temp),
      );
    }

    function actionsCircle() {
      const s = seat();
      const n = s ? s.actions : 0;
      $("actions-circle").className = n ? "" : "zero";
      $("actions-circle").replaceChildren(el("div", {}, el("b", { textContent: String(n) }), el("span", { textContent: n === 1 ? "action" : "actions" })));
    }

    function deckWindow(pid) {
      const g = game();
      const s = g.seats[pid];
      if (!s) return;
      const mine = pid === you() && priv();
      $("deck-title").textContent = mine ? "Your deck" : `${s.name}'s deck`;
      $("deck-note").textContent = `${s.deck} cards · ${s.hand} in hand · ${s.draw} to draw · ${s.discard} discarded`;
      const faces = (counts) => Object.entries(counts).sort().map(([id, n]) => {
        const node = el("div", { className: "deckcard" }, cardEl(id));
        if (n > 1) node.append(el("span", { className: "count", textContent: `×${n}` }));
        return node;
      });
      $("deck-cards").replaceChildren(...faces(s.deckList));
      $("discard-section").hidden = !mine;
      if (!mine) return;
      const discards = {};
      for (const id of priv().discardPile) discards[id] = (discards[id] || 0) + 1;
      $("discard-cards").replaceChildren(...(priv().discardPile.length ? faces(discards) : [el("span", { className: "muted", textContent: "Empty." })]));
    }

    return { cardEl, amounts, uses, market, seats, log, playArea, actionsCircle, deckWindow };
  }

  return { create };
})();
