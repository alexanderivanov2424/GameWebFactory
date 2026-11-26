"""Food list: several shopping lists, groups of items and every saved item, kept in <data>/lists.json,
with the pictures in <data>/images/<id>.png. Value checks are in checks.py, groups in groups.py.

The data:
- foods: every item on a list, in a group or in the Global list, so the page can suggest it when adding:
  {id, name, tags: [tag id], notes, images: [image id], global}. Everything about an item lives
  here, once, whichever list it's on. global (false for new foods) says it's in the Global list, set
  with "Add to global" in the item editor; a food with pictures is always global (adding one sets it,
  and it can't be unset); a food that isn't global is deleted as soon as it's on no list and in no group. Foods saved
  before the flag existed load as global.
  Names are lowercase (whatever is typed is lowercased; symbols, spaces and digits are fine) and
  unique: adding a name that's already a food reuses it, and a rename to another food's name is
  refused. Deleting a food (only from the Global list) takes it off every list and group and deletes its
  pictures.
- tags: every tag ever made ({id, name, hue}), kept forever. Names are lowercase letters and
  single spaces only, and unique; hue (0-359) is the tag's colour, picked at random when it's made
  among the hues used least so far. Setting an item's tags by name makes any new ones. A tag's
  name and hue can be changed (update_tag), and tags made (add_tag) or deleted (delete_tag, which
  takes them off every item), from the lists screen.
- lists: {id, name, items}; list names are unique ignoring case and there is always at least one.
  A list name is the list's address (/food-list/<name>), so it may only have ASCII letters, digits,
  "-" and "_", and "global" (the Global list's address) is refused; older names are made to fit when
  loaded ("Food list" -> "Food-list"). An entry on a list is {id, food, checked, pushed}; a food is on a list
  at most once. checked and pushed exclude each other (setting one clears the other); clearing the
  checked items also unpushes the rest.
- groups: {id, name, items}, named sets of items and other groups; see groups.py.
The page's Global list isn't stored: it's every global food (public_foods).
Fields from older versions (templates and copies, amounts, units) are ignored when loaded and
dropped at the next save.

Older data is moved over when loaded (and saved again once): list.json (one list:
{"items": [{id, name, notes, checked, images}]}) becomes the list "Food list" when lists.json
doesn't exist yet (list.json itself is left as it was), and notes/pictures that were kept on list
entries move to their food (notes joined, pictures up to the limit).

Nothing from the browser is trusted. Every value is checked here before it's kept:
- text: must be a string, normalised (NFC), control/format/private/unassigned characters dropped
  (newlines kept in notes), trimmed, and rejected when longer than the limit;
- checked, pushed and global: must be exactly true or false;
- ids are made here (random hex) and the browser can only name existing ones; file names are
  only ever built from those ids, never from anything the browser sends;
- images come in as raw RGB and go out as a PNG written by images.py.
Limits (lists, items per list, groups and their entries, foods, tags, pictures per item and in all, total data size, uploads
per hour) keep a stranger who finds the page from filling the disk. lists.json is checked the
same way when it's loaded, and image files nobody refers to are removed then.

Files are written to a temporary name and renamed, so a crash never leaves a half-written file.
"""

import json
import os
import secrets
import time
from collections import deque
from pathlib import Path

import images
from checks import (ID, LIST_NAME_MAX, Rejected, address_name, clean_text, food_name, free_name, has_id, new_id,
                    tag_name, url_name)
from groups import GroupsMixin

NOTES_MAX = 500
MAX_LISTS = 30
MAX_ITEMS = 300  # per list
MAX_FOODS = 3000
MAX_TAGS = 200
MAX_TAGS_PER_ITEM = 10
HUES = range(0, 360, 30)  # colours a new tag picks from
MAX_IMAGES_PER_ITEM = 4
MAX_IMAGES = 300
MAX_DATA_BYTES = 200 * 1024 * 1024
UPLOADS_PER_HOUR = 120
MAX_DELETE = 500  # foods deleted in one request
DEFAULT_LIST = "Food-list"
RESERVED_LIST_NAMES = {"global"}  # the Global list's address


