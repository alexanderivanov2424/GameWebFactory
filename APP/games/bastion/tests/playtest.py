"""DISABLED (2026-11-09): the bots were written for the worker-placement v4 rules and haven't been
updated for the per-player trading redesign (see REDESIGN_PROMPT.md). Running this prints a notice
and exits. Re-enable by rewriting tests/bots.py for the new Match API and removing the early exit.

Bastion: playtest runner (test-only, never deployed; not collected by the test runner). Plays whole
games with the bots in tests/bots.py through the Match API and prints aggregate balance stats.

    python3 -I APP/games/bastion/tests/playtest.py [--games N] [--players 1-4] [--map valley|highlands]
        [--difficulty easy|normal|hard] [--bot good|passive] [--seed S] [--keep 20] [--enemies 5]
        [--peace 5] [--gap 3] [--all] [--verbose] [--trace] [--jobs N]

--all runs the whole table (1-3 players x both maps) with the other options. --verbose prints
each game's result line, --trace a line per round (placements once everyone placed, haulers,
stockpile, enemies, buildings), the resolution report and the round's hauls and upkeep.
Stats: houses/population/units at checkpoints, hungry rounds, keep damage, goods made and
hauled, haulers used / idle and the auto-haul share, units per worked building, gold, upgrades. Run from the Dev folder (/T in the pod); it puts APP/ on sys.path.
"""

import sys

if __name__ == "__main__":
    sys.exit("Bastion playtest bots are disabled until they're rewritten for the redesign (see this file's header).")

import argparse  # noqa: E402
import os
import random
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if APP not in sys.path:
    sys.path.insert(0, APP)

from games.bastion.logic.match import Match  # noqa: E402
from games.bastion.tests.bots import Bot, Stats, auto_haul_preview, goods_total  # noqa: E402

CHECKPOINTS = (5, 10, 15, 20)
MAX_ROUNDS = 60


def trace_line(match, placed_now):
    placed = Counter()
    for target, by in placed_now.items():
        name = target if not target.startswith("s") else match.board.structures[int(target[1:])].kind
        placed[name] += sum(by.values())
    foes = " ".join(f"{f.enemy['id']}:{f.hp}" for f in match.foes if f.active)
    stock = " ".join(f"{k[:2]}{v}" for k, v in match.stock.items() if v)
    kinds = Counter(s.kind for s in match.board.structures.values())
    levels = sum(s.level for s in match.board.structures.values())
    stored = sum(s.stored() for s in match.board.structures.values())
    units = sum(s.units for s in match.seats.values())
    hands = " / ".join(",".join(c["card"].replace("plan-", "+") for c in seat.hand) for seat in match.seats.values())
    return (f"r{match.round:2} pop {match.population():2} units {units:2} hungry {match.hungry} keep {match.keep:2} "
            f"sold {match.soldiers} lv {levels} | hand {hands} "
            f"| {stock} stored {stored} | {dict(placed)} haul {units - sum(placed.values())} | {foes} | {dict(kinds)}")


