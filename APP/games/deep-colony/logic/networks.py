"""Power and pipe networks.

Networks(match) (match.networks). Components are 4-connected cells of finished buildings in the
"wire" layer (power networks, id "w<min cell index>") and the "pipe" layer (pipe networks, id
"p<min cell index>"). They are rebuilt only when match.buildings.version changes. A building joins
a power network when its powerPort cell holds a built wire, and a pipe network through its
pipeIn / pipeOut port cell holding a built pipe.

Power (step(dt), once per game step, before machines.step): per network, generators with
b.state["producing"] add d["power"]["gen"] W; users (d["power"]["use"]) that are built, enabled and
b.state["active"] demand W; batteries (d["power"]["capacity"] J, charge in b.state["charge"]) cover a
shortfall and take the surplus. When supply (plus stored charge) does not cover everyone, users are
powered in id order while the energy lasts. b.powered is set on every power user (False when not
attached, inactive or short of energy).

Pipes are segment by segment: every finished pipe cell (liquid layer "pipe", 10 kg; gas layer
"gaspipe", 1 kg) holds at most one packet [el, kg, temp, germs]. Every PACKET_DT seconds each packet
moves one segment toward the nearest consumer port (a building's pipeIn / gasIn cell, vents
included): into a neighbouring segment with a smaller BFS distance that is empty or holds the same
element with room. Producers put into the segment at their out port; consumers take from the segment
at their in port (only a matching element: a different packet there blocks, like the original game).
A segment that disappears (deconstructed, cancelled) hands its packet to world.release: never lost.

API:
    step(dt)
    needs_power(b) -> bool        the network at b's powerPort has an active user left unpowered,
                                  or a battery below 95%
    power_summary() -> {nid: {"gen": W, "use": W, "stored": J, "cap": J}}  (ints, last step)
    pipe_take(b, port, ids, kg) -> (el, kg, temp, germs)   port "pipeIn"/"pipeOut" (liquid) or
                                  "gasIn"/"gasOut" (gas); ids None = any element; takes from the
                                  packet in the segment at that port; none: (None, 0, 0, 0)
    pipe_put(b, port, el, kg, temp, germs) -> kg accepted (germs = total for the kg offered)
    pipe_has(b, port, el) -> kg of that element in the port's segment
    pipe_room(b, port, el=None) -> kg that still fits there (0 if another element sits there)
    pipe_summary() / gas_summary() -> {"<cell index>": {"el", "kg"}} (kg rounded to 0.1 / 0.01)
"""

PIPE_CAP = 10.0   # kg per liquid pipe segment
GAS_CAP = 1.0     # kg per gas pipe segment
PACKET_DT = 0.2   # s per packet move
PORT_KIND = {"pipeIn": "pipe", "pipeOut": "pipe", "gasIn": "gaspipe", "gasOut": "gaspipe"}
CAP = {"pipe": PIPE_CAP, "gaspipe": GAS_CAP}
SINKS = {"pipe": "pipeIn", "gaspipe": "gasIn"}
MIN_KG = 1e-6


def _key(b):
    digits = b.id[1:]
    return (int(digits) if digits.isdigit() else 0, b.id)


