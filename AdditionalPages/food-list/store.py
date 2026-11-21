"""Food list: several shopping lists plus every item ever added, kept in <data>/lists.json, with
the pictures in <data>/images/<id>.png.

The data:
- foods: every item ever added, kept forever (removing it from a list keeps it) so the page can
  suggest it when adding and edit it in the Global list: {id, name, tags: [tag id], notes, unit,
  amount, images: [image id]}. Everything about an item lives here, once, whichever list it's on,
  except how many to get: amount here is only the default a list entry starts with.
  Names are lowercase (whatever is typed is lowercased; symbols, spaces and digits are fine) and
  unique: adding a name that's already a food reuses it, and a rename to another food's name is
  refused. Deleting a food (only from the Global list) takes it off every list and deletes its
  pictures.
- tags: every tag ever made ({id, name, hue}), kept forever. Names are lowercase letters and
  single spaces only, and unique; hue (0-359) is the tag's colour, picked at random when it's made
  among the hues used least so far. Setting an item's tags by name makes any new ones. A tag's
  name and hue can be changed (update_tag) from the lists screen.
- lists: {id, name, template, copy_of, items}; list names are unique ignoring case and there is
  always at least one. An entry on a list is {id, food, checked, amount}; a food is on a list at
  most once. A template list can be copied: the copy gets the same foods with the template's
  amounts, all unchecked, isn't a template itself, and has copy_of = {id, name} of the template
  (the name follows renames of the template, and stays after it's deleted).
The page's Global list isn't stored: it's every food (public_foods).
Amounts are numbers above 0 (at most AMOUNT_MAX, rounded to 2 decimals) or None for "not set".

Older data is moved over when loaded (and saved again once): list.json (one list:
{"items": [{id, name, notes, checked, images}]}) becomes the list "Food list" when lists.json
doesn't exist yet (list.json itself is left as it was), and notes/pictures that were kept on list
entries move to their food (notes joined, pictures up to the limit).

Nothing from the browser is trusted. Every value is checked here before it's kept:
- text: must be a string, normalised (NFC), control/format/private/unassigned characters dropped
  (newlines kept in notes), trimmed, and rejected when longer than the limit;
- checked and template: must be exactly true or false; amounts: numbers in range or null;
- ids are made here (random hex) and the browser can only name existing ones; file names are
  only ever built from those ids, never from anything the browser sends;
- images come in as raw RGB and go out as a PNG written by images.py.
Limits (lists, items per list, foods, tags, pictures per item and in all, total data size, uploads
per hour) keep a stranger who finds the page from filling the disk. lists.json is checked the
same way when it's loaded, and image files nobody refers to are removed then.

Files are written to a temporary name and renamed, so a crash never leaves a half-written file.
"""

import json
import math
import os
import re
import secrets
import time
import unicodedata
from collections import deque
from pathlib import Path

import images

NAME_MAX = 80
LIST_NAME_MAX = 40
TAG_NAME_MAX = 24
NOTES_MAX = 500
UNIT_MAX = 16
AMOUNT_MAX = 9999
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
DEFAULT_LIST = "Food list"

ID = re.compile(r"^[0-9a-f]{16}$")
KEEP_FORMAT = {"‍"}  # zero-width joiner: needed by combined emoji


class Rejected(Exception):
    """A request we refuse; the message is shown to the user."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def new_id():
    return secrets.token_hex(8)


def clean_text(value, limit, multiline=False, label="Text"):
    """Return safe text from an untrusted value, or raise Rejected."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise Rejected(f"{label} must be text.")
    if len(value) > limit * 4:
        raise Rejected(f"{label} is too long (at most {limit} characters).")
    kept = []
    for ch in unicodedata.normalize("NFC", value):
        if ch == "\n" and multiline:
            kept.append(ch)
        elif ch in "\t\r\n":
            kept.append(" ")
        elif unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn") and ch not in KEEP_FORMAT:
            continue
        else:
            kept.append(ch)
    text = "".join(kept)
    if multiline:
        text = re.sub(r"\n{3,}", "\n\n", "\n".join(line.strip() for line in text.split("\n")))
    else:
        text = re.sub(r" {2,}", " ", text)
    text = text.strip()
    if len(text) > limit:
        raise Rejected(f"{label} is too long (at most {limit} characters).")
    return text


def food_name(value):
    """An item name as it's kept: cleaned text, lowercase."""
    return clean_text(value, NAME_MAX, label="The name").lower()[:NAME_MAX]


def tag_name(value):
    """A tag name as it's kept: lowercase letters and single spaces, or Rejected."""
    name = clean_text(value, TAG_NAME_MAX, label="A tag").lower()[:TAG_NAME_MAX]
    if not name:
        raise Rejected("Give the tag a name.")
    if not all(ch.isalpha() or ch == " " for ch in name):
        raise Rejected("Tags can only have letters and spaces.")
    return name


