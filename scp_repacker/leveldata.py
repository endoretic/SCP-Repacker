from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections import OrderedDict
from typing import Any, Dict, List, Sequence, Set, Tuple

from .archive import dump_json, load_json
from .metadata import LEVEL_CATEGORY, category_item_paths, iter_level_metadata_items

EXTENDED_NOTE_TYPE_MAPPING = {
    "NormalTapNote": "NormalTapNote",
    "CriticalTapNote": "CriticalTapNote",
    "NormalFlickNote": "NormalFlickNote",
    "CriticalFlickNote": "CriticalFlickNote",
    "NormalSlideStartNote": "NormalHeadTapNote",
    "CriticalSlideStartNote": "CriticalHeadTapNote",
    "NormalSlideEndNote": "NormalTailReleaseNote",
    "CriticalSlideEndNote": "CriticalTailReleaseNote",
    "NormalSlideEndFlickNote": "NormalTailFlickNote",
    "CriticalSlideEndFlickNote": "CriticalTailFlickNote",
    "IgnoredSlideTickNote": "TransientHiddenTickNote",
    "NormalSlideTickNote": "NormalTickNote",
    "CriticalSlideTickNote": "CriticalTickNote",
    "HiddenSlideTickNote": "AnchorNote",
    "NormalAttachedSlideTickNote": "NormalTickNote",
    "CriticalAttachedSlideTickNote": "CriticalTickNote",
    "NormalTraceNote": "NormalTraceNote",
    "CriticalTraceNote": "CriticalTraceNote",
    "DamageNote": "DamageNote",
    "NormalTraceFlickNote": "NormalTraceFlickNote",
    "CriticalTraceFlickNote": "CriticalTraceFlickNote",
    "NonDirectionalTraceFlickNote": "NormalTraceFlickNote",
    "HiddenSlideStartNote": "AnchorNote",
    "NormalSlideTraceNote": "NormalHeadTraceNote",
    "CriticalSlideTraceNote": "CriticalHeadTraceNote",
    "NormalSlideEndTraceNote": "NormalTailTraceNote",
    "CriticalSlideEndTraceNote": "CriticalTailTraceNote",
    "NormalTraceSlideStartNote": "NormalHeadTraceNote",
    "CriticalTraceSlideStartNote": "CriticalHeadTraceNote",
    "NormalTraceSlideEndNote": "NormalTailTraceNote",
    "CriticalTraceSlideEndNote": "CriticalTailTraceNote",
}
EXTENDED_ACTIVE_CONNECTOR_KIND_MAPPING = {
    # PJSekai+ uses bare connector names for active slides. ProSeka R also uses
    # bare names for guides, which are filtered before regular slide conversion.
    "NormalSlideConnector": 1,
    "CriticalSlideConnector": 2,
    "NormalActiveSlideConnector": 1,
    "CriticalActiveSlideConnector": 2,
}
EXTENDED_FLICK_DIRECTION_MAPPING = {
    -1: 1,
    0: 0,
    1: 2,
}
EXTENDED_EASE_TYPE_MAPPING = {
    -2: 5,
    -1: 3,
    0: 1,
    1: 2,
    2: 4,
}
EXTENDED_FADE_ALPHA_MAPPING = {
    0: (1.0, 0.0),
    1: (1.0, 1.0),
    2: (0.0, 1.0),
}
EXTENDED_GUIDE_KIND_MAPPING = {
    0: 101,
    1: 102,
    2: 103,
    3: 104,
    4: 105,
    5: 106,
    6: 107,
    7: 108,
}
PROSEKA_R_GUIDE_ARCHETYPE_KIND = {
    "NormalSlideConnector": 103,   # Green
    "CriticalSlideConnector": 105,  # Yellow
}


class EntityBuilder:
    def __init__(self, archetype: str) -> None:
        self.archetype = archetype
        self.values: "OrderedDict[str, float]" = OrderedDict()
        self.refs: "OrderedDict[str, EntityBuilder]" = OrderedDict()

    def set(self, key: str, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, EntityBuilder):
            self.refs[key] = value
        elif isinstance(value, (int, float)):
            self.values[key] = value

    def beat(self) -> float:
        return float(self.values.get("#BEAT", -1))


