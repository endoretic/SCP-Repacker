from __future__ import annotations

import copy
import posixpath
from collections import OrderedDict
from typing import Any, Dict, Iterable, Iterator, List, Sequence, Tuple

from .archive import dump_json, load_json

RESOURCE_CATEGORIES = ["skins", "backgrounds", "effects", "particles"]
LEVEL_CATEGORY = "levels"
ENGINE_CATEGORY = "engines"
RESOURCE_OVERRIDE_FIELDS: Sequence[Tuple[str, str]] = (
    ("skin", "useSkin"),
    ("background", "useBackground"),
    ("effect", "useEffect"),
    ("particle", "useParticle"),
)

def item_from_doc(doc: Any) -> Dict[str, Any]:
    if isinstance(doc, dict) and isinstance(doc.get("item"), dict):
        return doc["item"]
    if isinstance(doc, dict):
        return doc
    raise ValueError("JSON document is not an object or {item: object}")


def wrap_like(original_doc: Any, item: Dict[str, Any]) -> Any:
    if isinstance(original_doc, dict) and isinstance(original_doc.get("item"), dict):
        new_doc = dict(original_doc)
        new_doc["item"] = item
        return new_doc
    return item


def category_item_paths(entries: Dict[str, bytes], category: str) -> List[str]:
    prefix = f"sonolus/{category}/"
    skip = {f"sonolus/{category}/list", f"sonolus/{category}/info"}
    return [p for p in entries if p.startswith(prefix) and p not in skip]


def list_items(entries: Dict[str, bytes], category: str) -> List[Dict[str, Any]]:
    doc = load_json(entries, f"sonolus/{category}/list", {"pageCount": 1, "items": []})
    if not isinstance(doc, dict):
        return []
    items = doc.get("items", [])
    return items if isinstance(items, list) else []


def item_key(item: Dict[str, Any]) -> Tuple[str, str]:
    return (str(item.get("source", "")), str(item.get("name", "")))


def merge_key(item: Dict[str, Any]) -> Tuple[str, ...]:
    name = str(item.get("name", ""))
    if name:
        return (name,)
    return (str(item.get("source", "")), name)