def play_game(players, settings, seed, style, trace=False):
    rng = random.Random(seed)
    names = {f"p{i + 1}": f"Bot{i + 1}" for i in range(players)}
    match = Match(names, settings, rng=rng)
    stats = Stats()
    bots = {pid: Bot(match, pid, random.Random(seed * 31 + i), stats, style) for i, pid in enumerate(names)}
    per_round = []
    hungry_rounds = 0
    hungry_people = 0
    keep_hits = 0
    crews = Counter()  # units on a worked building -> times
    alive = {}  # enemy id -> rounds it was active at a round start
    while match.result is None and match.round <= MAX_ROUNDS:
        rnd = match.round
        houses = sum(1 for s in match.board.structures.values() if s.kind == "house")
        per_round.append({"round": rnd, "pop": match.population(), "houses": houses,
                          "units": sum(s.units for s in match.seats.values())})
        for pid in list(match.order):
            if match.result is None and match.phase == "place":
                bots[pid].place(ready=False)
        placed_now = {t: dict(by) for t, by in match.placed.items()}
        for t, by in placed_now.items():
            n = sum(by.values())
            if t.startswith("s"):
                crews[n] += 1
                stats.work_units += n
                stats.work_kinds[match.board.structures[int(t[1:])].kind] += n
            else:
                stats.fight_units += n
        for f in match.foes:
            if f.state == "active":
                alive[f.enemy["id"]] = alive.get(f.enemy["id"], 0) + 1
        if trace:
            print("  " + trace_line(match, placed_now))
        goods = goods_total(match)
        stored = sum(s.stored() for s in match.board.structures.values())
        for pid in list(match.order):
            if match.result is None and match.phase == "place":
                match.ready(pid)
        if match.result is None and match.phase == "act":
            stats.produced[rnd] += max(0, goods_total(match) - goods)
            stats.stored[rnd] += max(0, sum(s.stored() for s in match.board.structures.values()) - stored)
            stats.worked += sum(1 for s in match.board.structures.values() if s.worked)
            haulers = sum(s.haulers for s in match.seats.values())
            stats.haulers[rnd] = haulers
            stats.short_units += max(0, haulers - (sum(s.units for s in match.seats.values())
                                                     - sum(sum(by.values()) for by in placed_now.values())))
            if trace:
                for line in match.report["lines"]:
                    print("      " + line)
        guard = 0
        while match.result is None and match.round == rnd and match.phase == "act":
            pid = match.turn()
            keep = match.keep
            bots[pid].act()
            if match.result is None and match.turn() == pid:
                hauls, goods = auto_haul_preview(match, pid)
                stats.auto_hauls[rnd] += hauls
                stats.haul_units[rnd] += hauls
                stats.hauled[rnd] += goods
                stats.idle[rnd] += match.seats[pid].haulers - hauls
                match.end_turn(pid)
                if match.round != rnd:
                    keep_hits += max(0, keep - match.keep)
            guard += 1
            if guard > 20:
                raise RuntimeError("act phase stuck")
        if match.round != rnd or match.result:
            if match.eaten["hungry"]:
                hungry_rounds += 1
                hungry_people += match.eaten["hungry"]
        if trace and match.result is None:
            print(f"      hauled {stats.hauled[rnd]} in {stats.haul_units[rnd]} hauls ({stats.auto_hauls[rnd]} auto), "
                  f"{stats.idle[rnd]} idle; upkeep ate {match.eaten}")
    res = match.result or {"victory": False, "reason": "Too long", "round": match.round}
    return {
        "victory": res["victory"], "reason": res["reason"], "rounds": res["round"], "per_round": per_round,
        "stats": stats, "keep": match.keep, "keep_max": match.keep_max, "hungry_rounds": hungry_rounds,
        "hungry_people": hungry_people, "beaten": sum(1 for f in match.foes if f.state == "defeated"),
        "foes": len(match.foes), "keep_hits": keep_hits, "crews": crews,
        "levels": sum(s.level for s in match.board.structures.values()),
        "final_kinds": Counter(s.kind for s in match.board.structures.values()),
        "pop": match.population(), "stock": dict(match.stock),
        "enemies": [f.enemy["id"] + ("+" if f.state == "defeated" else "-") for f in match.foes],
        "alive": alive,
    }


def mean(values):
    values = list(values)
    return statistics.mean(values) if values else 0


def at_round(game, rnd, key):
    rows = [r for r in game["per_round"] if r["round"] <= rnd]
    return rows[-1][key] if rows else 0