def entity_data_map(entity: Dict[str, Any]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    data = entity.get("data")
    if not isinstance(data, list):
        return result
    for field in data:
        if not isinstance(field, dict):
            continue
        name = field.get("name")
        if not isinstance(name, str):
            continue
        if "value" in field:
            result[name] = field.get("value")
        elif "ref" in field:
            result[name] = field.get("ref")
    return result


def get_num(entity: Dict[str, Any], name: str, default: float = 0) -> float:
    value = entity_data_map(entity).get(name)
    return value if isinstance(value, (int, float)) else default


def get_field(entity: Dict[str, Any], name: str) -> Any:
    return entity_data_map(entity).get(name)


def has_field(entity: Dict[str, Any], name: str) -> bool:
    return name in entity_data_map(entity)


def get_optional_num(entity: Dict[str, Any], name: str) -> Any:
    value = get_field(entity, name)
    return value if isinstance(value, (int, float)) else None


def build_entity_indexes(entities: Sequence[Dict[str, Any]]) -> Tuple[Dict[str, List[Tuple[int, Dict[str, Any]]]], Dict[str, Dict[str, Any]]]:
    by_archetype: Dict[str, List[Tuple[int, Dict[str, Any]]]] = {}
    by_name: Dict[str, Dict[str, Any]] = {}
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        archetype = entity.get("archetype")
        if isinstance(archetype, str):
            by_archetype.setdefault(archetype, []).append((index, entity))
        name = entity.get("name")
        if isinstance(name, str):
            by_name[name] = entity
    return by_archetype, by_name


def resolve_source_entity(entities: Sequence[Dict[str, Any]], by_name: Dict[str, Dict[str, Any]], ref: Any) -> Any:
    if isinstance(ref, int) and 0 <= ref < len(entities):
        return entities[ref]
    if isinstance(ref, str):
        entity = by_name.get(ref)
        if entity is not None:
            return entity
        try:
            index = int(ref)
        except ValueError:
            return None
        if 0 <= index < len(entities):
            return entities[index]
    return None


def is_next_rush_level_data(level_data: Dict[str, Any]) -> bool:
    entities = level_data.get("entities")
    return isinstance(entities, list) and any(
        isinstance(entity, dict) and entity.get("archetype") == "#TIMESCALE_GROUP" for entity in entities
    )


def is_convertible_extended_level_data(level_data: Dict[str, Any]) -> bool:
    entities = level_data.get("entities")
    if not isinstance(entities, list) or is_next_rush_level_data(level_data):
        return False
    archetypes = {entity.get("archetype") for entity in entities if isinstance(entity, dict)}
    return bool(
        archetypes.intersection(EXTENDED_NOTE_TYPE_MAPPING)
        or archetypes.intersection(EXTENDED_ACTIVE_CONNECTOR_KIND_MAPPING)
        or "TimeScaleGroup" in archetypes
        or "#TIMESCALE_CHANGE" in archetypes
    )


def nearly_equal(left: float, right: float) -> bool:
    return abs(left - right) < 1e-6


def lerp(left: float, right: float, amount: float) -> float:
    return left + (right - left) * amount


def unlerp(left: float, right: float, value: float) -> float:
    return (value - left) / (right - left)


def clamp01(value: float) -> float:
    return min(1.0, max(0.0, value))


def apply_ease(ease_type: int, value: float) -> float:
    t = clamp01(value)
    if ease_type == 2:
        return t * t
    if ease_type == 3:
        return 1 - (1 - t) * (1 - t)
    if ease_type == 4:
        return 2 * t * t if t < 0.5 else 1 - ((-2 * t + 2) ** 2) / 2
    if ease_type == 5:
        return (1 - (1 - 2 * t) * (1 - 2 * t)) / 2 if t < 0.5 else 0.5 + ((2 * t - 1) * (2 * t - 1)) / 2
    return t


def convert_extended_level_data(level_data: Dict[str, Any]) -> Dict[str, Any]:
    entities = level_data.get("entities")
    if not isinstance(entities, list):
        raise ValueError("LevelData does not contain an entities list")

    by_archetype, by_name = build_entity_indexes(entities)
    default_tsg = EntityBuilder("#TIMESCALE_GROUP")
    init = EntityBuilder("Initialization")
    final_entities: List[EntityBuilder] = [default_tsg, init]

    bpm_changes = [
        {"beat": get_num(entity, "#BEAT"), "bpm": get_num(entity, "#BPM")}
        for _, entity in by_archetype.get("#BPM_CHANGE", [])
    ]
    bpm_changes.sort(key=lambda change: change["beat"])
    bpm_change_infos: List[Dict[str, float]] = []
    last_beat = 0.0
    last_time = 0.0
    last_bpm = float(bpm_changes[0]["bpm"]) if bpm_changes else 120.0

    for change in bpm_changes:
        beat = float(change["beat"])
        bpm = float(change["bpm"])
        last_time += ((beat - last_beat) * 60) / last_bpm
        bpm_change_infos.append({"beat": beat, "bpm": bpm, "time": last_time})
        last_beat = beat
        last_bpm = bpm

    def beat_to_time(beat: float) -> float:
        if not bpm_change_infos:
            return (beat * 60) / 120
        current = bpm_change_infos[0]
        for change in bpm_change_infos:
            if change["beat"] > beat:
                break
            current = change
        return current["time"] + ((beat - current["beat"]) * 60) / current["bpm"]

    def time_to_beat(time: float) -> float:
        if not bpm_change_infos:
            return (time * 120) / 60
        current = bpm_change_infos[0]
        for change in bpm_change_infos:
            if change["time"] > time:
                break
            current = change
        return current["beat"] + ((time - current["time"]) * current["bpm"]) / 60

    for _, entity in by_archetype.get("#BPM_CHANGE", []):
        bpm = EntityBuilder("#BPM_CHANGE")
        bpm.set("#BEAT", get_num(entity, "#BEAT"))
        bpm.set("#BPM", get_num(entity, "#BPM"))
        final_entities.append(bpm)

    timescale_groups_by_index: Dict[int, EntityBuilder] = {}
    timescale_groups_by_name: Dict[str, EntityBuilder] = {}
    timescale_changes_by_index: Dict[int, List[Dict[str, float]]] = {}
    timescale_changes_by_name: Dict[str, List[Dict[str, float]]] = {}

    def emit_timescale_changes(group: EntityBuilder, source_changes: Sequence[Dict[str, Any]]) -> List[Dict[str, float]]:
        changes: List[EntityBuilder] = []
        change_infos: List[Dict[str, float]] = []
        for raw_change in source_changes:
            beat = get_num(raw_change, "#BEAT")
            timescale = get_num(raw_change, "timeScale", get_num(raw_change, "#TIMESCALE", 1))
            change_infos.append({"beat": beat, "timeScale": timescale})
            change = EntityBuilder("#TIMESCALE_CHANGE")
            change.set("#BEAT", beat)
            change.set("#TIMESCALE", timescale)
            change.set("#TIMESCALE_SKIP", get_num(raw_change, "#TIMESCALE_SKIP", 0))
            change.set("#TIMESCALE_GROUP", group)
            change.set("#TIMESCALE_EASE", get_num(raw_change, "#TIMESCALE_EASE", 0))
            change.set("hideNotes", get_num(raw_change, "hideNotes", 0))
            if changes:
                changes[-1].set("next", change)
            changes.append(change)
        if changes:
            group.set("first", changes[0])
            final_entities.extend(changes)
        change_infos.sort(key=lambda change: change["beat"])
        return change_infos

    source_timescale_groups = by_archetype.get("TimeScaleGroup", [])
    fallback_tsg = default_tsg
    if source_timescale_groups:
        for index, entity in source_timescale_groups:
            group = EntityBuilder("#TIMESCALE_GROUP")
            final_entities.append(group)
            timescale_groups_by_index[index] = group
            name = entity.get("name")
            if isinstance(name, str):
                timescale_groups_by_name[name] = group

            raw_ref = get_field(entity, "first")
            source_changes: List[Dict[str, Any]] = []
            seen_refs = set()
            while raw_ref is not None and raw_ref not in seen_refs:
                seen_refs.add(raw_ref)
                raw_change = resolve_source_entity(entities, by_name, raw_ref)
                if not isinstance(raw_change, dict):
                    break
                source_changes.append(raw_change)
                next_ref = get_field(raw_change, "next")
                if isinstance(next_ref, (int, float)) and next_ref <= 0:
                    break
                raw_ref = next_ref
            change_infos = emit_timescale_changes(group, source_changes)
            timescale_changes_by_index[index] = change_infos
            if isinstance(name, str):
                timescale_changes_by_name[name] = change_infos
    else:
        source_changes = [entity for _, entity in by_archetype.get("#TIMESCALE_CHANGE", [])]
        source_changes.sort(key=lambda entity: get_num(entity, "#BEAT"))
        if not source_changes:
            source_changes = [
                {
                    "data": [
                        {"name": "#BEAT", "value": 0},
                        {"name": "#TIMESCALE", "value": 1},
                    ]
                }
            ]
        emit_timescale_changes(default_tsg, source_changes)

    def get_tsg(ref: Any) -> Any:
        if isinstance(ref, int):
            return timescale_groups_by_index.get(ref)
        if isinstance(ref, str):
            return timescale_groups_by_name.get(ref)
        return None

    def get_tsg_or_default(ref: Any) -> EntityBuilder:
        return get_tsg(ref) or fallback_tsg

    def get_tsg_changes(ref: Any) -> List[Dict[str, float]]:
        if isinstance(ref, int):
            return timescale_changes_by_index.get(ref, [])
        if isinstance(ref, str):
            return timescale_changes_by_name.get(ref, [])
        return []

    def time_to_scaled_time(time: float, changes: Sequence[Dict[str, float]]) -> float:
        if not changes:
            return time
        first_time = beat_to_time(changes[0]["beat"])
        if time < first_time:
            return time
        scaled_time = first_time
        for index, start in enumerate(changes):
            start_time = beat_to_time(start["beat"])
            end_time = None if index == len(changes) - 1 else beat_to_time(changes[index + 1]["beat"])
            if end_time is None or time < end_time:
                return scaled_time + (time - start_time) * start["timeScale"]
            scaled_time += (end_time - start_time) * start["timeScale"]
        return time

    def scaled_time_to_time(scaled_time: float, changes: Sequence[Dict[str, float]]) -> float:
        if not changes:
            return scaled_time
        first_time = beat_to_time(changes[0]["beat"])
        if scaled_time < first_time:
            return scaled_time
        current_scaled_time = first_time
        for index, start in enumerate(changes):
            start_time = beat_to_time(start["beat"])
            end_time = None if index == len(changes) - 1 else beat_to_time(changes[index + 1]["beat"])
            if end_time is None:
                if start["timeScale"] == 0:
                    return math.inf
                return start_time + (scaled_time - current_scaled_time) / start["timeScale"]
            next_scaled_time = current_scaled_time + (end_time - start_time) * start["timeScale"]
            min_scaled_time = min(current_scaled_time, next_scaled_time)
            max_scaled_time = max(current_scaled_time, next_scaled_time)
            if min_scaled_time <= scaled_time <= max_scaled_time:
                if abs(next_scaled_time - current_scaled_time) < 1e-6:
                    return start_time
                return lerp(start_time, end_time, unlerp(current_scaled_time, next_scaled_time, scaled_time))
            current_scaled_time = next_scaled_time
        return scaled_time

    notes_by_index: Dict[int, EntityBuilder] = {}
    notes_by_name: Dict[str, EntityBuilder] = {}
    connectors_by_index: Dict[int, Dict[str, Any]] = {}
    connectors_by_name: Dict[str, Dict[str, Any]] = {}

    source_archetypes = {entity.get("archetype") for entity in entities if isinstance(entity, dict)}
    bare_connector_archetypes = {"NormalSlideConnector", "CriticalSlideConnector"}
    proseka_r_active_connector_archetypes = {"NormalActiveSlideConnector", "CriticalActiveSlideConnector"}
    bare_connector_entities = [
        entity for archetype in bare_connector_archetypes for _, entity in by_archetype.get(archetype, [])
    ]
    uses_proseka_r_connector_schema = bool(source_archetypes.intersection(proseka_r_active_connector_archetypes)) or (
        bool(bare_connector_entities)
        and not any(has_field(entity, "startType") for entity in bare_connector_entities)
        and "TimeScaleGroup" not in source_archetypes
    )

    def is_proseka_r_guide_connector(entity: Dict[str, Any]) -> bool:
        return (
            entity.get("archetype") in bare_connector_archetypes
            and uses_proseka_r_connector_schema
            and not has_field(entity, "startType")
        )

    guide_connector_source_entities: List[Tuple[int, Dict[str, Any]]] = []
    for index, entity in enumerate(entities):
        if isinstance(entity, dict) and is_proseka_r_guide_connector(entity):
            guide_connector_source_entities.append((index, entity))

    guide_note_refs: Set[Any] = set()
    for _, entity in guide_connector_source_entities:
        for key in ("start", "end", "head", "tail"):
            ref = get_field(entity, key)
            if ref is not None:
                guide_note_refs.add(ref)

    note_source_entities: List[Tuple[int, Dict[str, Any]]] = []
    connector_source_entities: List[Tuple[int, Dict[str, Any]]] = []
    for index, entity in enumerate(entities):
        if not isinstance(entity, dict):
            continue
        archetype = entity.get("archetype")
        name = entity.get("name")
        is_guide_note = index in guide_note_refs or (isinstance(name, str) and name in guide_note_refs)
        if archetype in EXTENDED_NOTE_TYPE_MAPPING and not is_guide_note:
            note_source_entities.append((index, entity))
        if archetype in EXTENDED_ACTIVE_CONNECTOR_KIND_MAPPING and not is_proseka_r_guide_connector(entity):
            connector_source_entities.append((index, entity))

    source_entity_index_by_id = {
        id(entity): index for index, entity in enumerate(entities) if isinstance(entity, dict)
    }
    connectors_by_head_ref: Dict[Any, List[Tuple[int, Dict[str, Any]]]] = {}
    connectors_by_tail_ref: Dict[Any, List[Tuple[int, Dict[str, Any]]]] = {}
    connectors_by_start_ref: Dict[Any, List[Tuple[int, Dict[str, Any]]]] = {}

    def push_connector_index(
        index: Dict[Any, List[Tuple[int, Dict[str, Any]]]],
        key: Any,
        entry: Tuple[int, Dict[str, Any]],
    ) -> None:
        if key is None:
            return
        index.setdefault(key, []).append(entry)

    for entry in connector_source_entities:
        _, entity = entry
        push_connector_index(connectors_by_head_ref, get_field(entity, "head"), entry)
        push_connector_index(connectors_by_tail_ref, get_field(entity, "tail"), entry)
        push_connector_index(connectors_by_start_ref, get_field(entity, "start"), entry)

    def get_connectors_by_head_ref(ref: Any) -> List[Tuple[int, Dict[str, Any]]]:
        return [] if ref is None else connectors_by_head_ref.get(ref, [])

    def get_connectors_by_tail_ref(ref: Any) -> List[Tuple[int, Dict[str, Any]]]:
        return [] if ref is None else connectors_by_tail_ref.get(ref, [])

    def get_connectors_by_start_ref(ref: Any) -> List[Tuple[int, Dict[str, Any]]]:
        return [] if ref is None else connectors_by_start_ref.get(ref, [])

    def get_target_note_archetype(entity: Dict[str, Any]) -> str:
        archetype = str(entity.get("archetype"))
        if uses_proseka_r_connector_schema:
            if archetype == "HiddenSlideTickNote" and has_field(entity, "attach"):
                return "TransientHiddenTickNote"
            if archetype == "IgnoredSlideTickNote" and has_field(entity, "lane"):
                return "AnchorNote"
            if archetype == "NormalTraceFlickNote" and has_field(entity, "slide"):
                return "NormalTailTraceFlickNote"
            if archetype == "CriticalTraceFlickNote" and has_field(entity, "slide"):
                return "CriticalTailTraceFlickNote"
        return EXTENDED_NOTE_TYPE_MAPPING[archetype]

    for index, entity in note_source_entities:
        target_archetype = get_target_note_archetype(entity)
        note = EntityBuilder(target_archetype)
        note.set("#BEAT", get_num(entity, "#BEAT"))
        note.set("lane", get_num(entity, "lane", 0))
        note.set("size", get_num(entity, "size", 0))
        note.set("direction", EXTENDED_FLICK_DIRECTION_MAPPING.get(int(get_num(entity, "direction", 0)), 0))
        note.set("segmentKind", 1)
        note.set("segmentAlpha", 1)
        note.set("segmentLayer", 0)
        note.set("isAttached", 0)
        note.set("connectorEase", 0)
        note.set("isSeparator", 0)
        final_entities.append(note)
        notes_by_index[index] = note
        name = entity.get("name")
        if isinstance(name, str):
            notes_by_name[name] = note

    def get_note(ref: Any) -> Any:
        if isinstance(ref, int):
            return notes_by_index.get(ref)
        if isinstance(ref, str):
            return notes_by_name.get(ref)
        return None

    def resolve_original(ref: Any) -> Any:
        return resolve_source_entity(entities, by_name, ref)

    def source_archetype_of(ref: Any) -> str:
        source = resolve_original(ref)
        return str(source.get("archetype", "")) if isinstance(source, dict) else ""

    def get_time_scale_at(changes: Sequence[Dict[str, float]], beat: float) -> float:
        for change in reversed(changes):
            if change["beat"] < beat - 1e-6:
                return change["timeScale"]
        return 1

    active_slide_start_archetypes = {
        "NormalSlideStartNote",
        "CriticalSlideStartNote",
        "HiddenSlideStartNote",
        "NormalTraceSlideStartNote",
        "CriticalTraceSlideStartNote",
    }

    def should_use_start_as_head(start_ref: Any, head_ref: Any) -> bool:
        if start_ref == head_ref:
            return False
        start = resolve_original(start_ref)
        head = resolve_original(head_ref)
        if not isinstance(start, dict) or not isinstance(head, dict):
            return False
        if head.get("archetype") != "HiddenSlideStartNote":
            return False
        if start.get("archetype") not in active_slide_start_archetypes:
            return False
        return (
            nearly_equal(get_num(start, "#BEAT"), get_num(head, "#BEAT"))
            and nearly_equal(get_num(start, "lane"), get_num(head, "lane"))
            and nearly_equal(get_num(start, "size"), get_num(head, "size"))
        )

    def create_connector_anchor(beat: float, lane: float, size: float, tsg: Any, kind: float) -> EntityBuilder:
        anchor = EntityBuilder("AnchorNote")
        anchor.set("#BEAT", beat)
        anchor.set("lane", lane)
        anchor.set("size", size)
        anchor.set("direction", 0)
        anchor.set("#TIMESCALE_GROUP", tsg or default_tsg)
        anchor.set("isAttached", 0)
        anchor.set("connectorEase", 1)
        anchor.set("isSeparator", 0)
        anchor.set("segmentKind", kind)
        anchor.set("segmentAlpha", 1)
        anchor.set("segmentLayer", 0)
        final_entities.append(anchor)
        return anchor

    def get_connector_split_anchors(
        head_original: Dict[str, Any],
        tail_original: Dict[str, Any],
        tsg: Any,
        kind: float,
        ease: int,
    ) -> List[EntityBuilder]:
        head_beat = get_num(head_original, "#BEAT")
        tail_beat = get_num(tail_original, "#BEAT")
        if tail_beat <= head_beat:
            return []

        head_changes = get_tsg_changes(get_field(head_original, "timeScaleGroup"))
        tail_changes = get_tsg_changes(get_field(tail_original, "timeScaleGroup"))
        split_beats = [
            change["beat"]
            for change in head_changes
            if head_beat + 1e-6 < change["beat"] < tail_beat - 1e-6
            and not nearly_equal(change["timeScale"], get_time_scale_at(head_changes, change["beat"]))
        ]
        if not split_beats:
            return []

        head_scaled_time = time_to_scaled_time(beat_to_time(head_beat), head_changes)
        tail_scaled_time = time_to_scaled_time(beat_to_time(tail_beat), tail_changes)
        if abs(tail_scaled_time - head_scaled_time) < 1e-6:
            return []

        if ease != 1:
            for index in range(1, 8):
                scaled_time = lerp(head_scaled_time, tail_scaled_time, index / 8)
                beat = time_to_beat(scaled_time_to_time(scaled_time, head_changes))
                if math.isfinite(beat) and head_beat + 1e-6 < beat < tail_beat - 1e-6:
                    split_beats.append(beat)

        unique_split_beats: List[float] = []
        for beat in sorted(split_beats):
            if not unique_split_beats or not nearly_equal(beat, unique_split_beats[-1]):
                unique_split_beats.append(beat)

        head_lane = get_num(head_original, "lane")
        tail_lane = get_num(tail_original, "lane")
        head_size = get_num(head_original, "size")
        tail_size = get_num(tail_original, "size")

        anchors: List[EntityBuilder] = []
        for beat in unique_split_beats:
            scaled_time = time_to_scaled_time(beat_to_time(beat), head_changes)
            frac = unlerp(head_scaled_time, tail_scaled_time, scaled_time)
            eased_frac = apply_ease(ease, frac)
            anchors.append(
                create_connector_anchor(
                    beat,
                    lerp(head_lane, tail_lane, eased_frac),
                    lerp(head_size, tail_size, eased_frac),
                    tsg,
                    kind,
                )
            )
        return anchors

    def is_reverse_hidden_pop_connector(head_original: Any, tail_original: Any) -> bool:
        if not isinstance(head_original, dict) or not isinstance(tail_original, dict):
            return False
        if head_original.get("archetype") != "HiddenSlideStartNote":
            return False
        if tail_original.get("archetype") != "HiddenSlideTickNote":
            return False
        return get_num(tail_original, "#BEAT") < get_num(head_original, "#BEAT") - 1e-6

    def is_slide_tick_ref(ref: Any) -> bool:
        return source_archetype_of(ref) in {
            "IgnoredSlideTickNote",
            "NormalSlideTickNote",
            "CriticalSlideTickNote",
            "HiddenSlideTickNote",
            "NormalAttachedSlideTickNote",
            "CriticalAttachedSlideTickNote",
        }

    def is_scored_slide_tick_ref(ref: Any) -> bool:
        return source_archetype_of(ref) in {
            "NormalSlideTickNote",
            "CriticalSlideTickNote",
            "NormalAttachedSlideTickNote",
            "CriticalAttachedSlideTickNote",
        }

    def source_beat(ref: Any) -> float:
        source = resolve_original(ref)
        return get_num(source, "#BEAT") if isinstance(source, dict) else 0

    def get_ultimate_tail_ref(archetype: str, start_ref: Any, tail_ref: Any) -> Any:
        ultimate_tail_ref = tail_ref
        ultimate_tail_beat = source_beat(tail_ref)
        visited: Set[Tuple[str, str]] = set()

        def visit(head_ref: Any) -> None:
            nonlocal ultimate_tail_ref, ultimate_tail_beat
            key = (str(start_ref), str(head_ref))
            if head_ref is None or key in visited:
                return
            visited.add(key)

            head_connectors = get_connectors_by_head_ref(head_ref)
            next_connectors = [
                candidate
                for _, candidate in head_connectors
                if candidate.get("archetype") == archetype and get_field(candidate, "start") == start_ref
            ]
            if not next_connectors:
                next_connectors = [
                    candidate
                    for _, candidate in head_connectors
                    if candidate.get("archetype") == archetype
                ]
            if not next_connectors:
                beat = source_beat(head_ref)
                if beat >= ultimate_tail_beat:
                    ultimate_tail_beat = beat
                    ultimate_tail_ref = head_ref
                return
            for next_connector in next_connectors:
                visit(get_field(next_connector, "tail"))

        visit(tail_ref)
        if is_scored_slide_tick_ref(ultimate_tail_ref):
            for _, candidate in get_connectors_by_start_ref(start_ref):
                if candidate.get("archetype") != archetype:
                    continue
                candidate_tail_ref = get_field(candidate, "tail")
                candidate_tail_beat = source_beat(candidate_tail_ref)
                if candidate_tail_beat > ultimate_tail_beat:
                    ultimate_tail_ref = candidate_tail_ref
                    ultimate_tail_beat = candidate_tail_beat
        return ultimate_tail_ref

    def get_ultimate_start_ref(archetype: str, start_ref: Any, head_ref: Any) -> Any:
        if not is_slide_tick_ref(head_ref):
            return start_ref
        ultimate_start_ref = start_ref
        visited: Set[Tuple[str, str]] = set()

        def visit(current_head_ref: Any) -> None:
            nonlocal ultimate_start_ref
            key = (archetype, str(current_head_ref))
            if current_head_ref is None or key in visited:
                return
            visited.add(key)
            if not is_slide_tick_ref(current_head_ref):
                return

            tail_connectors = get_connectors_by_tail_ref(current_head_ref)
            previous_connectors = [
                candidate for _, candidate in tail_connectors if candidate.get("archetype") == archetype
            ]
            if not previous_connectors:
                previous_connectors = [
                    candidate
                    for _, candidate in tail_connectors
                    if candidate.get("archetype") in EXTENDED_ACTIVE_CONNECTOR_KIND_MAPPING
                ]

            for previous_connector in previous_connectors:
                ultimate_start_ref = get_field(previous_connector, "start")
                visit(get_field(previous_connector, "head"))

        visit(head_ref)
        return ultimate_start_ref

    def set_inferred_active_head(note: EntityBuilder, active_head: EntityBuilder) -> None:
        if "activeHead" not in note.refs:
            note.set("activeHead", active_head)

    def is_ignored_slide_tick_ref(ref: Any) -> bool:
        source = resolve_original(ref)
        if not isinstance(source, dict) or source.get("archetype") != "IgnoredSlideTickNote":
            return False
        return not (uses_proseka_r_connector_schema and has_field(source, "lane"))

    def get_next_connector_with_head(archetype: str, start_ref: Any, head_ref: Any) -> Any:
        head_connectors = get_connectors_by_head_ref(head_ref)
        for index, candidate in head_connectors:
            if candidate.get("archetype") == archetype and get_field(candidate, "start") == start_ref:
                return index, candidate
        for index, candidate in head_connectors:
            if candidate.get("archetype") == archetype:
                return index, candidate
        return None

    def resolve_connector_tail_ref(archetype: str, start_ref: Any, tail_ref: Any) -> Dict[str, Any]:
        skipped_note_refs: List[Any] = []
        skipped_connectors: List[Tuple[int, Dict[str, Any]]] = []
        visited: Set[str] = set()
        resolved_tail_ref = tail_ref
        while is_ignored_slide_tick_ref(resolved_tail_ref):
            if resolved_tail_ref is None:
                break
            key = str(resolved_tail_ref)
            if key in visited:
                break
            visited.add(key)
            skipped_note_refs.append(resolved_tail_ref)
            next_connector = get_next_connector_with_head(archetype, start_ref, resolved_tail_ref)
            if next_connector is None:
                break
            skipped_connectors.append(next_connector)
            resolved_tail_ref = get_field(next_connector[1], "tail")
        return {
            "tail_ref": resolved_tail_ref,
            "skipped_note_refs": skipped_note_refs,
            "skipped_connectors": skipped_connectors,
        }

    def ref_key(ref: Any) -> str:
        original = resolve_original(ref)
        index = source_entity_index_by_id.get(id(original)) if isinstance(original, dict) else None
        return f"index:{index}" if index is not None else f"{type(ref).__name__}:{ref}"

    def get_ref_beat(ref: Any) -> float:
        return source_beat(ref)

    def get_connector_active_start_ref(archetype: str, start_ref: Any, head_ref: Any, end_ref: Any) -> Any:
        if end_ref is not None:
            return start_ref
        return get_ultimate_start_ref(archetype, start_ref, head_ref)

    active_tail_refs_by_start: Dict[str, Any] = {}

    def get_active_tail_ref(active_start_ref: Any) -> Any:
        key = ref_key(active_start_ref)
        if key in active_tail_refs_by_start:
            return active_tail_refs_by_start[key]

        active_tail_ref = None
        active_tail_beat = -math.inf

        for _, candidate in connector_source_entities:
            start_ref = get_field(candidate, "start")
            head_ref = get_field(candidate, "head")
            if is_ignored_slide_tick_ref(head_ref):
                continue

            end_ref = get_field(candidate, "end")
            connector_active_start_ref = get_connector_active_start_ref(
                str(candidate.get("archetype")),
                start_ref,
                head_ref,
                end_ref,
            )
            if ref_key(connector_active_start_ref) != key:
                continue

            tail_info = resolve_connector_tail_ref(str(candidate.get("archetype")), start_ref, get_field(candidate, "tail"))
            candidate_tail_ref = (
                end_ref
                if end_ref is not None
                else get_ultimate_tail_ref(str(candidate.get("archetype")), active_start_ref, tail_info["tail_ref"])
            )
            candidate_tail_beat = get_ref_beat(candidate_tail_ref)
            if candidate_tail_beat >= active_tail_beat:
                active_tail_beat = candidate_tail_beat
                active_tail_ref = candidate_tail_ref

        active_tail_refs_by_start[key] = active_tail_ref
        return active_tail_ref

    for index, entity in connector_source_entities:
        source_archetype = str(entity.get("archetype"))
        start_ref = get_field(entity, "start")
        head_ref = get_field(entity, "head")
        if is_ignored_slide_tick_ref(head_ref):
            continue

        tail_info = resolve_connector_tail_ref(source_archetype, start_ref, get_field(entity, "tail"))
        tail_ref = tail_info["tail_ref"]
        if is_ignored_slide_tick_ref(tail_ref):
            continue

        raw_head_original = resolve_original(head_ref)
        tail_original = resolve_original(tail_ref)
        raw_head = get_note(head_ref)
        tail = get_note(tail_ref)

        end_ref = get_field(entity, "end")
        active_start_ref = get_connector_active_start_ref(source_archetype, start_ref, head_ref, end_ref)
        active_head = get_note(active_start_ref)
        uses_start_as_head = should_use_start_as_head(start_ref, head_ref)
        head = active_head if uses_start_as_head else raw_head
        head_original = resolve_original(start_ref if uses_start_as_head else head_ref)

        active_tail = get_note(end_ref if end_ref is not None else get_active_tail_ref(active_start_ref))
        if active_tail is None:
            active_tail = get_note(get_active_tail_ref(active_start_ref))
        if active_tail is None:
            active_tail = tail

        if not (head and tail and active_head and active_tail):
            continue

        connector_kind = EXTENDED_ACTIVE_CONNECTOR_KIND_MAPPING[source_archetype]
        ease = EXTENDED_EASE_TYPE_MAPPING.get(int(get_num(entity, "ease", 0)), 1)
        tsg = get_tsg(get_field(head_original, "timeScaleGroup")) if isinstance(head_original, dict) else None
        reverse_hidden_pop_connector = is_reverse_hidden_pop_connector(raw_head_original, tail_original)
        split_anchors = (
            get_connector_split_anchors(head_original, tail_original, tsg, connector_kind, ease)
            if isinstance(head_original, dict) and isinstance(tail_original, dict) and not reverse_hidden_pop_connector
            else []
        )
        segment_ease = 1 if split_anchors else ease
        segment_notes = [head, *split_anchors, tail]
        segments: List[Dict[str, EntityBuilder]] = []

        if reverse_hidden_pop_connector and isinstance(raw_head_original, dict) and isinstance(tail_original, dict):
            segment_head = create_connector_anchor(
                get_num(raw_head_original, "#BEAT"),
                get_num(raw_head_original, "lane"),
                get_num(raw_head_original, "size"),
                get_tsg(get_field(raw_head_original, "timeScaleGroup")) or tsg,
                connector_kind,
            )
            connector = EntityBuilder("Connector")
            connector.set("head", head)
            connector.set("tail", tail)
            connector.set("segmentHead", segment_head)
            connector.set("segmentTail", tail)
            connector.set("legacyHiddenPop", 1)
            connector.set("activeHead", active_head)
            connector.set("activeTail", active_tail)
            final_entities.append(connector)
            set_inferred_active_head(segment_head, active_head)
            segments.append({"head": segment_head, "tail": tail})
        else:
            for segment_head, segment_tail in zip(segment_notes, segment_notes[1:]):
                connector = EntityBuilder("Connector")
                connector.set("head", segment_head)
                connector.set("tail", segment_tail)
                connector.set("segmentHead", segment_head)
                connector.set("segmentTail", segment_tail)
                connector.set("activeHead", active_head)
                connector.set("activeTail", active_tail)
                final_entities.append(connector)
                segments.append({"head": segment_head, "tail": segment_tail})

        connector_link = {
            "head": head,
            "tail": tail,
            "activeHead": active_head,
            "activeTail": active_tail,
            "segments": segments,
        }

        for segment_head in segment_notes[:-1]:
            segment_head.set("connectorEase", segment_ease)
            segment_head.set("segmentKind", connector_kind)
            segment_head.set("segmentAlpha", 1)

        tail.set("segmentKind", connector_kind)
        tail.set("segmentAlpha", 1)
        active_head.set("segmentKind", connector_kind)
        for segment_note in segment_notes:
            set_inferred_active_head(segment_note, active_head)
        set_inferred_active_head(active_tail, active_head)
        for skipped_note_ref in tail_info["skipped_note_refs"]:
            skipped_note = get_note(skipped_note_ref)
            if skipped_note is None:
                continue
            skipped_note.set("attachHead", head)
            skipped_note.set("attachTail", tail)
            skipped_note.set("isAttached", 1)
            set_inferred_active_head(skipped_note, active_head)

        connectors_by_index[index] = connector_link
        name = entity.get("name")
        if isinstance(name, str):
            connectors_by_name[name] = connector_link
        for skipped_index, skipped_connector in tail_info["skipped_connectors"]:
            connectors_by_index[skipped_index] = connector_link
            skipped_name = skipped_connector.get("name")
            if isinstance(skipped_name, str):
                connectors_by_name[skipped_name] = connector_link

    def get_connector(ref: Any) -> Any:
        if isinstance(ref, int):
            return connectors_by_index.get(ref)
        if isinstance(ref, str):
            return connectors_by_name.get(ref)
        return None

    def get_attach_segment(connector: Dict[str, Any], beat: float) -> Dict[str, EntityBuilder]:
        for segment in connector["segments"]:
            head_beat = segment["head"].beat()
            tail_beat = segment["tail"].beat()
            min_beat = min(head_beat, tail_beat)
            max_beat = max(head_beat, tail_beat)
            if min_beat - 1e-6 <= beat <= max_beat + 1e-6:
                return segment
        return {"head": connector["head"], "tail": connector["tail"]}

    for index, note in notes_by_index.items():
        source = entities[index]
        note.set("#TIMESCALE_GROUP", get_tsg_or_default(get_field(source, "timeScaleGroup")))

        attach_ref = get_field(source, "attach")
        attach_connector = get_connector(attach_ref)
        if isinstance(attach_connector, dict):
            attach_segment = get_attach_segment(attach_connector, get_num(source, "#BEAT"))
            note.set("attachHead", attach_segment["head"])
            note.set("attachTail", attach_segment["tail"])
            note.set("isAttached", 1)

        slide_ref = get_field(source, "slide")
        slide_connector = get_connector(slide_ref)
        if isinstance(slide_connector, dict):
            note.set("activeHead", slide_connector["activeHead"])

    for _, entity in by_archetype.get("SimLine", []):
        left = get_note(get_field(entity, "a"))
        right = get_note(get_field(entity, "b"))
        if left and right:
            sim = EntityBuilder("SimLine")
            sim.set("left", left)
            sim.set("right", right)
            final_entities.append(sim)

    anchors_by_beat: Dict[float, List[EntityBuilder]] = {}
    anchor_positions: Dict[EntityBuilder, Set[str]] = {}

    def get_anchor(
        beat: float,
        lane: float,
        size: float,
        tsg: Any,
        position: str,
        segment_kind: float = -1,
        segment_alpha: float = -1,
        connector_ease: float = -1,
    ) -> EntityBuilder:
        anchor_tsg = tsg or default_tsg
        anchors = anchors_by_beat.get(beat, [])
        for anchor in anchors:
            positions = anchor_positions.get(anchor, set())
            if position in positions:
                continue
            if (
                anchor.values.get("lane") == lane
                and anchor.values.get("size") == size
                and anchor.refs.get("#TIMESCALE_GROUP") is anchor_tsg
                and (segment_kind == -1 or anchor.values.get("segmentKind") in (segment_kind, -1))
                and (segment_alpha == -1 or anchor.values.get("segmentAlpha") in (segment_alpha, -1))
                and (connector_ease == -1 or anchor.values.get("connectorEase") in (connector_ease, -1))
            ):
                if segment_kind != -1 and anchor.values.get("segmentKind") == -1:
                    anchor.set("segmentKind", segment_kind)
                if segment_alpha != -1 and anchor.values.get("segmentAlpha") == -1:
                    anchor.set("segmentAlpha", segment_alpha)
                if connector_ease != -1 and anchor.values.get("connectorEase") == -1:
                    anchor.set("connectorEase", connector_ease)
                positions.add(position)
                anchor_positions[anchor] = positions
                return anchor

        anchor = EntityBuilder("AnchorNote")
        anchor.set("#BEAT", beat)
        anchor.set("lane", lane)
        anchor.set("size", size)
        anchor.set("direction", 0)
        anchor.set("#TIMESCALE_GROUP", anchor_tsg)
        anchor.set("segmentKind", segment_kind)
        anchor.set("segmentAlpha", segment_alpha)
        anchor.set("segmentLayer", 0)
        anchor.set("connectorEase", connector_ease)
        anchor.set("isAttached", 0)
        anchor.set("isSeparator", 0)
        final_entities.append(anchor)
        anchors_by_beat.setdefault(beat, []).append(anchor)
        anchor_positions[anchor] = {position}
        return anchor

    def get_anchor_from_source_ref(
        ref: Any,
        position: str,
        segment_kind: float = -1,
        segment_alpha: float = -1,
        connector_ease: float = -1,
    ) -> Any:
        source = resolve_source_entity(entities, by_name, ref)
        if not isinstance(source, dict):
            return None
        return get_anchor(
            get_num(source, "#BEAT"),
            get_num(source, "lane", 0),
            get_num(source, "size", 0),
            get_tsg_or_default(get_field(source, "timeScaleGroup")),
            position,
            segment_kind,
            segment_alpha,
            connector_ease,
        )

    def get_source_alpha(ref: Any) -> Any:
        source = resolve_source_entity(entities, by_name, ref)
        if not isinstance(source, dict):
            return None
        alpha = get_optional_num(source, "segmentAlpha")
        if alpha is not None:
            return alpha
        return get_optional_num(source, "alpha")

    def get_guide_connector_alphas(entity: Dict[str, Any]) -> Tuple[float, float]:
        fade = get_optional_num(entity, "fade")
        if fade is not None:
            return EXTENDED_FADE_ALPHA_MAPPING.get(int(fade), (1.0, 1.0))

        start_alpha = get_optional_num(entity, "startAlpha")
        if start_alpha is None:
            start_alpha = get_optional_num(entity, "segmentStartAlpha")
        if start_alpha is None:
            start_alpha = get_source_alpha(get_field(entity, "start"))

        end_alpha = get_optional_num(entity, "endAlpha")
        if end_alpha is None:
            end_alpha = get_optional_num(entity, "segmentEndAlpha")
        if end_alpha is None:
            end_alpha = get_source_alpha(get_field(entity, "end"))

        return (
            float(start_alpha) if start_alpha is not None else 1.0,
            float(end_alpha) if end_alpha is not None else 0.0,
        )

    for index, entity in guide_connector_source_entities:
        ease = EXTENDED_EASE_TYPE_MAPPING.get(int(get_num(entity, "ease", 0)), 1)
        kind = PROSEKA_R_GUIDE_ARCHETYPE_KIND.get(entity.get("archetype"), 103)
        start_alpha, end_alpha = get_guide_connector_alphas(entity)
        start = get_anchor_from_source_ref(get_field(entity, "start"), f"proseka_r_guide_segment_head:{index}", kind, start_alpha)
        end = get_anchor_from_source_ref(get_field(entity, "end"), f"proseka_r_guide_segment_tail:{index}", kind, end_alpha)
        head = get_anchor_from_source_ref(get_field(entity, "head"), "proseka_r_guide_head", kind, -1, ease)
        tail = get_anchor_from_source_ref(get_field(entity, "tail"), "proseka_r_guide_tail", kind)
        if not (start and end and head and tail):
            continue
        connector = EntityBuilder("Connector")
        connector.set("head", head)
        connector.set("tail", tail)
        connector.set("segmentHead", start)
        connector.set("segmentTail", end)
        final_entities.append(connector)

    for _, entity in by_archetype.get("Guide", []):
        start_tsg = get_tsg_or_default(get_field(entity, "startTimeScaleGroup"))
        head_tsg = get_tsg_or_default(get_field(entity, "headTimeScaleGroup"))
        tail_tsg = get_tsg_or_default(get_field(entity, "tailTimeScaleGroup"))
        end_tsg = get_tsg_or_default(get_field(entity, "endTimeScaleGroup"))

        ease = EXTENDED_EASE_TYPE_MAPPING.get(int(get_num(entity, "ease", 0)), 1)
        start_alpha, end_alpha = EXTENDED_FADE_ALPHA_MAPPING.get(int(get_num(entity, "fade", 1)), (1.0, 1.0))
        kind = EXTENDED_GUIDE_KIND_MAPPING.get(int(get_num(entity, "color", 0)), 101)

        start = get_anchor(
            get_num(entity, "startBeat"),
            get_num(entity, "startLane"),
            get_num(entity, "startSize"),
            start_tsg,
            "segment_head",
            kind,
            start_alpha,
        )
        end = get_anchor(
            get_num(entity, "endBeat"),
            get_num(entity, "endLane"),
            get_num(entity, "endSize"),
            end_tsg,
            "segment_tail",
            kind,
            end_alpha,
        )
        head = get_anchor(
            get_num(entity, "headBeat"),
            get_num(entity, "headLane"),
            get_num(entity, "headSize"),
            head_tsg,
            "head",
            kind,
            -1,
            ease,
        )
        tail = get_anchor(
            get_num(entity, "tailBeat"),
            get_num(entity, "tailLane"),
            get_num(entity, "tailSize"),
            tail_tsg,
            "tail",
            kind,
        )
        connector = EntityBuilder("Connector")
        connector.set("head", head)
        connector.set("tail", tail)
        connector.set("segmentHead", start)
        connector.set("segmentTail", end)
        final_entities.append(connector)

    for anchors in anchors_by_beat.values():
        for anchor in anchors:
            if anchor.values.get("segmentKind") == -1:
                anchor.set("segmentKind", 101)
            if anchor.values.get("segmentAlpha") == -1:
                anchor.set("segmentAlpha", 1.0)
            if anchor.values.get("connectorEase") == -1:
                anchor.set("connectorEase", 1)

    final_entities.sort(key=lambda entity: (0 if entity.archetype == "Initialization" else 1, entity.beat()))

    for entity in final_entities:
        if entity.archetype != "Connector":
            continue
        head = entity.refs.get("head")
        tail = entity.refs.get("tail")
        if head and tail:
            head.set("next", tail)

    entity_to_name = {entity: format(index, "x") for index, entity in enumerate(final_entities)}
    serialized_entities: List[Dict[str, Any]] = []
    for entity in final_entities:
        data: List[Dict[str, Any]] = []
        for name, value in entity.values.items():
            data.append({"name": name, "value": value})
        for name, ref_entity in entity.refs.items():
            data.append({"name": name, "ref": entity_to_name[ref_entity]})
        serialized_entities.append(
            {
                "archetype": entity.archetype,
                "name": entity_to_name[entity],
                "data": data,
            }
        )

    return {
        "bgmOffset": level_data.get("bgmOffset", 0),
        "entities": serialized_entities,
    }


def decode_level_data_blob(blob: bytes) -> Dict[str, Any]:
    try:
        raw = gzip.decompress(blob)
    except OSError:
        raw = blob
    doc = json.loads(raw.decode("utf-8"))
    if not isinstance(doc, dict):
        raise ValueError("LevelData is not a JSON object")
    return doc


def encode_level_data_blob(level_data: Dict[str, Any]) -> bytes:
    raw = dump_json(level_data)
    return gzip.compress(raw, compresslevel=9, mtime=0)


def update_level_data_hashes_in_doc(doc: Any, hash_map: Dict[str, str]) -> Tuple[Any, int]:
    changed = 0
    if isinstance(doc, dict):
        new_doc = dict(doc)
        data_ref = new_doc.get("data")
        if isinstance(data_ref, dict):
            old_hash = data_ref.get("hash")
            if isinstance(old_hash, str) and old_hash in hash_map:
                new_data_ref = dict(data_ref)
                new_hash = hash_map[old_hash]
                new_data_ref["hash"] = new_hash
                url = new_data_ref.get("url")
                if isinstance(url, str) and url.startswith("/sonolus/repository/"):
                    new_data_ref["url"] = f"/sonolus/repository/{new_hash}"
                new_doc["data"] = new_data_ref
                changed += 1
        for key, value in list(new_doc.items()):
            if key == "data" and isinstance(value, dict):
                continue
            new_value, nested_changed = update_level_data_hashes_in_doc(value, hash_map)
            if nested_changed:
                new_doc[key] = new_value
                changed += nested_changed
        return new_doc, changed

    if isinstance(doc, list):
        new_items = []
        for item in doc:
            new_item, nested_changed = update_level_data_hashes_in_doc(item, hash_map)
            new_items.append(new_item)
            changed += nested_changed
        return new_items, changed

    return doc, 0


def convert_level_data_entries(entries: "OrderedDict[str, bytes]") -> List[Dict[str, Any]]:
    hashes: "OrderedDict[str, List[str]]" = OrderedDict()
    for location, item in iter_level_metadata_items(entries):
        data_ref = item.get("data")
        if not isinstance(data_ref, dict):
            continue
        data_hash = data_ref.get("hash")
        if isinstance(data_hash, str):
            hashes.setdefault(data_hash, []).append(location)

    hash_map: Dict[str, str] = {}
    results: List[Dict[str, Any]] = []

    for old_hash, locations in hashes.items():
        repository_path = f"sonolus/repository/{old_hash}"
        blob = entries.get(repository_path)
        if blob is None:
            results.append({"hash": old_hash, "action": "missing", "locations": locations})
            continue

        try:
            level_data = decode_level_data_blob(blob)
        except Exception as e:
            results.append({"hash": old_hash, "action": "decode-failed", "error": str(e), "locations": locations})
            continue

        if is_next_rush_level_data(level_data):
            results.append({"hash": old_hash, "action": "already-target-format", "locations": locations})
            continue
        if not is_convertible_extended_level_data(level_data):
            results.append({"hash": old_hash, "action": "unsupported-format", "locations": locations})
            continue

        try:
            converted = convert_extended_level_data(level_data)
            new_blob = encode_level_data_blob(converted)
        except Exception as e:
            results.append({"hash": old_hash, "action": "conversion-failed", "error": str(e), "locations": locations})
            continue

        new_hash = hashlib.sha1(new_blob).hexdigest()
        entries[f"sonolus/repository/{new_hash}"] = new_blob
        hash_map[old_hash] = new_hash
        results.append(
            {
                "hash": old_hash,
                "new_hash": new_hash,
                "action": "converted",
                "entities_before": len(level_data.get("entities", [])),
                "entities_after": len(converted.get("entities", [])),
                "locations": locations,
            }
        )

    if hash_map:
        for path in list(category_item_paths(entries, LEVEL_CATEGORY)) + ["sonolus/levels/list", "sonolus/levels/info"]:
            doc = load_json(entries, path, None)
            if doc is None:
                continue
            new_doc, changed = update_level_data_hashes_in_doc(doc, hash_map)
            if changed:
                entries[path] = dump_json(new_doc)

    return results