def clean_amount(value):
    """An amount as it's kept: a number above 0 (2 decimals at most) or None, or Rejected."""
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise Rejected("The amount must be a number.")
    if not 0 <= value <= AMOUNT_MAX:
        raise Rejected(f"The amount must be between 0 and {AMOUNT_MAX}.")
    value = round(float(value), 2)
    if value == 0:
        return None
    return int(value) if value.is_integer() else value


def saved_amount(value):
    try:
        return clean_amount(value)
    except Rejected:
        return None


def free_name(name, taken, limit=NAME_MAX):
    """name, or name with " 2", " 3"... added so its lowercase isn't in taken (when loading bad data)."""
    n = 1
    candidate = name
    while candidate.lower() in taken:
        n += 1
        suffix = f" {n}"
        candidate = name[:limit - len(suffix)] + suffix
    return candidate


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


def has_id(entry):
    return isinstance(entry, dict) and isinstance(entry.get("id"), str) and bool(ID.match(entry["id"]))


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.images_dir = self.folder / "images"
        self.data_file = self.folder / "lists.json"
        self.old_file = self.folder / "list.json"  # before there were several lists
        self.lists = []
        self.foods = {}     # food id -> {"name", "tags", "notes", "unit", "amount", "images"}
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
            food["unit"] = clean_text(entry.get("unit"), UNIT_MAX)
        except Rejected:
            pass
        food["amount"] = saved_amount(entry.get("amount"))
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
        taken = {lst["name"].lower() for lst in self.lists}
        name = free_name(clean_text(entry.get("name"), LIST_NAME_MAX) or "List", taken, LIST_NAME_MAX)
        lst = self._new_list(name, template=entry.get("template") is True, entry_id=entry["id"])
        source = entry.get("copy_of")
        if has_id(source):
            lst["copy_of"] = {"id": source["id"], "name": clean_text(source.get("name"), LIST_NAME_MAX) or "?"}
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
        return {"id": entry["id"], "food": food_id, "checked": entry.get("checked") is True,
                "amount": saved_amount(entry.get("amount"))}

    def save(self):
        data = json.dumps({
            "tags": [dict(tag, id=tag_id) for tag_id, tag in self.tags.items()],
            "foods": [dict(food, id=food_id) for food_id, food in self.foods.items()],
            "lists": self.lists,
        }, ensure_ascii=False, indent=1)
        write_atomic(self.data_file, data.encode("utf-8"))

    def _make_food(self, food_id, name):
        food = {"name": name, "tags": [], "notes": "", "unit": "", "amount": None, "images": []}
        self.foods[food_id] = food
        self.food_ids[name] = food_id
        return food

    def _new_list(self, name, template=False, entry_id=None):
        return {"id": entry_id or new_id(), "name": name, "template": template, "copy_of": None, "items": []}

    def _new_hue(self):
        used = [tag["hue"] for tag in self.tags.values()]
        counts = {hue: sum(abs((h - hue + 180) % 360 - 180) < 15 for h in used) for hue in HUES}
        least = min(counts.values())
        return secrets.choice([hue for hue, n in counts.items() if n == least])

    # ---- reading ----

    def summary(self):
        """Every list (without items), every food's name and tags, and every tag: for the lists screen
        and the suggestions while typing."""
        return {
            "lists": [{"id": lst["id"], "name": lst["name"], "template": lst["template"],
                       "copy_of": lst["copy_of"]["name"] if lst["copy_of"] else None,
                       "count": len(lst["items"]), "left": sum(not item["checked"] for item in lst["items"])}
                      for lst in self.lists],
            "foods": sorted(({"name": food["name"], "tags": list(food["tags"])} for food in self.foods.values()),
                           key=lambda food: food["name"]),
            "tags": sorted(({"id": tag_id, "name": tag["name"], "hue": tag["hue"]}
                            for tag_id, tag in self.tags.items()), key=lambda tag: tag["name"]),
        }

    def public_food(self, food_id):
        food = self.foods[food_id]
        return {"food": food_id, "name": food["name"], "tags": list(food["tags"]), "notes": food["notes"],
                "unit": food["unit"], "images": list(food["images"])}

    def public_item(self, item):
        return dict(self.public_food(item["food"]), id=item["id"], amount=item["amount"], checked=item["checked"])

    def public_list(self, list_id):
        """One list with its items, plus the summary."""
        lst = self.find_list(list_id)
        items = [self.public_item(item) for item in lst["items"]]
        return dict(self.summary(), list={"id": lst["id"], "name": lst["name"], "template": lst["template"],
                                          "copy_of": lst["copy_of"]["name"] if lst["copy_of"] else None,
                                          "items": items})

    def public_foods(self):
        """The Global list: every food (amount = its default) and the lists holding it, plus the summary."""
        holders = {}
        for lst in self.lists:
            for item in lst["items"]:
                holders.setdefault(item["food"], []).append(lst["name"])
        items = sorted((dict(self.public_food(food_id), id=food_id, amount=food["amount"],
                             lists=holders.get(food_id, [])) for food_id, food in self.foods.items()),
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
        name = clean_text(value, LIST_NAME_MAX, label="The list name")
        if not name:
            raise Rejected("Give the list a name.")
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
        name = self._list_name(data["name"], other_than=lst) if "name" in data else lst["name"]
        template = data.get("template", lst["template"])
        if not isinstance(template, bool):
            raise Rejected("Bad template value.")
        lst["name"], lst["template"] = name, template
        for other in self.lists:
            if other["copy_of"] and other["copy_of"]["id"] == lst["id"]:
                other["copy_of"]["name"] = name
        self.save()
        return {"id": lst["id"], "name": lst["name"], "template": lst["template"]}

    def copy_list(self, list_id, data):
        """A new list holding a template's items with its amounts, all unchecked."""
        source = self.find_list(list_id)
        if not source["template"]:
            raise Rejected("Only template lists can be copied.")
        self._room_for_list()
        lst = self._new_list(self._list_name(data.get("name")))
        lst["copy_of"] = {"id": source["id"], "name": source["name"]}
        lst["items"] = [{"id": new_id(), "food": item["food"], "checked": False, "amount": item["amount"]}
                        for item in source["items"]]
        self.lists.append(lst)
        self.save()
        return {"id": lst["id"], "name": lst["name"]}

    def delete_list(self, list_id):
        lst = self.find_list(list_id)
        if len(self.lists) == 1:
            raise Rejected("That's the only list; add another one before deleting it.")
        self.lists.remove(lst)
        self.save()

    # ---- entries on a list ----

    def add(self, list_id, data):
        """Put a food on a list by name (made if it's new), with the food's default amount."""
        lst = self.find_list(list_id)
        if len(lst["items"]) >= MAX_ITEMS:
            raise Rejected(f"The list is full ({MAX_ITEMS} items).", 507)
        name = food_name(data.get("name"))
        if not name:
            raise Rejected("Give the item a name.")
        food_id = self.food_ids.get(name)
        if food_id is not None and any(item["food"] == food_id for item in lst["items"]):
            raise Rejected(f"“{name}” is already on this list.", 409)
        if food_id is None:
            if len(self.foods) >= MAX_FOODS:
                raise Rejected(f"There are already {MAX_FOODS} saved items.", 507)
            food_id = new_id()
            self._make_food(food_id, name)
        item = {"id": new_id(), "food": food_id, "checked": False, "amount": self.foods[food_id]["amount"]}
        lst["items"].append(item)
        self.save()
        return self.public_item(item)

    def update(self, item_id, data):
        """Change an entry: checked and amount are the entry's own; the rest goes to its food."""
        _, item = self.find(item_id)
        checked = item["checked"]
        if "checked" in data:
            checked = data["checked"]
            if not isinstance(checked, bool):
                raise Rejected("Bad checked value.")
        amount = clean_amount(data["amount"]) if "amount" in data else item["amount"]
        apply_food = self._food_changes(item["food"], data)
        apply_food()
        item["checked"], item["amount"] = checked, amount
        self.save()
        return self.public_item(item)

    def delete(self, item_id):
        """Take an entry off its list (the food stays)."""
        lst, item = self.find(item_id)
        lst["items"].remove(item)
        self.save()

    def clear(self, list_id, which):
        lst = self.find_list(list_id)
        if which not in ("checked", "all"):
            raise Rejected("Bad clear request.")
        before = len(lst["items"])
        lst["items"] = [item for item in lst["items"] if which == "checked" and not item["checked"]]
        self.save()
        return before - len(lst["items"])

    # ---- foods (everything about an item) ----

    def _food_changes(self, food_id, data, default_amount=False):
        """Checks name, tags, notes, unit (and the default amount) for a food; returns a function
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
        if "unit" in data:
            changes["unit"] = clean_text(data["unit"], UNIT_MAX, label="The unit")
        if default_amount and "amount" in data:
            changes["amount"] = clean_amount(data["amount"])

        def apply():
            if "name" in changes:
                del self.food_ids[food["name"]]
                self.food_ids[changes["name"]] = food_id
            if "tags" in changes:
                changes["tags"] = [self._tag(tag) for tag in changes["tags"]]
            food.update(changes)
        return apply

    def update_food(self, food_id, data):
        """Change a food from the Global list (amount there is the default for new entries)."""
        self.find_food(food_id)
        self._food_changes(food_id, data, default_amount=True)()
        self.save()
        return dict(self.public_food(food_id), id=food_id, amount=self.foods[food_id]["amount"])

    def delete_foods(self, food_ids):
        """Delete foods for good: off every list, pictures deleted. Unknown ids are skipped."""
        if not isinstance(food_ids, list) or len(food_ids) > MAX_DELETE:
            raise Rejected("Bad delete request.")
        gone = {food_id for food_id in food_ids if isinstance(food_id, str) and food_id in self.foods}
        pictures = [image for food_id in gone for image in self.foods[food_id]["images"]]
        for food_id in gone:
            del self.food_ids[self.foods.pop(food_id)["name"]]
        for lst in self.lists:
            lst["items"] = [item for item in lst["items"] if item["food"] not in gone]
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
