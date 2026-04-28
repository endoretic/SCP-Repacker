from __future__ import annotations

import argparse
import copy
import json
import os
import posixpath
import zipfile
from collections import OrderedDict
from typing import Any, Dict, Iterable, Iterator, List, Sequence, Tuple

RESOURCE_CATEGORIES = ["skins", "backgrounds", "effects", "particles"]
LEVEL_CATEGORY = "levels"
ENGINE_CATEGORY = "engines"
RESOURCE_OVERRIDE_FIELDS: Sequence[Tuple[str, str]] = (
    ("skin", "useSkin"),
    ("background", "useBackground"),
    ("effect", "useEffect"),
    ("particle", "useParticle"),
)


def is_json_like_path(path: str) -> bool:
    # Sonolus package files often do not have .json extensions.
    parts = path.split("/")
    return len(parts) >= 2 and parts[0] == "sonolus" and parts[1] not in {"repository"}


def read_zip(path: str) -> "OrderedDict[str, bytes]":
    entries: "OrderedDict[str, bytes]" = OrderedDict()
    with zipfile.ZipFile(path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = info.filename.replace("\\", "/")
            entries[name] = zf.read(info)
    return entries


def write_zip(path: str, entries: "OrderedDict[str, bytes]") -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)


def load_json(entries: Dict[str, bytes], path: str, default: Any = None) -> Any:
    data = entries.get(path)
    if data is None:
        return default
    try:
        return json.loads(data.decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"Failed to parse JSON entry {path}: {e}") from e


def dump_json(obj: Any) -> bytes:
    # Compact JSON; Sonolus accepts no-pretty formatting.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


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


def copy_repository(target: "OrderedDict[str, bytes]", source: Dict[str, bytes]) -> int:
    copied = 0
    for path, data in source.items():
        if path.startswith("sonolus/repository/"):
            if target.get(path) != data:
                copied += 1
            target[path] = data
    return copied


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


def iter_repository_paths(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        url = value.get("url")
        if isinstance(url, str) and url.startswith("/sonolus/repository/"):
            yield url.lstrip("/")
        for nested in value.values():
            yield from iter_repository_paths(nested)
        return

    if isinstance(value, list):
        for nested in value:
            yield from iter_repository_paths(nested)


def validate_repository_references(entries: Dict[str, bytes]) -> List[str]:
    missing: List[str] = []
    seen_missing = set()
    repository_entries = {path for path in entries if path.startswith("sonolus/repository/")}

    for path in entries:
        if not is_json_like_path(path):
            continue
        try:
            doc = load_json(entries, path, None)
        except RuntimeError:
            continue
        if doc is None:
            continue
        for repo_path in iter_repository_paths(doc):
            if repo_path not in repository_entries and repo_path not in seen_missing:
                seen_missing.add(repo_path)
                missing.append(repo_path)

    return missing


def print_engine_summary(label: str, engines: Sequence[Dict[str, Any]]) -> None:
    print(label)
    if not engines:
        print("  (none)")
        return
    for engine in engines:
        print(f"  {engine.get('name')} | {engine.get('title')} | source={engine.get('source')}")


def print_validation_summary(label: str, items: Sequence[str]) -> None:
    print(label)
    if not items:
        print("  none")
        return
    for item in items[:10]:
        print(f"  {item}")
    if len(items) > 10:
        print(f"  ... and {len(items) - 10} more")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Repack Sonolus .scp levels to use an engine from a resource .scp and merge selectable resources."
    )
    ap.add_argument("levels_scp", help="Input .scp containing levels to patch")
    ap.add_argument("resource_scp", help="Resource .scp containing target engines/resources")
    ap.add_argument("output_scp", help="Output .scp path")
    ap.add_argument("--engine", help="Target engine item name, e.g. rush or NextRUSH_P")
    ap.add_argument("--list-engines", action="store_true", help="List engines in the resource .scp and exit")
    ap.add_argument(
        "--no-replace-defaults",
        action="store_true",
        help="Only replace level.engine; keep each level's original skin/background/effect/particle defaults",
    )
    ap.add_argument(
        "--only-selected-engine",
        action="store_true",
        help="Include only the selected engine in sonolus/engines instead of all engines from the resource package",
    )
    ap.add_argument(
        "--keep-old-engines",
        action="store_true",
        help="Keep old engines from the levels package too. Default removes old engines and uses resource package engines.",
    )
    args = ap.parse_args()

    target_entries = read_zip(args.levels_scp)
    resource_entries = read_zip(args.resource_scp)

    if args.list_engines:
        print_available_engines(resource_entries)
        return 0

    if not args.engine:
        print_available_engines(resource_entries)
        raise SystemExit("\nPlease choose one with --engine <name>.")

    source_engines = summarize_level_engines(target_entries)
    target_engine = extract_engine_item(resource_entries, args.engine)

    # Start with the original levels package, then modify/merge.
    output: "OrderedDict[str, bytes]" = OrderedDict(target_entries)

    replace_defaults = not args.no_replace_defaults
    patch_counts = patch_levels(output, target_engine, replace_defaults=replace_defaults)

    # Merge repository files. Target first, resource second.
    copied_target_repository = copy_repository(output, target_entries)
    copied_resource_repository = copy_repository(output, resource_entries)

    # Engines: use resource package engines, selected by user for level patching.
    merged_engine_count = install_engines(
        output,
        resource_entries,
        args.engine,
        only_selected=args.only_selected_engine,
        keep_old_engines=args.keep_old_engines,
        original_target=target_entries,
    )

    # Visual resources: merge old + resource package.
    merged_category_counts: Dict[str, int] = {}
    for category in RESOURCE_CATEGORIES:
        merged_category_counts[category] = merge_resource_category(output, target_entries, resource_entries, category)

    # Prefer resource top-level info only when target lacks it; preserve target collection metadata by default.
    for path in ["sonolus/package", "sonolus/info"]:
        if path not in output and path in resource_entries:
            output[path] = resource_entries[path]

    engine_mismatches, default_usage_warnings = validate_level_engine_consistency(
        output,
        target_engine,
        replace_defaults=replace_defaults,
    )
    missing_repository_files = validate_repository_references(output)

    os.makedirs(os.path.dirname(os.path.abspath(args.output_scp)) or ".", exist_ok=True)
    write_zip(args.output_scp, output)

    print(f"Done: wrote {args.output_scp}")
    print(f"Selected engine: {target_engine.get('name')} ({target_engine.get('title')})")
    print_engine_summary("Detected level engines before patch:", source_engines)
    print(f"Rewrote level detail files: {patch_counts['level_files']}")
    print(f"Rewrote levels/list items: {patch_counts['list_items']}")
    print(f"Rewrote levels/info items: {patch_counts['info_items']}")
    print(f"Merged {ENGINE_CATEGORY} list items: {merged_engine_count}")
    for category in RESOURCE_CATEGORIES:
        print(f"Merged {category} list items: {merged_category_counts[category]}")
    print(f"Copied repository files from target package: {copied_target_repository}")
    print(f"Copied repository files from resource package: {copied_resource_repository}")
    print_validation_summary("Validation engine mismatches:", engine_mismatches)
    print_validation_summary("Validation default-resource warnings:", default_usage_warnings)
    print_validation_summary("Validation missing repository files:", missing_repository_files)
    print(
        "Warning: this script rewrites engine references and merges resources. "
        "It does not convert Sonolus LevelData."
    )
    print("Tip: delete the old imported collection in Sonolus before importing the new .scp, to avoid cache/name collisions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