class Networks:
    def __init__(self, match):
        self.match = match
        self._version = None
        self._pcell = {}     # power: cell index -> nid
        self._members = {}   # power: nid -> [building]
        self._attached = {}  # building id -> power nid
        self._pinfo = {}     # nid -> {"gen", "use", "stored", "cap", "short", "low"}
        self._pk = {"pipe": {}, "gaspipe": {}}    # kind -> {cell index: [el, kg, temp, germs]}
        self._cells = {"pipe": set(), "gaspipe": set()}
        self._order = {"pipe": [], "gaspipe": []}  # (distance, cell) nearest consumer first
        self._dist = {"pipe": {}, "gaspipe": {}}
        self._acc = 0.0

    # --- components -----------------------------------------------------------------------

    def _components(self, layer, prefix):
        world = self.match.world
        buildings = self.match.buildings
        cells = {i for i, bid in buildings.layers[layer].items()
                 if bid in buildings.by_id and buildings.by_id[bid].built}
        cell2net, counts = {}, {}
        for start in sorted(cells):
            if start in cell2net:
                continue
            nid = f"{prefix}{start}"
            cell2net[start] = nid
            stack, n = [start], 0
            while stack:
                i = stack.pop()
                n += 1
                for j in world.nbrs[i]:
                    if j in cells and j not in cell2net:
                        cell2net[j] = nid
                        stack.append(j)
            counts[nid] = n
        return cell2net, counts

    def _sync(self):
        version = self.match.buildings.version
        if version == self._version:
            return
        self._version = version
        world = self.match.world
        self._pcell, _ = self._components("wire", "w")
        self._members, self._attached = {}, {}
        for b in self.match.buildings:
            if not b.built or not b.d["power"]:
                continue
            pc = b.port_cell("powerPort")
            nid = self._pcell.get(world.idx(*pc)) if pc else None
            if nid:
                self._members.setdefault(nid, []).append(b)
                self._attached[b.id] = nid
        for members in self._members.values():
            members.sort(key=_key)
        self._sync_pipes()

    def _sync_pipes(self):
        world = self.match.world
        buildings = self.match.buildings
        for kind in CAP:
            cells = {i for i, bid in buildings.layers[kind].items()
                     if bid in buildings.by_id and buildings.by_id[bid].built}
            self._cells[kind] = cells
            packets = self._pk[kind]
            for i in [i for i in packets if i not in cells]:
                el, kg, temp, germs = packets.pop(i)
                world.release(*world.xy(i), el, kg, temp, germs)
            frontier = []
            for b in buildings:
                pc = b.port_cell(SINKS[kind]) if b.built else None
                i = world.idx(*pc) if pc and world.inside(*pc) else None
                if i in cells and i not in frontier:
                    frontier.append(i)
            dist = {i: 0 for i in frontier}
            while frontier:
                nxt = []
                for i in frontier:
                    for j in world.nbrs[i]:
                        if j in cells and j not in dist:
                            dist[j] = dist[i] + 1
                            nxt.append(j)
                frontier = nxt
            self._dist[kind] = dist
            self._order[kind] = sorted((d, i) for i, d in dist.items())

    def _move(self, kind):
        """One packet move: nearest-to-consumer first, so a queue advances together."""
        packets, dist, world, cap = self._pk[kind], self._dist[kind], self.match.world, CAP[kind]
        for d, i in self._order[kind]:
            pk = packets.get(i)
            if pk is None or d == 0:
                continue
            for dj, j in sorted((dist[j], j) for j in world.nbrs[i] if dist.get(j, d) < d):
                other = packets.get(j)
                if other is None:
                    packets[j] = packets.pop(i)
                    break
                if other[0] == pk[0] and other[1] < cap - MIN_KG:
                    put = min(pk[1], cap - other[1])
                    share = put / pk[1]
                    total = other[1] + put
                    other[2] = (other[2] * other[1] + pk[2] * put) / total
                    other[3] += pk[3] * share
                    other[1] = total
                    pk[3] -= pk[3] * share
                    pk[1] -= put
                    if pk[1] <= MIN_KG:
                        del packets[i]
                    break

    # --- power ----------------------------------------------------------------------------

    def step(self, dt):
        self._sync()
        self._acc = min(self._acc + dt, 5 * PACKET_DT)
        while self._acc >= PACKET_DT:
            self._acc -= PACKET_DT
            for kind in CAP:
                self._move(kind)
        users_seen = set()
        info = {}
        for nid, members in self._members.items():
            gen = 0.0
            users, batteries = [], []
            for b in members:
                p = b.d["power"]
                if p.get("gen") and b.state.get("producing") and b.enabled:
                    gen += p["gen"]
                if p.get("use") and b.enabled and b.state.get("active"):
                    users.append(b)
                if p.get("capacity"):
                    batteries.append(b)
            demand = sum(b.d["power"]["use"] for b in users)
            stored = sum(b.state.get("charge", 0.0) for b in batteries)
            cap = sum(b.d["power"]["capacity"] for b in batteries)
            energy = gen * dt + stored
            spent = 0.0
            short = False
            for b in users:
                need = b.d["power"]["use"] * dt
                if not short and energy - spent >= need - 1e-9:
                    b.powered = True
                    spent += need
                else:
                    short = True
                    b.powered = False
                users_seen.add(b.id)
            supply = gen * dt
            if spent <= supply:
                surplus = supply - spent
                for b in batteries:  # fill emptiest-first share by room
                    room = b.d["power"]["capacity"] - b.state.get("charge", 0.0)
                    add = min(room, surplus)
                    b.state["charge"] = b.state.get("charge", 0.0) + add
                    surplus -= add
            else:
                draw = spent - supply
                for b in batteries:
                    have = b.state.get("charge", 0.0)
                    take = min(have, draw)
                    b.state["charge"] = have - take
                    draw -= take
            stored_after = sum(b.state.get("charge", 0.0) for b in batteries)
            info[nid] = {"gen": gen, "use": demand, "stored": stored_after, "cap": cap, "short": short,
                         "low": cap > 0 and stored_after < 0.95 * cap}
        self._pinfo = info
        for members in self._members.values():
            for b in members:
                if b.d["power"].get("use") and b.id not in users_seen:
                    b.powered = False
        for b in self.match.buildings:
            if b.built and b.d["power"].get("use") and b.id not in self._attached:
                b.powered = False

    def needs_power(self, b):
        self._sync()
        nid = self._attached.get(b.id)
        info = self._pinfo.get(nid)
        # a running generator keeps being needed while something draws from it (else the operator
        # would quit the moment the shortage is fixed and power would flicker)
        return bool(info and (info["short"] or info["low"] or (info["gen"] > 0 and info["use"] > 0)))

    def power_summary(self):
        return {nid: {"gen": int(i["gen"]), "use": int(i["use"]), "stored": int(i["stored"]), "cap": int(i["cap"])}
                for nid, i in self._pinfo.items()}

    # --- pipes ----------------------------------------------------------------------------

    def _seg(self, b, port):
        """(packets dict, cell index, cap) of the segment at b's port, or None."""
        self._sync()
        kind = PORT_KIND[port]
        pc = b.port_cell(port)
        if pc is None or not b.built:
            return None
        i = self.match.world.idx(*pc)
        return (self._pk[kind], i, CAP[kind]) if i in self._cells[kind] else None

    def pipe_take(self, b, port, ids, kg):
        seg = self._seg(b, port)
        pk = seg[0].get(seg[1]) if seg else None
        if pk is None or kg <= 0 or (ids is not None and pk[0] not in ids):
            return None, 0.0, 0.0, 0.0
        got = min(kg, pk[1])
        germs = pk[3] * got / pk[1]
        el, temp = pk[0], pk[2]
        pk[1] -= got
        pk[3] -= germs
        if pk[1] <= MIN_KG:
            del seg[0][seg[1]]
        return el, got, temp, germs

    def pipe_put(self, b, port, el, kg, temp, germs):
        seg = self._seg(b, port)
        if seg is None or kg <= 0:
            return 0.0
        packets, i, cap = seg
        pk = packets.get(i)
        if pk is None:
            put = min(kg, cap)
            packets[i] = [el, put, temp, germs * put / kg]
            return put
        if pk[0] != el:
            return 0.0
        put = min(kg, max(0.0, cap - pk[1]))
        if put <= 0:
            return 0.0
        total = pk[1] + put
        pk[2] = (pk[2] * pk[1] + temp * put) / total
        pk[3] += germs * put / kg
        pk[1] = total
        return put

    def pipe_has(self, b, port, el):
        seg = self._seg(b, port)
        pk = seg[0].get(seg[1]) if seg else None
        return pk[1] if pk and pk[0] == el else 0.0

    def pipe_room(self, b, port, el=None):
        seg = self._seg(b, port)
        if seg is None:
            return 0.0
        pk = seg[0].get(seg[1])
        if pk is None:
            return seg[2]
        if el is not None and pk[0] != el:
            return 0.0
        return max(0.0, seg[2] - pk[1])

    def _summary(self, kind, digits):
        self._sync()
        out = {}
        for i, (el, kg, _, _) in self._pk[kind].items():
            if round(kg, digits) > 0:
                out[str(i)] = {"el": el, "kg": round(kg, digits)}
        return out

    def pipe_summary(self):
        return self._summary("pipe", 1)

    def gas_summary(self):
        return self._summary("gaspipe", 2)
