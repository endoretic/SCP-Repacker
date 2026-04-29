from __future__ import annotations

import json
import zipfile
from collections import OrderedDict
from typing import Any, Dict, Iterator


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


def copy_repository(target: "OrderedDict[str, bytes]", source: Dict[str, bytes]) -> int:
    copied = 0
    for path, data in source.items():
        if path.startswith("sonolus/repository/"):
            if target.get(path) != data:
                copied += 1
            target[path] = data
    return copied


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