def report(results, label):
    n = len(results)
    wins = sum(1 for g in results if g["victory"])
    print(f"\n=== {label}: {n} games, win {wins}/{n} = {100 * wins / n:.0f}%, rounds {mean(g['rounds'] for g in results):.1f}")
    losses = Counter(g["reason"] for g in results if not g["victory"])
    for reason, k in losses.most_common():
        print(f"  lost: {k} x {reason}")
    line = "  houses/pop at round " + ", ".join(
        f"{r}: {mean(at_round(g, r, 'houses') for g in results):.1f}/{mean(at_round(g, r, 'pop') for g in results):.0f}"
        for r in CHECKPOINTS)
    print(line + f", end: {mean(g['final_kinds']['house'] for g in results):.1f}/{mean(g['pop'] for g in results):.0f}")
    print(f"  units at round " + ", ".join(f"{r}: {mean(at_round(g, r, 'units') for g in results):.1f}" for r in CHECKPOINTS))
    print(f"  hungry rounds {mean(g['hungry_rounds'] for g in results):.1f} (people {mean(g['hungry_people'] for g in results):.1f})"
          f", keep end {mean(g['keep'] for g in results):.1f}/{results[0]['keep_max']}, keep damage taken "
          f"{mean(g['keep_hits'] for g in results):.1f}, enemies beaten {mean(g['beaten'] for g in results):.1f}/{results[0]['foes']}")
    rounds = mean(g["rounds"] for g in results)
    prod = mean(sum(g["stats"].produced.values()) for g in results)
    hauled = mean(sum(g["stats"].hauled.values()) for g in results)
    haul_units = mean(sum(g["stats"].haul_units.values()) for g in results)
    auto = mean(sum(g["stats"].auto_hauls.values()) for g in results)
    haulers = mean(sum(g["stats"].haulers.values()) for g in results)
    idle = mean(sum(g["stats"].idle.values()) for g in results)
    mid = [g for g in results if g["rounds"] >= 12]
    mid_hauls = mean(sum(1 for r in range(6, 13) if g["stats"].hauled[r] > 0) for g in mid) if mid else 0
    into = mean(sum(g["stats"].stored.values()) for g in results)
    print(f"  goods made {prod:.0f} ({prod / rounds:.1f}/round, {100 * into / max(1, prod):.0f}% into stores), hauled {hauled:.0f} ({hauled / rounds:.1f}/round), "
          f"rounds 6-12 with hauls {mid_hauls:.1f}/7")
    print(f"  haulers {haulers / rounds:.1f}/round: used {haul_units / rounds:.1f} ({100 * auto / max(1, haul_units):.0f}% "
          f"by auto-haul), idle {idle / rounds:.1f}; units that couldn't work {mean(g['stats'].short_units for g in results):.1f}/game")
    crews = Counter()
    for g in results:
        crews.update(g["crews"])
    worked = sum(crews.values())
    print(f"  units per worked building {sum(k * v for k, v in crews.items()) / max(1, worked):.2f} ("
          + ", ".join(f"{k}: {100 * v / max(1, worked):.0f}%" for k, v in sorted(crews.items())) + ")")
    kinds = Counter()
    for g in results:
        kinds.update(g["stats"].work_kinds)
    total = sum(kinds.values())
    print("  work units by building: " + ", ".join(f"{k} {100 * v / max(1, total):.0f}%" for k, v in kinds.most_common()))
    gold_out = Counter()
    for g in results:
        gold_out.update(g["stats"].gold_out)
    print(f"  gold in {mean(g['stats'].gold_in for g in results):.0f} (from cards), out "
          + ", ".join(f"{k} {v / n:.0f}" for k, v in gold_out.most_common()))
    ups = Counter()
    for g in results:
        ups.update(g["stats"].upgrades)
    print(f"  upgrades/game " + ", ".join(f"to level {k}: {v / n:.1f}" for k, v in sorted(ups.items()))
          + f" (tools {mean(g['stats'].tools_upgrades for g in results):.1f}, levels at the end {mean(g['levels'] for g in results):.1f})"
          f", tools sold {mean(g['stats'].tools_sold for g in results):.1f}")
    print(f"  units: work {mean(g['stats'].work_units for g in results):.0f}, fight {mean(g['stats'].fight_units for g in results):.0f},"
          f" rerolls {mean(g['stats'].rerolls for g in results):.1f}")
    stock = Counter()
    for g in results:
        stock.update(g["stock"])
    print("  stockpile at the end: " + ", ".join(f"{k} {v / n:.0f}" for k, v in stock.items()))
    built = Counter()
    for g in results:
        built.update(g["stats"].built)
    print("  built/game: " + ", ".join(f"{k} {v / n:.1f}" for k, v in built.most_common()))
    bought = Counter()
    for g in results:
        bought.update(g["stats"].bought)
    print("  bought/game: " + ", ".join(f"{k} {v / n:.1f}" for k, v in bought.most_common()))
    beaten = Counter()
    for g in results:
        beaten.update(e for e in g["enemies"])
    print("  enemies (+ beaten / - not): " + ", ".join(f"{k} {v}" for k, v in sorted(beaten.items())))
    alive = {}
    for g in results:
        for k, v in g["alive"].items():
            alive.setdefault(k, []).append(v)
    print("  rounds each enemy stayed: " + ", ".join(f"{k} {mean(v):.1f}" for k, v in sorted(alive.items())))
    return wins / n


def run(args, players, game_map):
    settings = {"difficulty": args.difficulty, "keepHealth": args.keep, "map": game_map, "enemies": args.enemies,
                "peaceRounds": args.peace, "enemyGap": args.gap}
    seeds = [args.seed + i for i in range(args.games)]
    if args.jobs > 1 and not args.trace and len(seeds) > 1:
        with ProcessPoolExecutor(args.jobs) as pool:
            results = list(pool.map(play_game, [players] * len(seeds), [settings] * len(seeds), seeds,
                                    [args.bot] * len(seeds)))
    else:
        results = [play_game(players, settings, seed, args.bot, args.trace) for seed in seeds]
    for i, g in enumerate(results):
        if args.verbose:
            print(f"  seed {args.seed + i}: {'WIN ' if g['victory'] else 'loss'} r{g['rounds']} pop {g['pop']} "
                  f"keep {g['keep']} {' '.join(g['enemies'])} {g['reason']}")
    return report(results, f"{args.bot} bot, {players}p, {game_map}, {args.difficulty}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument("--players", type=int, default=1)
    parser.add_argument("--map", default="valley")
    parser.add_argument("--difficulty", default="normal")
    parser.add_argument("--bot", default="good", choices=("good", "passive"))
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--keep", type=int, default=20)
    parser.add_argument("--enemies", type=int, default=5)
    parser.add_argument("--peace", type=int, default=5)
    parser.add_argument("--gap", type=int, default=3)
    parser.add_argument("--all", action="store_true", help="1-3 players on both maps")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1, help="games run in parallel processes")
    parser.add_argument("--trace", action="store_true", help="a line per round (use with --games 1)")
    args = parser.parse_args()
    started = time.time()
    if args.all:
        table = {}
        for game_map in ("valley", "highlands"):
            for players in (1, 2, 3):
                table[(players, game_map)] = run(args, players, game_map)
        print("\nwin rates: " + ", ".join(f"{p}p {m}: {100 * w:.0f}%" for (p, m), w in table.items()))
    else:
        run(args, args.players, args.map)
    print(f"({time.time() - started:.1f}s)")


if __name__ == "__main__":
    main()