def write_atomic(path, data):
    tmp = path.with_name(f".{path.name}.tmp")
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path):
    """The JSON object in path, or None when it's missing or unreadable."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


class Store(GroupsMixin):
    max_items = MAX_ITEMS  # per list (groups.py checks it too)

    def __init__(self, folder):
        self.folder = Path(folder)
        self.images_dir = self.folder / "images"
        self.data_file = self.folder / "lists.json"
        self.old_file = self.folder / "list.json"  # before there were several lists
        self.lists = []
        self.groups = []    # see groups.py
        self.foods = {}     # food id -> {"name", "tags", "notes", "images", "global"}
        self.food_ids = {}  # name -> food id
        self.tags = {}      # tag id -> {"name", "hue"}
        self.tag_ids = {}   # name -> tag id
        self.uploads = deque()  # times of recent uploads (all users)
        self.images_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.load()

    # ---- loading and saving ----

    def load(self):
        self.moved = not self.data_file.exists()  # older data was moved over: save once loaded
        raw = read_json(self.data_file)
        if raw is None and self.moved:
            old = read_json(self.old_file) or {}
            raw = {"lists": [{"id": new_id(), "name": DEFAULT_LIST, "items": old.get("items", [])}]}
        raw = raw or {}
        self.lists, self.foods, self.food_ids, self.tags, self.tag_ids = [], {}, {}, {}, {}
        seen = set()
        for key, load, limit, kept in (("tags", self._load_tag, MAX_TAGS, self.tags),
                                       ("foods", self._load_food, MAX_FOODS, self.foods),
                                       ("lists", self._load_list, MAX_LISTS, self.lists)):
            for entry in raw.get(key, []) if isinstance(raw.get(key), list) else []:
                if len(kept) >= limit:
                    break
                try:
                    load(entry, seen)
                except Rejected:
                    continue
        if not self.lists:
            self.lists.append(self._new_list(DEFAULT_LIST))
        self._load_groups(raw.get("groups"), seen)
        for food in self.foods.values():
            if food["images"] and not food["global"]:
                food["global"] = self.moved = True  # foods with pictures are always global
        unused = self._unused()
        if unused:
            self._forget(unused)  # their pictures go with the unreferenced files below
            self.moved = True
        referenced = {image for food in self.foods.values() for image in food["images"]}
        for path in self.images_dir.iterdir():
            if path.is_file() and (path.stem not in referenced or path.suffix != ".png"):
                path.unlink(missing_ok=True)
        self.data_bytes = sum(p.stat().st_size for p in self.images_dir.iterdir() if p.is_file())
        if self.moved:
            self.save()

    def _load_tag(self, entry, seen):
        if not has_id(entry) or entry["id"] in seen:
            raise Rejected("bad tag")
        name = tag_name(entry.get("name"))
        if name in self.tag_ids:
            raise Rejected("duplicate tag")
        hue = entry.get("hue")
        if not isinstance(hue, int) or isinstance(hue, bool) or not 0 <= hue < 360:
            hue = self._new_hue()
        seen.add(entry["id"])
        self.tags[entry["id"]] = {"name": name, "hue": hue}
        self.tag_ids[name] = entry["id"]

    def _load_food(self, entry, seen):
        if not has_id(entry) or entry["id"] in seen:
            raise Rejected("bad food")
        name = free_name(food_name(entry.get("name")) or "?", self.food_ids)
        food = self._make_food(entry["id"], name)
        seen.add(entry["id"])
        for tag in entry.get("tags", []) if isinstance(entry.get("tags"), list) else []:
            if isinstance(tag, str) and tag in self.tags and tag not in food["tags"] and len(food["tags"]) < MAX_TAGS_PER_ITEM:
                food["tags"].append(tag)
        try:
            food["notes"] = clean_text(entry.get("notes"), NOTES_MAX, multiline=True)
        except Rejected:
            pass
        food["global"] = entry.get("global", True) is True  # saved before the flag: was in the Global list
        self._take_images(food, entry.get("images"), seen)

    def _take_images(self, food, pictures, seen):
        for image in pictures if isinstance(pictures, list) else []:
            if (isinstance(image, str) and ID.match(image) and image not in seen
                    and (self.images_dir / f"{image}.png").is_file()
                    and len(food["images"]) < MAX_IMAGES_PER_ITEM):
                seen.add(image)
                food["images"].append(image)

    def _load_list(self, entry, seen):
        if not has_id(entry) or entry["id"] in seen:
            raise Rejected("bad list")
        seen.add(entry["id"])
        taken = {lst["name"].lower() for lst in self.lists} | RESERVED_LIST_NAMES
        try:
            saved = clean_text(entry.get("name"), LIST_NAME_MAX)
        except Rejected:
            saved = ""
        name = free_name(url_name(saved) or "List", taken, LIST_NAME_MAX, sep="-")
        if name != saved:
            self.moved = True  # save the fitted name
        lst = self._new_list(name, entry_id=entry["id"])
        on_list = set()
        for raw in entry.get("items", []) if isinstance(entry.get("items"), list) else []:
            if len(lst["items"]) >= MAX_ITEMS:
                break
            try:
                lst["items"].append(self._load_item(raw, seen, on_list))
            except Rejected:
                continue
        self.lists.append(lst)

    def _load_item(self, entry, seen, on_list):
        if not has_id(entry) or entry["id"] in seen:
            raise Rejected("bad item")
        if "food" in entry:
            food_id = entry["food"]
            if not isinstance(food_id, str) or food_id not in self.foods or food_id in on_list:
                raise Rejected("bad food")
        else:  # from the old list.json: the entry has its own name
            name = food_name(entry.get("name")) or "?"
            food_id = self.food_ids.get(name)
            if food_id in on_list:
                name, food_id = free_name(name, self.food_ids), None
            if food_id is None:
                if len(self.foods) >= MAX_FOODS:
                    raise Rejected("too many foods")
                food_id = new_id()
                self._make_food(food_id, name)
        seen.add(entry["id"])
        on_list.add(food_id)
        food = self.foods[food_id]
        if "notes" in entry or "images" in entry:  # from before everything moved to the food
            self.moved = True
            try:
                notes = clean_text(entry.get("notes"), NOTES_MAX, multiline=True)
            except Rejected:
                notes = ""
            if notes and notes not in food["notes"]:
                joined = (food["notes"] + "\n" + notes).strip()
                if len(joined) <= NOTES_MAX:
                    food["notes"] = joined
            self._take_images(food, entry.get("images"), seen)
        checked = entry.get("checked") is True
        return {"id": entry["id"], "food": food_id, "checked": checked, "pushed": not checked and entry.get("pushed") is True}

    def save(self):
        data = json.dumps({
            "tags": [dict(tag, id=tag_id) for tag_id, tag in self.tags.items()],
            "foods": [dict(food, id=food_id) for food_id, food in self.foods.items()],
            "lists": self.lists,
            "groups": self.groups,
        }, ensure_ascii=False, indent=1)
        write_atomic(self.data_file, data.encode("utf-8"))

    def _make_food(self, food_id, name):
        food = {"name": name, "tags": [], "notes": "", "images": [], "global": False}
        self.foods[food_id] = food
        self.food_ids[name] = food_id
        return food

    def _unused(self):
        """Ids of the foods on no list, in no group and not in the Global list."""
        used = {item["food"] for lst in self.lists for item in lst["items"]}
        used.update(item["food"] for group in self.groups for item in group["items"] if "food" in item)
        return [food_id for food_id, food in self.foods.items() if not food["global"] and food_id not in used]

    def _forget(self, food_ids):
        """Delete foods (not from lists; the caller does that); returns their pictures' ids."""
        pictures = [image for food_id in food_ids for image in self.foods[food_id]["images"]]
        for food_id in food_ids:
            del self.food_ids[self.foods.pop(food_id)["name"]]
        return pictures

    def _tidy(self):
        """Save after entries left lists: foods now on no list and not global go, with their pictures."""
        pictures = self._forget(self._unused())
        self.save()
        self._remove_files(pictures)

    def _new_list(self, name, entry_id=None):
        return {"id": entry_id or new_id(), "name": name, "items": []}

    def _new_hue(self):
        used = [tag["hue"] for tag in self.tags.values()]
        counts = {hue: sum(abs((h - hue + 180) % 360 - 180) < 15 for h in used) for hue in HUES}
        least = min(counts.values())
        return secrets.choice([hue for hue, n in counts.items() if n == least])

    # ---- reading ----

    def summary(self):
        """Every list (without items), every group (groups.py), every food's name and tags, and every
        tag: for the lists screen and the suggestions while typing."""
        return {
            "lists": [{"id": lst["id"], "name": lst["name"], "count": len(lst["items"]),
                       "left": sum(not item["checked"] for item in lst["items"])} for lst in self.lists],
            "groups": self.group_summaries(),
            "foods": sorted(({"name": food["name"], "tags": list(food["tags"]), "global": food["global"]}
                            for food in self.foods.values()),
                           key=lambda food: food["name"]),
            "tags": sorted(({"id": tag_id, "name": tag["name"], "hue": tag["hue"]}
                            for tag_id, tag in self.tags.items()), key=lambda tag: tag["name"]),
        }

    def public_food(self, food_id):
        food = self.foods[food_id]
        return {"food": food_id, "name": food["name"], "tags": list(food["tags"]), "notes": food["notes"],
                "images": list(food["images"]), "global": food["global"]}

    def public_item(self, item):
        return dict(self.public_food(item["food"]), id=item["id"], checked=item["checked"], pushed=item["pushed"])

    def public_list(self, list_id):
        """One list with its items, plus the summary."""
        lst = self.find_list(list_id)
        items = [self.public_item(item) for item in lst["items"]]
        return dict(self.summary(), list={"id": lst["id"], "name": lst["name"], "items": items})

    def public_foods(self):
        """The Global list: every global food, plus the summary."""
        items = sorted((dict(self.public_food(food_id), id=food_id)
                        for food_id, food in self.foods.items() if food["global"]),
                       key=lambda item: item["name"])
        return dict(self.summary(), list={"id": "global", "name": "Global", "global": True, "items": items})

    def find_list(self, list_id):
        for lst in self.lists:
            if lst["id"] == list_id:
                return lst
        raise Rejected("That list is gone (someone may have deleted it).", 404)

    def find_food(self, food_id):
        if food_id not in self.foods:
            raise Rejected("That item is gone (someone may have deleted it).", 404)
        return self.foods[food_id]

    def find(self, item_id):
        """(list, entry) for an entry on any list."""
        for lst in self.lists:
            for item in lst["items"]:
                if item["id"] == item_id:
                    return lst, item
        raise Rejected("That item is gone (someone may have removed it).", 404)

    def image_path(self, image_id):
        """The file for a picture some food has, else None."""
        if not ID.match(image_id) or not any(image_id in food["images"] for food in self.foods.values()):
            return None
        return self.images_dir / f"{image_id}.png"

    # ---- lists ----

    def _list_name(self, value, other_than=None):
        name = address_name(value, "list")
        if name.lower() in RESERVED_LIST_NAMES:
            raise Rejected(f"“{name}” is the Global list's address; pick another name.")
        if any(lst["name"].lower() == name.lower() for lst in self.lists if lst is not other_than):
            raise Rejected(f"There's already a list called “{name}”.")
        return name

    def _room_for_list(self):
        if len(self.lists) >= MAX_LISTS:
            raise Rejected(f"There are already {MAX_LISTS} lists.", 507)

    def add_list(self, data):
        self._room_for_list()
        lst = self._new_list(self._list_name(data.get("name")))
        self.lists.append(lst)
        self.save()
        return {"id": lst["id"], "name": lst["name"]}

    def update_list(self, list_id, data):
        lst = self.find_list(list_id)
        if "name" in data:
            lst["name"] = self._list_name(data["name"], other_than=lst)
        self.save()
        return {"id": lst["id"], "name": lst["name"]}

    def delete_list(self, list_id):
        lst = self.find_list(list_id)
        if len(self.lists) == 1:
            raise Rejected("That's the only list; add another one before deleting it.")
        self.lists.remove(lst)
        self._tidy()

    # ---- entries on a list ----

    def add(self, list_id, data):
        """Put a food on a list by name (made if it's new)."""
        lst = self.find_list(list_id)
        if len(lst["items"]) >= MAX_ITEMS:
            raise Rejected(f"The list is full ({MAX_ITEMS} items).", 507)
        food_id = self._food_for_name(data.get("name"), [item["food"] for item in lst["items"]], "on this list")
        item = {"id": new_id(), "food": food_id, "checked": False, "pushed": False}
        lst["items"].append(item)
        self.save()
        return self.public_item(item)

    def _food_for_name(self, value, taken, where):
        """The food called value (made if it's new), refused when it's one of taken (food ids)."""
        name = food_name(value)
        if not name:
            raise Rejected("Give the item a name.")
        food_id = self.food_ids.get(name)
        if food_id is not None and food_id in taken:
            raise Rejected(f"“{name}” is already {where}.", 409)
        if food_id is None:
            if len(self.foods) >= MAX_FOODS:
                raise Rejected(f"There are already {MAX_FOODS} saved items.", 507)
            food_id = new_id()
            self._make_food(food_id, name)
        return food_id

    def update(self, item_id, data):
        """Change an entry: checked and pushed are the entry's own (setting one clears the other); the rest
        goes to its food."""
        _, item = self.find(item_id)
        state = {}
        for key in ("checked", "pushed"):
            if key in data:
                if not isinstance(data[key], bool):
                    raise Rejected(f"Bad {key} value.")
                state[key] = data[key]
        if state.get("checked") and state.get("pushed"):
            raise Rejected("An item can't be checked and pushed at once.")
        self._food_changes(item["food"], data)()
        for key, value in state.items():
            item[key] = value
            if value:
                item["pushed" if key == "checked" else "checked"] = False
        self.save()
        return self.public_item(item)

    def delete(self, item_id):
        """Take an entry off its list (the food stays if it's on another list or global)."""
        lst, item = self.find(item_id)
        lst["items"].remove(item)
        self._tidy()

    def clear(self, list_id, which):
        """Remove the checked items ("checked", which also unpushes the rest) or all of them ("all")."""
        lst = self.find_list(list_id)
        if which not in ("checked", "all"):
            raise Rejected("Bad clear request.")
        before = len(lst["items"])
        lst["items"] = [item for item in lst["items"] if which == "checked" and not item["checked"]]
        for item in lst["items"]:
            item["pushed"] = False
        self._tidy()
        return before - len(lst["items"])

    # ---- foods (everything about an item) ----

    def _food_changes(self, food_id, data):
        """Checks name, tags, notes and global for a food; returns a function
        that applies them, so nothing changes when any of them is refused."""
        food = self.foods[food_id]
        changes = {}
        if "tags" in data:
            changes["tags"] = self._tag_names(data["tags"])
        if "name" in data:
            name = food_name(data["name"])
            if not name:
                raise Rejected("Give the item a name.")
            other = self.food_ids.get(name)
            if other is not None and other != food_id:
                raise Rejected(f"There's already an item called “{name}”.", 409)
            changes["name"] = name
        if "notes" in data:
            changes["notes"] = clean_text(data["notes"], NOTES_MAX, multiline=True, label="The notes")
        if "global" in data:
            if not isinstance(data["global"], bool):
                raise Rejected("Bad global value.")
            if not data["global"] and food["images"]:
                raise Rejected("Items with pictures stay in the Global list.")
            changes["global"] = data["global"]

        def apply():
            if "name" in changes:
                del self.food_ids[food["name"]]
                self.food_ids[changes["name"]] = food_id
            if "tags" in changes:
                changes["tags"] = [self._tag(tag) for tag in changes["tags"]]
            food.update(changes)
        return apply

    def update_food(self, food_id, data):
        """Change a food from the Global list."""
        self.find_food(food_id)
        self._food_changes(food_id, data)()
        result = dict(self.public_food(food_id), id=food_id)
        self._tidy()  # taken out of the Global list while on no list: gone
        return result

    def delete_foods(self, food_ids):
        """Delete foods for good: off every list and group, pictures deleted. Unknown ids are skipped."""
        if not isinstance(food_ids, list) or len(food_ids) > MAX_DELETE:
            raise Rejected("Bad delete request.")
        gone = {food_id for food_id in food_ids if isinstance(food_id, str) and food_id in self.foods}
        pictures = self._forget(gone)
        for lst in self.lists:
            lst["items"] = [item for item in lst["items"] if item["food"] not in gone]
        for group in self.groups:
            group["items"] = [item for item in group["items"] if item.get("food") not in gone]
        self.save()
        self._remove_files(pictures)
        return len(gone)

    def _tag_names(self, value):
        """Checked tag names for a food (nothing is made yet)."""
        if not isinstance(value, list) or len(value) > MAX_TAGS_PER_ITEM * 2:
            raise Rejected("Bad tags.")
        names = []
        for raw in value:
            name = tag_name(raw)
            if name not in names:
                names.append(name)
        if len(names) > MAX_TAGS_PER_ITEM:
            raise Rejected(f"An item can have at most {MAX_TAGS_PER_ITEM} tags.")
        if len(self.tags) + sum(name not in self.tag_ids for name in names) > MAX_TAGS:
            raise Rejected(f"There are already {MAX_TAGS} tags.", 507)
        return names

    def add_tag(self, data):
        """Make a tag from the lists screen (hue 0-359; least used one when not given)."""
        name = tag_name(data.get("name"))
        if name in self.tag_ids:
            raise Rejected(f"There's already a tag called “{name}”.", 409)
        if len(self.tags) >= MAX_TAGS:
            raise Rejected(f"There are already {MAX_TAGS} tags.", 507)
        hue = data.get("hue", self._new_hue())
        if not isinstance(hue, int) or isinstance(hue, bool) or not 0 <= hue < 360:
            raise Rejected("Bad colour.")
        tag_id = self._tag(name)
        self.tags[tag_id]["hue"] = hue
        self.save()
        return dict(self.tags[tag_id], id=tag_id)

    def update_tag(self, tag_id, data):
        """Rename a tag or change its colour (hue 0-359)."""
        if tag_id not in self.tags:
            raise Rejected("That tag is gone.", 404)
        tag = self.tags[tag_id]
        name = tag_name(data["name"]) if "name" in data else tag["name"]
        if self.tag_ids.get(name, tag_id) != tag_id:
            raise Rejected(f"There's already a tag called “{name}”.", 409)
        hue = data.get("hue", tag["hue"])
        if not isinstance(hue, int) or isinstance(hue, bool) or not 0 <= hue < 360:
            raise Rejected("Bad colour.")
        del self.tag_ids[tag["name"]]
        tag.update(name=name, hue=hue)
        self.tag_ids[name] = tag_id
        self.save()
        return dict(tag, id=tag_id)

    def delete_tag(self, tag_id):
        """Delete a tag for good, taking it off every food."""
        if tag_id not in self.tags:
            raise Rejected("That tag is gone.", 404)
        del self.tag_ids[self.tags.pop(tag_id)["name"]]
        for food in self.foods.values():
            if tag_id in food["tags"]:
                food["tags"].remove(tag_id)
        self.save()

    def _tag(self, name):
        """The id of the tag called name, made if it's new."""
        if name not in self.tag_ids:
            tag_id = new_id()
            self.tags[tag_id] = {"name": name, "hue": self._new_hue()}
            self.tag_ids[name] = tag_id
        return self.tag_ids[name]

    # ---- pictures (on foods) ----

    def add_image(self, food_id, body, now=None):
        food = self.find_food(food_id)
        if len(food["images"]) >= MAX_IMAGES_PER_ITEM:
            raise Rejected(f"An item can have at most {MAX_IMAGES_PER_ITEM} pictures.", 507)
        if sum(len(f["images"]) for f in self.foods.values()) >= MAX_IMAGES:
            raise Rejected(f"There are already {MAX_IMAGES} pictures; remove some first.", 507)
        now = time.monotonic() if now is None else now
        while self.uploads and now - self.uploads[0] > 3600:
            self.uploads.popleft()
        if len(self.uploads) >= UPLOADS_PER_HOUR:
            raise Rejected("Too many pictures uploaded in the last hour; try again later.", 429)
        try:
            png = images.encode_png(*images.parse_rgb(body))
        except images.BadImage as error:
            raise Rejected(str(error)) from None
        if self.data_bytes + len(png) > MAX_DATA_BYTES:
            raise Rejected("There's no room for more pictures; remove some first.", 507)
        self.uploads.append(now)
        image_id = new_id()
        write_atomic(self.images_dir / f"{image_id}.png", png)
        self.data_bytes += len(png)
        food["images"].append(image_id)
        food["global"] = True  # foods with pictures are always in the Global list
        self.save()
        return image_id

    def delete_image(self, food_id, image_id):
        food = self.find_food(food_id)
        if image_id not in food["images"]:
            raise Rejected("That picture is gone.", 404)
        food["images"].remove(image_id)
        self.save()
        self._remove_files([image_id])

    def _remove_files(self, image_ids):
        for image_id in image_ids:
            path = self.images_dir / f"{image_id}.png"
            try:
                self.data_bytes -= path.stat().st_size
                path.unlink()
            except FileNotFoundError:
                pass
