from __future__ import annotations

import gzip
import hashlib
import json
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


def convert_extended_level_data(level_data: Dict[str, Any]) -> Dict[str, Any]:
    entities = level_data.get("entities")
    if not isinstance(entities, list):
        raise ValueError("LevelData does not contain an entities list")

    by_archetype, by_name = build_entity_indexes(entities)
    final_entities: List[EntityBuilder] = []

    default_tsg = EntityBuilder("#TIMESCALE_GROUP")
    final_entities.append(default_tsg)

    init = EntityBuilder("Initialization")
    final_entities.append(init)

    for _, entity in by_archetype.get("#BPM_CHANGE", []):
        bpm = EntityBuilder("#BPM_CHANGE")
        bpm.set("#BEAT", get_num(entity, "#BEAT"))
        bpm.set("#BPM", get_num(entity, "#BPM"))
        final_entities.append(bpm)

    timescale_groups_by_index: Dict[int, EntityBuilder] = {}
    timescale_groups_by_name: Dict[str, EntityBuilder] = {}

    def emit_timescale_changes(group: EntityBuilder, source_changes: Sequence[Dict[str, Any]]) -> None:
        changes: List[EntityBuilder] = []
        for raw_change in source_changes:
            change = EntityBuilder("#TIMESCALE_CHANGE")
            change.set("#BEAT", get_num(raw_change, "#BEAT"))
            change.set("#TIMESCALE", get_num(raw_change, "timeScale", get_num(raw_change, "#TIMESCALE", 1)))
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

    source_timescale_groups = by_archetype.get("TimeScaleGroup", [])
    if source_timescale_groups:
        default_change = {
            "data": [
                {"name": "#BEAT", "value": 0},
                {"name": "#TIMESCALE", "value": 1},
            ]
        }
        emit_timescale_changes(default_tsg, [default_change])

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
            emit_timescale_changes(group, source_changes)
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

    def get_tsg(ref: Any) -> EntityBuilder:
        if isinstance(ref, int):
            return timescale_groups_by_index.get(ref, default_tsg)
        if isinstance(ref, str):
            return timescale_groups_by_name.get(ref, default_tsg)
        return default_tsg

    notes_by_index: Dict[int, EntityBuilder] = {}
    notes_by_name: Dict[str, EntityBuilder] = {}
    connectors_by_index: Dict[int, EntityBuilder] = {}
    connectors_by_name: Dict[str, EntityBuilder] = {}

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

    for index, entity in note_source_entities:
        source_archetype = str(entity.get("archetype"))
        target_archetype = EXTENDED_NOTE_TYPE_MAPPING[source_archetype]
        note = EntityBuilder(target_archetype)
        note.set("#BEAT", get_num(entity, "#BEAT"))
        note.set("lane", get_num(entity, "lane", 0))
        note.set("size", get_num(entity, "size", 0))
        note.set("direction", EXTENDED_FLICK_DIRECTION_MAPPING.get(int(get_num(entity, "direction", 0)), 0))
        note.set("segmentKind", 1)
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

    for index, entity in connector_source_entities:
        start_ref = get_field(entity, "start")
        head_ref = get_field(entity, "head")
        tail_ref = get_field(entity, "tail")
        end_ref = get_field(entity, "end")

        head = get_note(head_ref)
        tail = get_note(tail_ref)
        segment_head = get_note(start_ref)
        segment_tail = get_note(end_ref)

        if segment_tail is None:
            ultimate_tail_ref = tail_ref
            visited = set()
            while ultimate_tail_ref is not None and ultimate_tail_ref not in visited:
                visited.add(ultimate_tail_ref)
                next_connector = None
                for _, candidate in connector_source_entities:
                    if get_field(candidate, "head") == ultimate_tail_ref and get_field(candidate, "start") == start_ref:
                        next_connector = candidate
                        break
                if next_connector is None:
                    break
                ultimate_tail_ref = get_field(next_connector, "tail")
            segment_tail = get_note(ultimate_tail_ref)

        if segment_tail is None:
            segment_tail = tail
        if not (head and tail and segment_head and segment_tail):
            continue

        source_archetype = str(entity.get("archetype"))
        connector_kind = EXTENDED_ACTIVE_CONNECTOR_KIND_MAPPING[source_archetype]
        ease = EXTENDED_EASE_TYPE_MAPPING.get(int(get_num(entity, "ease", 0)), 1)

        connector = EntityBuilder("Connector")
        connector.set("head", head)
        connector.set("tail", tail)
        connector.set("segmentHead", segment_head)
        connector.set("segmentTail", segment_tail)
        connector.set("activeHead", segment_head)
        connector.set("activeTail", segment_tail)

        for connector_note in (head, tail, segment_head, segment_tail):
            connector_note.set("segmentKind", connector_kind)
            connector_note.set("segmentAlpha", 1)
        head.set("connectorEase", ease)
        tail.set("connectorEase", ease)

        final_entities.append(connector)
        connectors_by_index[index] = connector
        name = entity.get("name")
        if isinstance(name, str):
            connectors_by_name[name] = connector

    def get_connector(ref: Any) -> Any:
        if isinstance(ref, int):
            return connectors_by_index.get(ref)
        if isinstance(ref, str):
            return connectors_by_name.get(ref)
        return None

    for index, note in notes_by_index.items():
        source = entities[index]
        note.set("#TIMESCALE_GROUP", get_tsg(get_field(source, "timeScaleGroup")))

        attach_ref = get_field(source, "attach")
        attach_connector = get_connector(attach_ref)
        if isinstance(attach_connector, EntityBuilder) and "head" in attach_connector.refs and "tail" in attach_connector.refs:
            note.set("attachHead", attach_connector.refs["head"])
            note.set("attachTail", attach_connector.refs["tail"])
            note.set("isAttached", 1)

        slide_ref = get_field(source, "slide")
        slide_connector = get_connector(slide_ref)
        if isinstance(slide_connector, EntityBuilder) and "activeHead" in slide_connector.refs:
            note.set("activeHead", slide_connector.refs["activeHead"])

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
        tsg: EntityBuilder,
        position: str,
        segment_kind: float = -1,
        segment_alpha: float = -1,
        connector_ease: float = -1,
    ) -> EntityBuilder:
        anchors = anchors_by_beat.get(beat, [])
        for anchor in anchors:
            positions = anchor_positions.get(anchor, set())
            if position in positions:
                continue
            if (
                anchor.values.get("lane") == lane
                and anchor.values.get("size") == size
                and anchor.refs.get("#TIMESCALE_GROUP") is tsg
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
        anchor.set("#TIMESCALE_GROUP", tsg)
        anchor.set("segmentKind", segment_kind)
        anchor.set("segmentAlpha", segment_alpha)
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
            get_tsg(get_field(source, "timeScaleGroup")),
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
            float(end_alpha) if end_alpha is not None else 1.0,
        )

    for index, entity in guide_connector_source_entities:
        ease = EXTENDED_EASE_TYPE_MAPPING.get(int(get_num(entity, "ease", 0)), 1)
        kind = 101
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
        start_tsg = get_tsg(get_field(entity, "startTimeScaleGroup"))
        head_tsg = get_tsg(get_field(entity, "headTimeScaleGroup"))
        tail_tsg = get_tsg(get_field(entity, "tailTimeScaleGroup"))
        end_tsg = get_tsg(get_field(entity, "endTimeScaleGroup"))

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

