"""Marooned: points. Some are public during play (running()), the rest come at the end (final()).

Public during play: exploring, building, finished stages, starving nights.
At the end: escaping, relics, hunger, nightly ballots, the Imposter's own sources, and the
secret objectives. Highest total wins (ties share the win).

    running(m, pid)   # int, shown next to each player during play
    final(m)          # {pid: {"total", "lines": [[label, points], ...], "objectives": [...]}}
    winners(scores)   # [pid, ...]
"""

from . import objectives
from .people import STAGE_POINTS

BUILT_PER_POINT = 2
ESCAPE = 8
RELIC_ESCAPED = 3
RELIC_STRANDED = 1
WELL_FED = 2            # ending at hunger WELL_FED_HUNGER or less
WELL_FED_HUNGER = 1
STARVING = -1           # per night spent starving
VOTE_RIGHT = 1          # per night you voted for the Imposter
IMPOSTER_NO_ESCAPE = 12
IMPOSTER_PER_STRANDED = 3
IMPOSTER_WRONG_TOP = 1  # per night the most-voted player was innocent
IMPOSTER_SNAPPED = 2


def _common(s):
    lines = []
    if s.stats["explorePoints"]:
        lines.append(["Exploring", s.stats["explorePoints"]])
    if s.stats["built"] // BUILT_PER_POINT:
        lines.append(["Building", s.stats["built"] // BUILT_PER_POINT])
    if s.stats["stages"]:
        lines.append(["Stages finished", s.stats["stages"] * STAGE_POINTS])
    if s.stats["starving"]:
        lines.append(["Starving nights", s.stats["starving"] * STARVING])
    return lines


def running(m, pid):
    return sum(points for _, points in _common(m.people[pid]))


def wrong_top_votes(m):
    count = 0
    for night in m.vote_history.values():
        counts = {pid: n for pid, n in night["tally"].items() if pid != "nobody"}
        if not counts:
            continue
        top = max(counts.values())
        leaders = [pid for pid, n in counts.items() if n == top]
        if len(leaders) == 1 and leaders[0] != m.imposter:
            count += 1
    return count


def final(m):
    scores = {}
    castaways = [pid for pid in m.people if pid != m.imposter]
    stranded = [pid for pid in castaways if pid in m.order and pid not in m.escaped]
    for pid, s in m.people.items():
        lines = _common(s)
        relics = s.pack.get("relic", 0)
        if pid != m.imposter:
            if pid in m.escaped:
                lines.append(["Escaped", ESCAPE])
            right = sum(1 for choice in s.stats["votes"] if choice == m.imposter)
            if right:
                lines.append(["Voted for the Imposter", right * VOTE_RIGHT])
        else:
            if not m.escaped:
                lines.append(["Nobody escaped", IMPOSTER_NO_ESCAPE])
            elif stranded:
                lines.append(["Castaways left behind", len(stranded) * IMPOSTER_PER_STRANDED])
            wrong = wrong_top_votes(m)
            if wrong:
                lines.append(["Nights an innocent got the most votes", wrong * IMPOSTER_WRONG_TOP])
            if m.snapped:
                lines.append(["Snapped build checks", m.snapped * IMPOSTER_SNAPPED])
        if relics:
            per = RELIC_ESCAPED if pid in m.escaped else RELIC_STRANDED
            lines.append(["Relics", relics * per])
        if s.hunger <= WELL_FED_HUNGER:
            lines.append(["Well fed at the end", WELL_FED])
        kept = []
        for oid in m.objectives.get(pid, []):
            done = objectives.achieved(m, pid, oid)
            kept.append({**objectives.public(oid), "done": done})
            if done:
                lines.append([f"Objective: {objectives.OBJECTIVES[oid]['title']}", objectives.OBJECTIVES[oid]["points"]])
        scores[pid] = {"total": sum(p for _, p in lines), "lines": lines, "objectives": kept}
    return scores


def winners(scores, players):
    if not players:
        return []
    best = max(scores[pid]["total"] for pid in players)
    return [pid for pid in players if scores[pid]["total"] == best]
