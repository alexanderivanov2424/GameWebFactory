/*
 * Marooned: the prompt box above the board: whatever the game is waiting on you (or others) for.
 *
 *   MaroonedPrompts.render(element, state, send)
 *       Objectives to keep, your secret gather roll, the 2 tiles you drew, build-check steps
 *       (pick a helper, discard 1 of 3, reveal 1 of 2), and the night vote. When the game waits
 *       on someone else, it says who. Hides the element when there's nothing to show.
 *       send(message) sends a game message.
 */
(() => {
  const { el, listNames } = AppDom;
  const icon = (item) => MaroonedBoard.ITEM_ICONS[item] || "";

  // Kept objective ids while picking, per game (not sent until "Keep these").
  let picking = { game: null, ids: new Set() };

  function render(element, state, send) {
    const game = state.game;
    const priv = state.private || {};
    const me = state.you;
    const name = (pid) => game.names[pid] || "?";
    const parts = [];
    const inGame = game.order.includes(me);

    if (game.stage === "objectives") {
      parts.push(...objectives(state, send, name));
    } else if (game.stage === "vote") {
      parts.push(...vote(state, send, name, inGame));
    } else if (game.stage === "day") {
      if (priv.roll) parts.push(...roll(priv.roll, game, send));
      else if (priv.tileChoices) parts.push(...tileChoices(priv.tileChoices, game, send));
      else if (game.check) parts.push(...check(state, send, name));
      else if (game.pending) {
        const what = game.pending.kind === "gather" ? "is rolling to gather…" : "is choosing a tile…";
        parts.push(el("p", {}, `${name(game.pending.player)} ${what}`));
      }
    }
    element.hidden = parts.length === 0;
    element.replaceChildren(...parts);
  }

  function objectives(state, send, name) {
    const game = state.game;
    const priv = state.private || {};
    const waiting = game.order.filter((pid) => !(game.picked || {})[pid]).map(name);
    if (!priv.dealt) return [el("p", {}, `Players are picking their secret objectives… (${listNames(waiting)})`)];
    if (priv.kept) {
      return [el("h2", {}, "Objectives kept"), el("p", { className: "muted" }, `Waiting for ${listNames(waiting)}.`)];
    }
    if (picking.game !== state.gameNumber) picking = { game: state.gameNumber, ids: new Set() };
    const keep = game.rules.keep;
    const cards = priv.dealt.map((o) => {
      const chosen = picking.ids.has(o.id);
      const card = el("button", { className: `pick-card${chosen ? " chosen" : ""}` },
        el("b", {}, `${o.title} (+${o.points})`), el("span", {}, o.text));
      card.addEventListener("click", () => {
        if (chosen) picking.ids.delete(o.id);
        else if (picking.ids.size < keep) picking.ids.add(o.id);
        render(document.getElementById("prompt"), state, send);
      });
      return card;
    });
    const button = el("button", { className: "green", disabled: picking.ids.size !== keep }, "Keep these");
    button.addEventListener("click", () => send({ action: "keep", objectives: [...picking.ids] }));
    const role = priv.role === "imposter"
      ? "You are the IMPOSTER. Keep the others from escaping, without getting caught."
      : "You are a castaway. Get off this island, and watch out for the Imposter.";
    return [
      el("p", { className: `role-line ${priv.role}` }, role),
      el("h2", {}, `Keep ${keep} secret objective${keep > 1 ? "s" : ""}`),
      el("div", { className: "pick-row" }, ...cards),
      button,
    ];
  }

  function roll(roll, game, send) {
    const yields = game.rules.gatherYield;
    const buttons = [];
    for (let face = roll.face; face >= 1; face--) {
      const amount = yields[String(face)];
      const label = amount ? `Announce ${face}: gather ${icon(roll.item)} ${roll.item}` : `Announce ${face}: nothing`;
      const button = el("button", { className: face === roll.face ? "green" : "plain" }, label);
      button.addEventListener("click", () => send({ action: "report", face }));
      buttons.push(button);
    }
    return [
      el("h2", {}, `🎲 You rolled a ${roll.face} gathering ${roll.item}`),
      el("p", { className: "muted small" },
        "Only you saw the die. You may announce a worse roll (you get what you announce), never a better one. " +
        "1 = nothing, 2–3 = 1, 4–5 = 2, 6 = 3, +1 on a success with the right tool."),
      el("div", { className: "row" }, ...buttons),
    ];
  }

  function tileCard(kind, extra) {
    const res = Object.entries(kind.resources || {})
      .map(([item, n]) => `${icon(item)} ${n < 0 ? "∞" : n}`).join("  ");
    return el("button", { className: "pick-card tile-card" },
      el("span", { className: "big-icon" }, kind.icon || ""),
      el("b", {}, kind.name),
      el("span", { className: "small" }, `Move ${kind.moveCost}${res ? " · " + res : ""}`),
      el("span", { className: "small muted" }, kind.text),
      extra || "");
  }

  function tileChoices(cards, game, send) {
    const choices = cards.map((card) => {
      const button = tileCard(game.tileTypes[card.card]);
      button.style.borderColor = game.tileTypes[card.card].color;
      button.addEventListener("click", () => send({ action: "place", uid: card.uid }));
      return button;
    });
    return [
      el("h2", {}, "🔍 Place one of the tiles you drew"),
      el("p", { className: "muted small" }, "Nobody else sees the other one: it goes face down under the deck."),
      el("div", { className: "pick-row" }, ...choices),
    ];
  }

  function checkCard(game, card, send, action, label) {
    const info = game.checkDeck.cards[card.card] || { name: card.card, text: "" };
    const button = el("button", { className: `pick-card check-${card.card}` },
      el("b", {}, info.name), el("span", { className: "small" }, info.text), el("span", { className: "small muted" }, label));
    button.addEventListener("click", () => send({ action, uid: card.uid }));
    return button;
  }

  function check(state, send, name) {
    const game = state.game;
    const priv = state.private || {};
    const me = state.you;
    const c = game.check;
    const stage = game.projects[c.project];
    const stageName = stage.stages[stage.built] ? stage.stages[stage.built].name : stage.name;
    if (c.step === "helper") {
      if (c.builder !== me) return [el("p", {}, `${name(c.builder)} is picking a helper to check the ${stageName}…`)];
      const buttons = game.order.filter((pid) => pid !== me).map((pid) => {
        const button = el("button", {}, name(pid));
        button.addEventListener("click", () => send({ action: "helper", player: pid }));
        return button;
      });
      return [
        el("h2", {}, `🔨 The ${stageName} is ready: pick a helper for the build check`),
        el("p", { className: "muted small" },
          "You'll draw 3 check cards, discard 1 in secret and hand the other 2 to your helper, who reveals 1."),
        el("div", { className: "row" }, ...buttons),
      ];
    }
    if (c.step === "discard" && c.builder === me && priv.checkHand) {
      return [
        el("h2", {}, `🔨 Build check (${stageName}): discard one card`),
        el("p", { className: "muted small" }, `The other two go to ${name(c.helper)}, who reveals one. Nobody sees the discard.`),
        el("div", { className: "pick-row" }, ...priv.checkHand.map((card) => checkCard(game, card, send, "discard", "Discard"))),
      ];
    }
    if (c.step === "reveal" && c.helper === me && priv.checkHand) {
      return [
        el("h2", {}, `🔨 Build check (${stageName}): reveal one card`),
        el("p", { className: "muted small" }, `${name(c.builder)} handed you these two. The other is discarded unseen.`),
        el("div", { className: "pick-row" }, ...priv.checkHand.map((card) => checkCard(game, card, send, "reveal", "Reveal"))),
      ];
    }
    const who = c.step === "reveal" ? name(c.helper) : name(c.builder);
    return [el("p", {}, `Build check on the ${stageName}: ${name(c.builder)} and ${name(c.helper)}. Waiting for ${who}…`)];
  }

  function vote(state, send, name, inGame) {
    const game = state.game;
    const priv = state.private || {};
    const waiting = game.order.filter((pid) => !(game.voted || {})[pid]).map(name);
    const head = el("h2", {}, `🌙 Night ${game.day}: who do you suspect?`);
    const note = el("p", { className: "muted small" },
      "Talk it over in the chat. Ballots are secret; only the tally is shown, and it changes nothing by itself.");
    if (!inGame) return [head, el("p", { className: "muted" }, `Waiting for ${listNames(waiting)}.`)];
    if (priv.ballot) {
      const choice = priv.ballot === "nobody" ? "nobody" : name(priv.ballot);
      return [head, el("p", {}, `You voted for ${choice}. Waiting for ${listNames(waiting)}.`)];
    }
    const buttons = game.order.filter((pid) => pid !== state.you).map((pid) => {
      const button = el("button", {}, name(pid));
      button.addEventListener("click", () => send({ action: "vote", player: pid }));
      return button;
    });
    const nobody = el("button", { className: "plain" }, "Nobody");
    nobody.addEventListener("click", () => send({ action: "vote", player: "nobody" }));
    return [head, note, el("div", { className: "row" }, ...buttons, nobody)];
  }

  window.MaroonedPrompts = { render };
})();
