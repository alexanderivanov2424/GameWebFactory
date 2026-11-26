"""Food list groups: named sets of items, mixed into store.Store (GroupsMixin).

A group is {id, name, items}; an entry in it is {id, food} or {id, group} (another group, kept by
reference, so changes to it show up everywhere it's used). A food or group is in a group at most once.
Group names follow the list name rules (they're addresses: /food-list/group/<name>) and are unique
among groups, ignoring case. A group never ends up inside itself, directly or through other groups:
that's refused when adding, and such entries are dropped when loading. Adding a group to a list puts
every item it holds, through nested groups too, on the list (items already there are skipped). Foods
in a group are kept like foods on a list (store.Store._unused counts them as used).
Uses the Store's foods, lists and helpers (_food_for_name, _tidy, public_food, summary...).
"""

from checks import LIST_NAME_MAX, Rejected, address_name, clean_text, free_name, has_id, new_id, url_name

MAX_GROUPS = 100
MAX_GROUP_ITEMS = 300  # entries per group


class GroupsMixin:
    groups = ()  # [{id, name, items}], set by _load_groups

    # ---- loading ----

    def _load_groups(self, raw, seen):
        """Groups from saved data (after foods): bad entries are dropped, then nested groups that are
        gone or would put a group inside itself."""
        self.groups = []
        for entry in raw if isinstance(raw, list) else []:
            if len(self.groups) >= MAX_GROUPS:
                break
            if not has_id(entry) or entry["id"] in seen:
                continue
            seen.add(entry["id"])
            try:
                saved = clean_text(entry.get("name"), LIST_NAME_MAX)
            except Rejected:
                saved = ""
            taken = {group["name"].lower() for group in self.groups}
            name = free_name(url_name(saved) or "Group", taken, LIST_NAME_MAX, sep="-")
            if name != saved:
                self.moved = True
            group = {"id": entry["id"], "name": name, "items": []}
            targets = set()
            for item in entry.get("items", []) if isinstance(entry.get("items"), list) else []:
                if len(group["items"]) >= MAX_GROUP_ITEMS:
                    break
                key = "food" if isinstance(item, dict) and "food" in item else "group"
                target = item.get(key) if isinstance(item, dict) else None
                if (not has_id(item) or item["id"] in seen or not isinstance(target, str) or target in targets
                        or (key == "food" and target not in self.foods)):
                    continue
                seen.add(item["id"])
                targets.add(target)
                group["items"].append({"id": item["id"], key: target})
            self.groups.append(group)
        ids = {group["id"] for group in self.groups}
        for group in self.groups:  # one at a time, so a loop loses just one link
            kept = [item for item in group["items"] if "food" in item
                    or (item["group"] in ids and group["id"] not in self._inside(item["group"]))]
            if len(kept) != len(group["items"]):
                group["items"] = kept
                self.moved = True

    # ---- reading ----

    def _groups_by_id(self):
        return {group["id"]: group for group in self.groups}

    def _inside(self, group_id):
        """The ids of group_id and every group in it, however deep."""
        by_id = self._groups_by_id()
        found, todo = set(), [group_id]
        while todo:
            current = todo.pop()
            if current in found or current not in by_id:
                continue
            found.add(current)
            todo.extend(item["group"] for item in by_id[current]["items"] if "group" in item)
        return found

    def group_foods(self, group_id):
        """Every food in a group, through nested groups too, in order, each once."""
        by_id = self._groups_by_id()
        foods, seen_foods, seen_groups = [], set(), set()

        def walk(current):
            seen_groups.add(current)
            for item in by_id[current]["items"]:
                if "food" in item:
                    if item["food"] not in seen_foods:
                        seen_foods.add(item["food"])
                        foods.append(item["food"])
                elif item["group"] in by_id and item["group"] not in seen_groups:
                    walk(item["group"])

        if group_id in by_id:
            walk(group_id)
        return foods

    def group_summaries(self):
        """Every group for the lists screen and suggestions: size = items it adds, groups = the ones in it."""
        return [{"id": group["id"], "name": group["name"], "size": len(self.group_foods(group["id"])),
                 "groups": [item["group"] for item in group["items"] if "group" in item]}
                for group in self.groups]

    def find_group(self, group_id):
        for group in self.groups:
            if group["id"] == group_id:
                return group
        raise Rejected("That group is gone (someone may have deleted it).", 404)

    def _public_entry(self, item):
        if "food" in item:
            return dict(self.public_food(item["food"]), id=item["id"])
        other = self.find_group(item["group"])
        return {"id": item["id"], "group": other["id"], "name": other["name"],
                "size": len(self.group_foods(other["id"]))}

    def public_group(self, group_id):
        """One group with its entries (foods as items without checked; groups as {id, group, name, size}),
        plus the summary."""
        group = self.find_group(group_id)
        return dict(self.summary(), list={"id": group["id"], "name": group["name"], "group": True,
                                          "items": [self._public_entry(item) for item in group["items"]]})

    # ---- changing groups ----

    def _group_name(self, value, other_than=None):
        name = address_name(value, "group")
        if any(group["name"].lower() == name.lower() for group in self.groups if group is not other_than):
            raise Rejected(f"There's already a group called “{name}”.")
        return name

    def add_group(self, data):
        if len(self.groups) >= MAX_GROUPS:
            raise Rejected(f"There are already {MAX_GROUPS} groups.", 507)
        group = {"id": new_id(), "name": self._group_name(data.get("name")), "items": []}
        self.groups.append(group)
        self.save()
        return {"id": group["id"], "name": group["name"]}

    def update_group(self, group_id, data):
        group = self.find_group(group_id)
        if "name" in data:
            group["name"] = self._group_name(data["name"], other_than=group)
        self.save()
        return {"id": group["id"], "name": group["name"]}

    def delete_group(self, group_id):
        """Delete a group, and take it out of every group holding it (its foods stay if used elsewhere)."""
        group = self.find_group(group_id)
        self.groups.remove(group)
        for other in self.groups:
            other["items"] = [item for item in other["items"] if item.get("group") != group_id]
        self._tidy()

    def add_to_group(self, group_id, data):
        """Put an item (by name, made if it's new) or another group ({"group": id}) in a group."""
        group = self.find_group(group_id)
        if len(group["items"]) >= MAX_GROUP_ITEMS:
            raise Rejected(f"The group is full ({MAX_GROUP_ITEMS} entries).", 507)
        if "group" in data:
            child = data["group"]
            other = self.find_group(child) if isinstance(child, str) else None
            if other is None:
                raise Rejected("Bad group.")
            if group_id in self._inside(child):
                raise Rejected(f"“{other['name']}” can't go in “{group['name']}”: it would end up inside itself.")
            if any(item.get("group") == child for item in group["items"]):
                raise Rejected(f"“{other['name']}” is already in this group.", 409)
            item = {"id": new_id(), "group": child}
        else:
            food_id = self._food_for_name(data.get("name"), [item.get("food") for item in group["items"]],
                                          "in this group")
            item = {"id": new_id(), "food": food_id}
        group["items"].append(item)
        self.save()
        return self._public_entry(item)

    def remove_from_group(self, group_id, entry_id):
        group = self.find_group(group_id)
        kept = [item for item in group["items"] if item["id"] != entry_id]
        if len(kept) == len(group["items"]):
            raise Rejected("That's not in the group any more.", 404)
        group["items"] = kept
        self._tidy()

    def add_group_to_list(self, list_id, data):
        """Put every item of a group (and the groups in it) on a list; ones already there are skipped."""
        lst = self.find_list(list_id)
        group_id = data.get("group")
        group = self.find_group(group_id) if isinstance(group_id, str) else None
        if group is None:
            raise Rejected("Bad group.")
        on_list = {item["food"] for item in lst["items"]}
        new = [food_id for food_id in self.group_foods(group_id) if food_id not in on_list]
        if len(lst["items"]) + len(new) > self.max_items:
            raise Rejected(f"That doesn't fit: a list holds at most {self.max_items} items.", 507)
        lst["items"].extend({"id": new_id(), "food": food_id, "checked": False, "pushed": False} for food_id in new)
        self.save()
        return {"added": len(new)}
