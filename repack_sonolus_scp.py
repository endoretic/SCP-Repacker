from __future__ import annotations

import argparse
import os
from collections import OrderedDict
from typing import Any, Dict, List, Sequence

from scp_repacker.archive import (
    copy_repository,
    read_zip,
    validate_repository_references,
    write_zip,
)
from scp_repacker.leveldata import convert_level_data_entries
from scp_repacker.metadata import (
    ENGINE_CATEGORY,
    RESOURCE_CATEGORIES,
    extract_engine_item,
    install_engines,
    merge_resource_category,
    patch_levels,
    print_available_engines,
    summarize_level_engines,
    validate_level_engine_consistency,
)


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
    ap.add_argument(
        "--convert-level-data",
        action="store_true",
        help=(
            "Convert supported PJSekai+/ProSeka R style LevelData to the NextRUSH/RUSH target format "
            "before rewriting engine references."
        ),
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

    output: "OrderedDict[str, bytes]" = OrderedDict(target_entries)

    level_data_conversion_results: List[Dict[str, Any]] = []
    if args.convert_level_data:
        level_data_conversion_results = convert_level_data_entries(output)

    replace_defaults = not args.no_replace_defaults
    patch_counts = patch_levels(output, target_engine, replace_defaults=replace_defaults)

    copied_target_repository = copy_repository(output, target_entries)
    copied_resource_repository = copy_repository(output, resource_entries)

    merged_engine_count = install_engines(
        output,
        resource_entries,
        args.engine,
        only_selected=args.only_selected_engine,
        keep_old_engines=args.keep_old_engines,
        original_target=target_entries,
    )

    merged_category_counts: Dict[str, int] = {}
    for category in RESOURCE_CATEGORIES:
        merged_category_counts[category] = merge_resource_category(output, target_entries, resource_entries, category)

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
    if args.convert_level_data:
        print("LevelData conversion results:")
        if not level_data_conversion_results:
            print("  none")
        for result in level_data_conversion_results:
            action = result.get("action")
            old_hash = result.get("hash")
            new_hash = result.get("new_hash")
            if action == "converted":
                print(
                    "  converted "
                    f"{old_hash} -> {new_hash} "
                    f"({result.get('entities_before')} entities -> {result.get('entities_after')})"
                )
            elif result.get("error"):
                print(f"  {action}: {old_hash} ({result.get('error')})")
            else:
                print(f"  {action}: {old_hash}")
    print(f"Merged {ENGINE_CATEGORY} list items: {merged_engine_count}")
    for category in RESOURCE_CATEGORIES:
        print(f"Merged {category} list items: {merged_category_counts[category]}")
    print(f"Copied repository files from target package: {copied_target_repository}")
    print(f"Copied repository files from resource package: {copied_resource_repository}")
    print_validation_summary("Validation engine mismatches:", engine_mismatches)
    print_validation_summary("Validation default-resource warnings:", default_usage_warnings)
    print_validation_summary("Validation missing repository files:", missing_repository_files)
    if args.convert_level_data:
        print("LevelData conversion: enabled for verified PJSekai+ / ProSeka R source formats.")
    else:
        print("LevelData conversion: disabled. Package metadata and resources were rewritten only.")
    print("Tip: delete the old imported collection in Sonolus before importing the new .scp, to avoid cache/name collisions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
