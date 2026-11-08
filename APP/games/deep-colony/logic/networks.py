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

API:
    step(dt)
    needs_power(b) -> bool        the network at b's powerPort has an active user left unpowered,
                                  or a battery below 95%
    power_summary() -> {nid: {"gen": W, "use": W, "stored": J, "cap": J}}  (ints, last step)
    pipe_take(b, port, ids, kg) -> (el, kg, temp, germs)   port "pipeIn"/"pipeOut"; ids None = any
                                  element; takes from one element; unattached: (None, 0, 0, 0)
    pipe_put(b, port, el, kg, temp, germs) -> kg accepted (germs = total for the kg offered)
    pipe_has(b, port, el) -> kg of that element in the network
    pipe_room(b, port) -> kg that still fits (capacity PIPE_CAP kg per pipe segment, all elements)
    pipe_summary() -> {nid: {el: kg rounded to 0.1}}
Rebuilding pipes keeps contents: each old buffer moves to the new network holding its old cells
(capped; any excess is dropped).
"""

PIPE_CAP = 10.0
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
        self._ipcell = {}    # pipe: cell index -> nid
        self._icount = {}    # pipe: nid -> segment count
        self._buf = {}       # pipe: nid -> {el: [kg, temp, germs]}

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
        old_pcell, old_buf = self._ipcell, self._buf
        self._ipcell, self._icount = self._components("pipe", "p")
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
        # pipe contents move to the network that now holds their old cells
        remap = {}
        for cell, onid in old_pcell.items():
            nn = self._ipcell.get(cell)
            if nn and onid not in remap:
                remap[onid] = nn
        self._buf = {}
        for onid, content in old_buf.items():
            nn = remap.get(onid)
            if nn is None:
                continue
            target = self._buf.setdefault(nn, {})
            for el, (kg, temp, germs) in content.items():
                self._add(target, el, kg, temp, germs)
        for nid, content in self._buf.items():
            total = sum(v[0] for v in content.values())
            cap = self._icount[nid] * PIPE_CAP
            if total > cap:
                scale = cap / total
                for v in content.values():
                    v[0] *= scale
                    v[2] *= scale

    @staticmethod
    def _add(content, el, kg, temp, germs):
        cur = content.get(el)
        if cur is None:
            content[el] = [kg, temp, germs]
        else:
            total = cur[0] + kg
            cur[1] = (cur[1] * cur[0] + temp * kg) / total if total > 0 else temp
            cur[0] = total
            cur[2] += germs

    # --- power ----------------------------------------------------------------------------

    def step(self, dt):
        self._sync()
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

    def _net(self, b, port):
        self._sync()
        pc = b.port_cell(port)
        if pc is None or not b.built:
            return None
        return self._ipcell.get(self.match.world.idx(*pc))

    def _total(self, nid):
        return sum(v[0] for v in self._buf.get(nid, {}).values())

    def pipe_take(self, b, port, ids, kg):
        nid = self._net(b, port)
        content = self._buf.get(nid) if nid else None
        if not content or kg <= 0:
            return None, 0.0, 0.0, 0.0
        best = None
        for el, v in content.items():
            if (ids is None or el in ids) and v[0] > MIN_KG and (best is None or v[0] > content[best][0]):
                best = el
        if best is None:
            return None, 0.0, 0.0, 0.0
        v = content[best]
        got = min(kg, v[0])
        germs = v[2] * got / v[0]
        temp = v[1]
        v[0] -= got
        v[2] -= germs
        if v[0] <= MIN_KG:
            del content[best]
        return best, got, temp, germs

    def pipe_put(self, b, port, el, kg, temp, germs):
        nid = self._net(b, port)
        if nid is None or kg <= 0:
            return 0.0
        room = self._icount[nid] * PIPE_CAP - self._total(nid)
        put = min(kg, max(0.0, room))
        if put <= 0:
            return 0.0
        self._add(self._buf.setdefault(nid, {}), el, put, temp, germs * put / kg)
        return put

    def pipe_has(self, b, port, el):
        nid = self._net(b, port)
        v = self._buf.get(nid, {}).get(el) if nid else None
        return v[0] if v else 0.0

    def pipe_room(self, b, port):
        nid = self._net(b, port)
        if nid is None:
            return 0.0
        return max(0.0, self._icount[nid] * PIPE_CAP - self._total(nid))

    def pipe_summary(self):
        self._sync()
        out = {}
        for nid, content in self._buf.items():
            out[nid] = {el: round(v[0], 1) for el, v in content.items() if v[0] >= 0.05}
        return out