def merge_item_lists(*lists: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: "OrderedDict[Tuple[str, ...], Dict[str, Any]]" = OrderedDict()
    for items in lists:
        for item in items:
            if not isinstance(item, dict):
                continue
            key = merge_key(item)
            if not any(key):
                continue
            merged[key] = item
    return list(merged.values())


def build_list_doc(items: List[Dict[str, Any]], original_doc: Any = None) -> Dict[str, Any]:
    doc = dict(original_doc) if isinstance(original_doc, dict) else {}
    doc["pageCount"] = 1
    doc["items"] = items
    return doc


def build_sections_doc(item_type: str, items: List[Dict[str, Any]], original_doc: Any = None) -> Dict[str, Any]:
    if isinstance(original_doc, dict) and isinstance(original_doc.get("sections"), list):
        doc = dict(original_doc)
        sections: List[Any] = []
        inserted = False
        for section in original_doc["sections"]:
            if isinstance(section, dict) and section.get("itemType") == item_type:
                new_section = dict(section)
                new_section["items"] = items if not inserted else []
                inserted = True
                sections.append(new_section)
            else:
                sections.append(section)
        if not inserted:
            sections.append({"itemType": item_type, "title": "#NEWEST", "items": items})
        doc["sections"] = sections
        return doc

    return {"sections": [{"itemType": item_type, "title": "#NEWEST", "items": items}]}


def extract_engine_item(resource_entries: Dict[str, bytes], engine_name: str) -> Dict[str, Any]:
    path = f"sonolus/engines/{engine_name}"
    doc = load_json(resource_entries, path)
    if doc is None:
        available = [posixpath.basename(p) for p in category_item_paths(resource_entries, "engines")]
        raise SystemExit(
            f"Engine '{engine_name}' not found in resource package. Available: {', '.join(available) or '(none)'}"
        )
    return item_from_doc(doc)


def print_available_engines(resource_entries: Dict[str, bytes]) -> None:
    paths = category_item_paths(resource_entries, ENGINE_CATEGORY)
    if not paths:
        print("No engines found in resource package.")
        return
    print("Available engines in resource package:")
    for p in paths:
        try:
            item = item_from_doc(load_json(resource_entries, p))
            print(f"  {item.get('name')}  |  {item.get('title')}  |  source={item.get('source')}")
        except Exception:
            print(f"  {posixpath.basename(p)}  |  (failed to read item)")


def patch_level_item(item: Dict[str, Any], target_engine: Dict[str, Any], replace_defaults: bool) -> Dict[str, Any]:
    patched = copy.deepcopy(item)
    patched["engine"] = copy.deepcopy(target_engine)

    if replace_defaults:
        # Force levels back onto the selected engine defaults so old custom
        # overrides do not keep pointing at resources from the previous engine.
        for resource_key, usage_key in RESOURCE_OVERRIDE_FIELDS:
            engine_resource = target_engine.get(resource_key)
            if isinstance(engine_resource, dict) and engine_resource:
                patched[usage_key] = {"useDefault": True}
                if resource_key in patched:
                    patched[resource_key] = copy.deepcopy(engine_resource)

    return patched


def patch_level_sections_doc(doc: Any, target_engine: Dict[str, Any], replace_defaults: bool) -> Tuple[Any, int]:
    if not (isinstance(doc, dict) and isinstance(doc.get("sections"), list)):
        return doc, 0

    new_doc = dict(doc)
    new_sections: List[Any] = []
    patched_count = 0
    for section in doc["sections"]:
        if isinstance(section, dict) and isinstance(section.get("items"), list):
            new_section = dict(section)
            patched_items, count = patch_level_docs(section["items"], target_engine, replace_defaults)
            new_section["items"] = patched_items
            patched_count += count
            new_sections.append(new_section)
        else:
            new_sections.append(section)
    new_doc["sections"] = new_sections
    return new_doc, patched_count


def patch_level_doc(doc: Any, target_engine: Dict[str, Any], replace_defaults: bool) -> Tuple[Any, int]:
    patched_doc = doc
    patched_count = 0

    if isinstance(patched_doc, dict) and isinstance(patched_doc.get("item"), dict):
        new_doc = dict(patched_doc)
        new_doc["item"] = patch_level_item(patched_doc["item"], target_engine, replace_defaults)
        patched_doc = new_doc
        patched_count += 1
    elif isinstance(patched_doc, dict) and "engine" in patched_doc:
        patched_doc = patch_level_item(patched_doc, target_engine, replace_defaults)
        patched_count += 1

    patched_doc, section_count = patch_level_sections_doc(patched_doc, target_engine, replace_defaults)
    return patched_doc, patched_count + section_count


def patch_level_docs(items: Sequence[Any], target_engine: Dict[str, Any], replace_defaults: bool) -> Tuple[List[Any], int]:
    patched_items: List[Any] = []
    patched_count = 0
    for item in items:
        patched_item, changed = patch_level_doc(item, target_engine, replace_defaults)
        patched_items.append(patched_item)
        patched_count += changed
    return patched_items, patched_count


def patch_levels(entries: "OrderedDict[str, bytes]", target_engine: Dict[str, Any], replace_defaults: bool) -> Dict[str, int]:
    counts = {"level_files": 0, "embedded_level_items": 0, "list_items": 0, "info_items": 0}

    for path in list(category_item_paths(entries, LEVEL_CATEGORY)):
        doc = load_json(entries, path)
        patched_doc, changed = patch_level_doc(doc, target_engine, replace_defaults)
        if changed:
            entries[path] = dump_json(patched_doc)
            counts["level_files"] += 1
            counts["embedded_level_items"] += changed

    list_path = "sonolus/levels/list"
    list_doc = load_json(entries, list_path, None)
    if isinstance(list_doc, dict) and isinstance(list_doc.get("items"), list):
        patched_items, count = patch_level_docs(list_doc["items"], target_engine, replace_defaults)
        new_list_doc = dict(list_doc)
        new_list_doc["items"] = patched_items
        entries[list_path] = dump_json(new_list_doc)
        counts["list_items"] = count

    info_path = "sonolus/levels/info"
    info_doc = load_json(entries, info_path, None)
    if isinstance(info_doc, dict) and isinstance(info_doc.get("sections"), list):
        new_info_doc, patched_info_items = patch_level_sections_doc(info_doc, target_engine, replace_defaults)
        entries[info_path] = dump_json(new_info_doc)
        counts["info_items"] = patched_info_items

    return counts


def remove_category(entries: "OrderedDict[str, bytes]", category: str) -> None:
    prefix = f"sonolus/{category}/"
    for path in list(entries.keys()):
        if path.startswith(prefix):
            del entries[path]


def merge_resource_category(
    output: "OrderedDict[str, bytes]",
    original_target: Dict[str, bytes],
    resource: Dict[str, bytes],
    category: str,
) -> int:
    # Copy all item files from target and resource, resource wins if paths collide.
    for src in (original_target, resource):
        for path, data in src.items():
            if path.startswith(f"sonolus/{category}/") and not path.endswith("/list"):
                output[path] = data

    list_path = f"sonolus/{category}/list"
    target_list_doc = load_json(original_target, list_path, None)
    resource_list_doc = load_json(resource, list_path, None)
    merged = merge_item_lists(list_items(original_target, category), list_items(resource, category))
    output[list_path] = dump_json(build_list_doc(merged, target_list_doc or resource_list_doc))

    # Prefer resource info if available; otherwise keep target info.
    info_path = f"sonolus/{category}/info"
    if info_path in resource:
        output[info_path] = resource[info_path]
    elif info_path in original_target:
        output[info_path] = original_target[info_path]

    return len(merged)


def install_engines(
    output: "OrderedDict[str, bytes]",
    resource: Dict[str, bytes],
    selected_engine_name: str,
    only_selected: bool,
    keep_old_engines: bool,
    original_target: Dict[str, bytes],
) -> int:
    if not keep_old_engines:
        remove_category(output, ENGINE_CATEGORY)

    if keep_old_engines:
        for path, data in original_target.items():
            if path.startswith(f"sonolus/{ENGINE_CATEGORY}/"):
                output[path] = data

    selected_path = f"sonolus/{ENGINE_CATEGORY}/{selected_engine_name}"
    target_list_doc = load_json(original_target, f"sonolus/{ENGINE_CATEGORY}/list", None)
    resource_list_doc = load_json(resource, f"sonolus/{ENGINE_CATEGORY}/list", None)
    merged_engine_items: List[Dict[str, Any]] = list_items(original_target, ENGINE_CATEGORY) if keep_old_engines else []

    if only_selected:
        if selected_path not in resource:
            raise SystemExit(f"Selected engine item file missing: {selected_path}")
        output[selected_path] = resource[selected_path]
        selected_item = item_from_doc(load_json(resource, selected_path))
        merged_engine_items = merge_item_lists(merged_engine_items, [selected_item])
    else:
        resource_engine_items = []
        for path in category_item_paths(resource, ENGINE_CATEGORY):
            output[path] = resource[path]
            try:
                resource_engine_items.append(item_from_doc(load_json(resource, path)))
            except Exception:
                pass
        merged_engine_items = merge_item_lists(merged_engine_items, resource_engine_items)

    output[f"sonolus/{ENGINE_CATEGORY}/list"] = dump_json(build_list_doc(merged_engine_items, resource_list_doc or target_list_doc))

    info_path = f"sonolus/{ENGINE_CATEGORY}/info"
    info_template = load_json(resource, info_path, None)
    if info_template is None:
        info_template = load_json(original_target, info_path, None)
    output[info_path] = dump_json(build_sections_doc("engine", merged_engine_items, info_template))

    return len(merged_engine_items)


def iter_level_metadata_items(entries: Dict[str, bytes]) -> Iterator[Tuple[str, Dict[str, Any]]]:
    for path in category_item_paths(entries, LEVEL_CATEGORY):
        doc = load_json(entries, path, None)
        if doc is None:
            continue
        item = item_from_doc(doc)
        if "engine" in item:
            yield path, item
        yield from iter_level_section_items(doc, f"{path}.sections")

    list_doc = load_json(entries, "sonolus/levels/list", None)
    if isinstance(list_doc, dict) and isinstance(list_doc.get("items"), list):
        for index, item in enumerate(list_doc["items"]):
            if isinstance(item, dict) and "engine" in item:
                yield f"sonolus/levels/list[{index}]", item

    info_doc = load_json(entries, "sonolus/levels/info", None)
    yield from iter_level_section_items(info_doc, "sonolus/levels/info")


def iter_level_section_items(doc: Any, prefix: str) -> Iterator[Tuple[str, Dict[str, Any]]]:
    if not (isinstance(doc, dict) and isinstance(doc.get("sections"), list)):
        return

    for section_index, section in enumerate(doc["sections"]):
        if not (isinstance(section, dict) and isinstance(section.get("items"), list)):
            continue
        for item_index, item in enumerate(section["items"]):
            if isinstance(item, dict) and "engine" in item:
                location = f"{prefix}[{section_index}][{item_index}]"
                yield location, item
                yield from iter_level_section_items(item, f"{location}.sections")


def summarize_level_engines(entries: Dict[str, bytes]) -> List[Dict[str, Any]]:
    seen: "OrderedDict[Tuple[str, str], Dict[str, Any]]" = OrderedDict()
    for _, item in iter_level_metadata_items(entries):
        engine = item.get("engine")
        if isinstance(engine, dict):
            seen[item_key(engine)] = engine
    return list(seen.values())


def validate_level_engine_consistency(
    entries: Dict[str, bytes],
    target_engine: Dict[str, Any],
    replace_defaults: bool,
) -> Tuple[List[str], List[str]]:
    expected_engine_key = item_key(target_engine)
    mismatches: List[str] = []
    default_usage_warnings: List[str] = []

    for location, item in iter_level_metadata_items(entries):
        engine = item.get("engine")
        if not isinstance(engine, dict) or item_key(engine) != expected_engine_key:
            mismatches.append(location)

        if replace_defaults:
            for resource_key, usage_key in RESOURCE_OVERRIDE_FIELDS:
                engine_resource = target_engine.get(resource_key)
                if isinstance(engine_resource, dict) and engine_resource:
                    usage = item.get(usage_key)
                    if not (isinstance(usage, dict) and usage.get("useDefault") is True):
                        default_usage_warnings.append(f"{location} -> {usage_key}")

    return mismatches, default_usage_warnings

