(function (root, factory) {
  if (typeof module !== "undefined" && typeof module.exports === "object") {
    module.exports = factory(root, require("./vendor/fflate.js"));
    return;
  }
  root.SonolusRepackLevelData = factory(root, root.fflate);
})(typeof globalThis !== "undefined" ? globalThis : this, function (root, fflate) {
  "use strict";

  if (!fflate) {
    throw new Error("fflate is required before loading repack-leveldata.js");
  }

  var gzipSync = fflate.gzipSync;
  var gunzipSync = fflate.gunzipSync;
  var LEVEL_CATEGORY = "levels";
  var textDecoder = new TextDecoder("utf-8");
  var textEncoder = new TextEncoder();

  var EXTENDED_NOTE_TYPE_MAPPING = {
    NormalTapNote: "NormalTapNote",
    CriticalTapNote: "CriticalTapNote",
    NormalFlickNote: "NormalFlickNote",
    CriticalFlickNote: "CriticalFlickNote",
    NormalSlideStartNote: "NormalHeadTapNote",
    CriticalSlideStartNote: "CriticalHeadTapNote",
    NormalSlideEndNote: "NormalTailReleaseNote",
    CriticalSlideEndNote: "CriticalTailReleaseNote",
    NormalSlideEndFlickNote: "NormalTailFlickNote",
    CriticalSlideEndFlickNote: "CriticalTailFlickNote",
    IgnoredSlideTickNote: "TransientHiddenTickNote",
    NormalSlideTickNote: "NormalTickNote",
    CriticalSlideTickNote: "CriticalTickNote",
    HiddenSlideTickNote: "AnchorNote",
    NormalAttachedSlideTickNote: "NormalTickNote",
    CriticalAttachedSlideTickNote: "CriticalTickNote",
    NormalTraceNote: "NormalTraceNote",
    CriticalTraceNote: "CriticalTraceNote",
    DamageNote: "DamageNote",
    NormalTraceFlickNote: "NormalTraceFlickNote",
    CriticalTraceFlickNote: "CriticalTraceFlickNote",
    NonDirectionalTraceFlickNote: "NormalTraceFlickNote",
    HiddenSlideStartNote: "AnchorNote",
    NormalSlideTraceNote: "NormalHeadTraceNote",
    CriticalSlideTraceNote: "CriticalHeadTraceNote",
    NormalSlideEndTraceNote: "NormalTailTraceNote",
    CriticalSlideEndTraceNote: "CriticalTailTraceNote",
    NormalTraceSlideStartNote: "NormalHeadTraceNote",
    CriticalTraceSlideStartNote: "CriticalHeadTraceNote",
    NormalTraceSlideEndNote: "NormalTailTraceNote",
    CriticalTraceSlideEndNote: "CriticalTailTraceNote",
  };
  var EXTENDED_ACTIVE_CONNECTOR_KIND_MAPPING = {
    // PJSekai+ uses bare connector names for active slides. ProSeka R also uses
    // bare names for guides, which are filtered before regular slide conversion.
    NormalSlideConnector: 1,
    CriticalSlideConnector: 2,
    NormalActiveSlideConnector: 1,
    CriticalActiveSlideConnector: 2,
  };
  var EXTENDED_FLICK_DIRECTION_MAPPING = {
    "-1": 1,
    0: 0,
    1: 2,
  };
  var EXTENDED_EASE_TYPE_MAPPING = {
    "-2": 5,
    "-1": 3,
    0: 1,
    1: 2,
    2: 4,
  };
  var EXTENDED_FADE_ALPHA_MAPPING = {
    0: [1, 0],
    1: [1, 1],
    2: [0, 1],
  };
  var EXTENDED_GUIDE_KIND_MAPPING = {
    0: 101,
    1: 102,
    2: 103,
    3: 104,
    4: 105,
    5: 106,
    6: 107,
    7: 108,
  };

  function deepCopy(value) {
    if (value === null || value === undefined) {
      return value;
    }
    if (typeof structuredClone === "function") {
      return structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
  }

  function sha1Hex(bytes) {
    var bitLength = bytes.length * 8;
    var paddedLength = bytes.length + 1;
    while (paddedLength % 64 !== 56) {
      paddedLength += 1;
    }

    var padded = new Uint8Array(paddedLength + 8);
    padded.set(bytes);
    padded[bytes.length] = 0x80;

    var high = Math.floor(bitLength / 0x100000000);
    var low = bitLength >>> 0;
    for (var index = 0; index < 4; index += 1) {
      padded[paddedLength + index] = (high >>> (24 - index * 8)) & 0xff;
      padded[paddedLength + 4 + index] = (low >>> (24 - index * 8)) & 0xff;
    }

    var h0 = 0x67452301;
    var h1 = 0xefcdab89;
    var h2 = 0x98badcfe;
    var h3 = 0x10325476;
    var h4 = 0xc3d2e1f0;
    var words = new Uint32Array(80);

    function rotl(value, bits) {
      return ((value << bits) | (value >>> (32 - bits))) >>> 0;
    }

    for (var offset = 0; offset < padded.length; offset += 64) {
      for (var w = 0; w < 16; w += 1) {
        var i = offset + w * 4;
        words[w] = ((padded[i] << 24) | (padded[i + 1] << 16) | (padded[i + 2] << 8) | padded[i + 3]) >>> 0;
      }
      for (w = 16; w < 80; w += 1) {
        words[w] = rotl(words[w - 3] ^ words[w - 8] ^ words[w - 14] ^ words[w - 16], 1);
      }

      var a = h0;
      var b = h1;
      var c = h2;
      var d = h3;
      var e = h4;

      for (w = 0; w < 80; w += 1) {
        var f;
        var k;
        if (w < 20) {
          f = (b & c) | (~b & d);
          k = 0x5a827999;
        } else if (w < 40) {
          f = b ^ c ^ d;
          k = 0x6ed9eba1;
        } else if (w < 60) {
          f = (b & c) | (b & d) | (c & d);
          k = 0x8f1bbcdc;
        } else {
          f = b ^ c ^ d;
          k = 0xca62c1d6;
        }
        var temp = (rotl(a, 5) + f + e + k + words[w]) >>> 0;
        e = d;
        d = c;
        c = rotl(b, 30);
        b = a;
        a = temp;
      }

      h0 = (h0 + a) >>> 0;
      h1 = (h1 + b) >>> 0;
      h2 = (h2 + c) >>> 0;
      h3 = (h3 + d) >>> 0;
      h4 = (h4 + e) >>> 0;
    }

    return [h0, h1, h2, h3, h4]
      .map(function (value) {
        return ("00000000" + value.toString(16)).slice(-8);
      })
      .join("");
  }

  function loadJson(entries, path, defaultValue) {
    if (!entries.has(path)) {
      return defaultValue;
    }
    try {
      return JSON.parse(textDecoder.decode(entries.get(path)));
    } catch (error) {
      throw new Error("Failed to parse JSON entry " + path + ": " + error.message);
    }
  }

  function dumpJson(value) {
    return textEncoder.encode(JSON.stringify(value));
  }

  function itemFromDoc(doc) {
    if (doc && typeof doc === "object" && doc.item && typeof doc.item === "object" && !Array.isArray(doc.item)) {
      return doc.item;
    }
    if (doc && typeof doc === "object" && !Array.isArray(doc)) {
      return doc;
    }
    throw new Error("JSON document is not an object or {item: object}");
  }

  function categoryItemPaths(entries, category) {
    var prefix = "sonolus/" + category + "/";
    var skip = new Set(["sonolus/" + category + "/list", "sonolus/" + category + "/info"]);
    return Array.from(entries.keys()).filter(function (path) {
      return path.indexOf(prefix) === 0 && !skip.has(path);
    });
  }

  function iterLevelSectionItems(doc, prefix, callback) {
    if (!doc || typeof doc !== "object" || !Array.isArray(doc.sections)) {
      return;
    }

    doc.sections.forEach(function (section, sectionIndex) {
      if (!section || typeof section !== "object" || !Array.isArray(section.items)) {
        return;
      }
      section.items.forEach(function (item, itemIndex) {
        if (item && typeof item === "object" && Object.prototype.hasOwnProperty.call(item, "engine")) {
          var location = prefix + "[" + sectionIndex + "][" + itemIndex + "]";
          callback(location, item);
          iterLevelSectionItems(item, location + ".sections", callback);
        }
      });
    });
  }

  function iterLevelMetadataItems(entries, callback) {
    categoryItemPaths(entries, LEVEL_CATEGORY).forEach(function (path) {
      var doc = loadJson(entries, path, null);
      if (doc === null) {
        return;
      }
      var item = itemFromDoc(doc);
      if (item && typeof item === "object" && Object.prototype.hasOwnProperty.call(item, "engine")) {
        callback(path, item);
      }
      iterLevelSectionItems(doc, path + ".sections", callback);
    });

    var listDoc = loadJson(entries, "sonolus/levels/list", null);
    if (listDoc && typeof listDoc === "object" && Array.isArray(listDoc.items)) {
      listDoc.items.forEach(function (item, index) {
        if (item && typeof item === "object" && Object.prototype.hasOwnProperty.call(item, "engine")) {
          callback("sonolus/levels/list[" + index + "]", item);
        }
      });
    }

    var infoDoc = loadJson(entries, "sonolus/levels/info", null);
    iterLevelSectionItems(infoDoc, "sonolus/levels/info", callback);
  }

  function EntityBuilder(archetype) {
    this.archetype = archetype;
    this.values = new Map();
    this.refs = new Map();
  }

  EntityBuilder.prototype.set = function (key, value) {
    if (value === undefined || value === null) {
      return;
    }
    if (value instanceof EntityBuilder) {
      this.refs.set(key, value);
    } else if (typeof value === "number" && Number.isFinite(value)) {
      this.values.set(key, value);
    }
  };

  EntityBuilder.prototype.beat = function () {
    return this.values.has("#BEAT") ? this.values.get("#BEAT") : -1;
  };

  function entityDataMap(entity) {
    var result = new Map();
    if (!entity || typeof entity !== "object" || !Array.isArray(entity.data)) {
      return result;
    }
    entity.data.forEach(function (field) {
      if (!field || typeof field !== "object" || typeof field.name !== "string") {
        return;
      }
      if (Object.prototype.hasOwnProperty.call(field, "value")) {
        result.set(field.name, field.value);
      } else if (Object.prototype.hasOwnProperty.call(field, "ref")) {
        result.set(field.name, field.ref);
      }
    });
    return result;
  }

  function getField(entity, name) {
    return entityDataMap(entity).get(name);
  }

  function hasField(entity, name) {
    return entityDataMap(entity).has(name);
  }

  function getOptionalNum(entity, name) {
    var value = getField(entity, name);
    return typeof value === "number" && Number.isFinite(value) ? value : undefined;
  }

  function getNum(entity, name, defaultValue) {
    var value = getField(entity, name);
    return typeof value === "number" && Number.isFinite(value) ? value : defaultValue || 0;
  }

  function buildEntityIndexes(entities) {
    var byArchetype = new Map();
    var byName = new Map();
    entities.forEach(function (entity, index) {
      if (!entity || typeof entity !== "object") {
        return;
      }
      if (typeof entity.archetype === "string") {
        if (!byArchetype.has(entity.archetype)) {
          byArchetype.set(entity.archetype, []);
        }
        byArchetype.get(entity.archetype).push({ index: index, entity: entity });
      }
      if (typeof entity.name === "string") {
        byName.set(entity.name, entity);
      }
    });
    return { byArchetype: byArchetype, byName: byName };
  }

  function resolveSourceEntity(entities, byName, ref) {
    if (typeof ref === "number" && ref >= 0 && ref < entities.length) {
      return entities[ref];
    }
    if (typeof ref === "string") {
      if (byName.has(ref)) {
        return byName.get(ref);
      }
      var index = Number(ref);
      if (Number.isInteger(index) && index >= 0 && index < entities.length) {
        return entities[index];
      }
    }
    return undefined;
  }

  function isNextRushLevelData(levelData) {
    return Boolean(
      levelData &&
        typeof levelData === "object" &&
        Array.isArray(levelData.entities) &&
        levelData.entities.some(function (entity) {
          return entity && typeof entity === "object" && entity.archetype === "#TIMESCALE_GROUP";
        })
    );
  }

  function isConvertibleExtendedLevelData(levelData) {
    if (!levelData || typeof levelData !== "object" || !Array.isArray(levelData.entities)) {
      return false;
    }
    if (isNextRushLevelData(levelData)) {
      return false;
    }
    return levelData.entities.some(function (entity) {
      if (!entity || typeof entity !== "object") {
        return false;
      }
      return (
        Object.prototype.hasOwnProperty.call(EXTENDED_NOTE_TYPE_MAPPING, entity.archetype) ||
        Object.prototype.hasOwnProperty.call(EXTENDED_ACTIVE_CONNECTOR_KIND_MAPPING, entity.archetype) ||
        entity.archetype === "TimeScaleGroup" ||
        entity.archetype === "#TIMESCALE_CHANGE"
      );
    });
  }

  function convertExtendedLevelData(levelData) {
    if (!levelData || typeof levelData !== "object" || !Array.isArray(levelData.entities)) {
      throw new Error("LevelData does not contain an entities list");
    }

    var entities = levelData.entities;
    var indexes = buildEntityIndexes(entities);
    var byArchetype = indexes.byArchetype;
    var byName = indexes.byName;
    var finalEntities = [];

    var defaultTsg = new EntityBuilder("#TIMESCALE_GROUP");
    finalEntities.push(defaultTsg);
    finalEntities.push(new EntityBuilder("Initialization"));

    (byArchetype.get("#BPM_CHANGE") || []).forEach(function (entry) {
      var bpm = new EntityBuilder("#BPM_CHANGE");
      bpm.set("#BEAT", getNum(entry.entity, "#BEAT", 0));
      bpm.set("#BPM", getNum(entry.entity, "#BPM", 0));
      finalEntities.push(bpm);
    });

    var timescaleGroupsByIndex = new Map();
    var timescaleGroupsByName = new Map();

    function emitTimescaleChanges(group, sourceChanges) {
      var changes = [];
      sourceChanges.forEach(function (rawChange) {
        var change = new EntityBuilder("#TIMESCALE_CHANGE");
        change.set("#BEAT", getNum(rawChange, "#BEAT", 0));
        change.set("#TIMESCALE", getNum(rawChange, "timeScale", getNum(rawChange, "#TIMESCALE", 1)));
        change.set("#TIMESCALE_SKIP", getNum(rawChange, "#TIMESCALE_SKIP", 0));
        change.set("#TIMESCALE_GROUP", group);
        change.set("#TIMESCALE_EASE", getNum(rawChange, "#TIMESCALE_EASE", 0));
        change.set("hideNotes", getNum(rawChange, "hideNotes", 0));
        if (changes.length) {
          changes[changes.length - 1].set("next", change);
        }
        changes.push(change);
      });
      if (changes.length) {
        group.set("first", changes[0]);
        finalEntities.push.apply(finalEntities, changes);
      }
    }

    var sourceTimescaleGroups = byArchetype.get("TimeScaleGroup") || [];
    if (sourceTimescaleGroups.length) {
      emitTimescaleChanges(defaultTsg, [{ data: [{ name: "#BEAT", value: 0 }, { name: "#TIMESCALE", value: 1 }] }]);

      sourceTimescaleGroups.forEach(function (entry) {
        var group = new EntityBuilder("#TIMESCALE_GROUP");
        finalEntities.push(group);
        timescaleGroupsByIndex.set(entry.index, group);
        if (typeof entry.entity.name === "string") {
          timescaleGroupsByName.set(entry.entity.name, group);
        }

        var rawRef = getField(entry.entity, "first");
        var sourceChanges = [];
        var seenRefs = new Set();
        while (rawRef !== undefined && !seenRefs.has(rawRef)) {
          seenRefs.add(rawRef);
          var rawChange = resolveSourceEntity(entities, byName, rawRef);
          if (!rawChange) {
            break;
          }
          sourceChanges.push(rawChange);
          var nextRef = getField(rawChange, "next");
          if (typeof nextRef === "number" && nextRef <= 0) {
            break;
          }
          rawRef = nextRef;
        }
        emitTimescaleChanges(group, sourceChanges);
      });
    } else {
      var sourceChanges = (byArchetype.get("#TIMESCALE_CHANGE") || [])
        .map(function (entry) {
          return entry.entity;
        })
        .sort(function (left, right) {
          return getNum(left, "#BEAT", 0) - getNum(right, "#BEAT", 0);
        });
      if (!sourceChanges.length) {
        sourceChanges = [{ data: [{ name: "#BEAT", value: 0 }, { name: "#TIMESCALE", value: 1 }] }];
      }
      emitTimescaleChanges(defaultTsg, sourceChanges);
    }

    function getTsg(ref) {
      if (typeof ref === "number" && timescaleGroupsByIndex.has(ref)) {
        return timescaleGroupsByIndex.get(ref);
      }
      if (typeof ref === "string" && timescaleGroupsByName.has(ref)) {
        return timescaleGroupsByName.get(ref);
      }
      return defaultTsg;
    }

    var notesByIndex = new Map();
    var notesByName = new Map();
    var connectorsByIndex = new Map();
    var connectorsByName = new Map();
    var noteSourceEntities = [];
    var connectorSourceEntities = [];
    var sourceArchetypes = new Set();

    entities.forEach(function (entity) {
      if (entity && typeof entity === "object") {
        sourceArchetypes.add(entity.archetype);
      }
    });

    var bareConnectorArchetypes = new Set(["NormalSlideConnector", "CriticalSlideConnector"]);
    var prosekaRActiveConnectorArchetypes = new Set(["NormalActiveSlideConnector", "CriticalActiveSlideConnector"]);
    var bareConnectorEntities = [];
    bareConnectorArchetypes.forEach(function (archetype) {
      (byArchetype.get(archetype) || []).forEach(function (entry) {
        bareConnectorEntities.push(entry.entity);
      });
    });

    var hasProsekaRActiveConnector = Array.from(prosekaRActiveConnectorArchetypes).some(function (archetype) {
      return sourceArchetypes.has(archetype);
    });
    var usesProsekaRConnectorSchema =
      hasProsekaRActiveConnector ||
      (bareConnectorEntities.length > 0 &&
        !bareConnectorEntities.some(function (entity) {
          return hasField(entity, "startType");
        }) &&
        !sourceArchetypes.has("TimeScaleGroup"));

    function isProsekaRGuideConnector(entity) {
      return (
        entity &&
        typeof entity === "object" &&
        bareConnectorArchetypes.has(entity.archetype) &&
        usesProsekaRConnectorSchema &&
        !hasField(entity, "startType")
      );
    }

    var guideConnectorSourceEntities = [];
    entities.forEach(function (entity, index) {
      if (isProsekaRGuideConnector(entity)) {
        guideConnectorSourceEntities.push({ index: index, entity: entity });
      }
    });

    var guideNoteRefs = new Set();
    guideConnectorSourceEntities.forEach(function (entry) {
      ["start", "end", "head", "tail"].forEach(function (key) {
        var ref = getField(entry.entity, key);
        if (ref !== undefined && ref !== null) {
          guideNoteRefs.add(ref);
        }
      });
    });

    entities.forEach(function (entity, index) {
      if (!entity || typeof entity !== "object") {
        return;
      }
      var isGuideNote = guideNoteRefs.has(index) || (typeof entity.name === "string" && guideNoteRefs.has(entity.name));
      if (Object.prototype.hasOwnProperty.call(EXTENDED_NOTE_TYPE_MAPPING, entity.archetype) && !isGuideNote) {
        noteSourceEntities.push({ index: index, entity: entity });
      }
      if (
        Object.prototype.hasOwnProperty.call(EXTENDED_ACTIVE_CONNECTOR_KIND_MAPPING, entity.archetype) &&
        !isProsekaRGuideConnector(entity)
      ) {
        connectorSourceEntities.push({ index: index, entity: entity });
      }
    });

    noteSourceEntities.forEach(function (entry) {
      var note = new EntityBuilder(EXTENDED_NOTE_TYPE_MAPPING[entry.entity.archetype]);
      note.set("#BEAT", getNum(entry.entity, "#BEAT", 0));
      note.set("lane", getNum(entry.entity, "lane", 0));
      note.set("size", getNum(entry.entity, "size", 0));
      note.set("direction", EXTENDED_FLICK_DIRECTION_MAPPING[String(getNum(entry.entity, "direction", 0))] || 0);
      note.set("segmentKind", 1);
      note.set("isAttached", 0);
      note.set("connectorEase", 0);
      note.set("isSeparator", 0);
      finalEntities.push(note);
      notesByIndex.set(entry.index, note);
      if (typeof entry.entity.name === "string") {
        notesByName.set(entry.entity.name, note);
      }
    });

    function getNote(ref) {
      if (typeof ref === "number") {
        return notesByIndex.get(ref);
      }
      if (typeof ref === "string") {
        return notesByName.get(ref);
      }
      return undefined;
    }

    connectorSourceEntities.forEach(function (entry) {
      var startRef = getField(entry.entity, "start");
      var head = getNote(getField(entry.entity, "head"));
      var tailRef = getField(entry.entity, "tail");
      var tail = getNote(tailRef);
      var segmentHead = getNote(startRef);
      var segmentTail = getNote(getField(entry.entity, "end"));

      if (!segmentTail) {
        var ultimateTailRef = tailRef;
        var visited = new Set();
        while (ultimateTailRef !== undefined && !visited.has(ultimateTailRef)) {
          visited.add(ultimateTailRef);
          var nextConnector = connectorSourceEntities.find(function (candidate) {
            return getField(candidate.entity, "head") === ultimateTailRef && getField(candidate.entity, "start") === startRef;
          });
          if (!nextConnector) {
            break;
          }
          ultimateTailRef = getField(nextConnector.entity, "tail");
        }
        segmentTail = getNote(ultimateTailRef);
      }

      if (!segmentTail) {
        segmentTail = tail;
      }
      if (!(head && tail && segmentHead && segmentTail)) {
        return;
      }

      var connectorKind = EXTENDED_ACTIVE_CONNECTOR_KIND_MAPPING[entry.entity.archetype];
      var ease = EXTENDED_EASE_TYPE_MAPPING[String(getNum(entry.entity, "ease", 0))] || 1;
      var connector = new EntityBuilder("Connector");
      connector.set("head", head);
      connector.set("tail", tail);
      connector.set("segmentHead", segmentHead);
      connector.set("segmentTail", segmentTail);
      connector.set("activeHead", segmentHead);
      connector.set("activeTail", segmentTail);

      [head, tail, segmentHead, segmentTail].forEach(function (connectorNote) {
        connectorNote.set("segmentKind", connectorKind);
        connectorNote.set("segmentAlpha", 1);
      });
      head.set("connectorEase", ease);
      tail.set("connectorEase", ease);

      finalEntities.push(connector);
      connectorsByIndex.set(entry.index, connector);
      if (typeof entry.entity.name === "string") {
        connectorsByName.set(entry.entity.name, connector);
      }
    });

    function getConnector(ref) {
      if (typeof ref === "number") {
        return connectorsByIndex.get(ref);
      }
      if (typeof ref === "string") {
        return connectorsByName.get(ref);
      }
      return undefined;
    }

    notesByIndex.forEach(function (note, index) {
      var source = entities[index];
      note.set("#TIMESCALE_GROUP", getTsg(getField(source, "timeScaleGroup")));

      var attachConnector = getConnector(getField(source, "attach"));
      if (attachConnector && attachConnector.refs.has("head") && attachConnector.refs.has("tail")) {
        note.set("attachHead", attachConnector.refs.get("head"));
        note.set("attachTail", attachConnector.refs.get("tail"));
        note.set("isAttached", 1);
      }

      var slideConnector = getConnector(getField(source, "slide"));
      if (slideConnector && slideConnector.refs.has("activeHead")) {
        note.set("activeHead", slideConnector.refs.get("activeHead"));
      }
    });

    (byArchetype.get("SimLine") || []).forEach(function (entry) {
      var left = getNote(getField(entry.entity, "a"));
      var right = getNote(getField(entry.entity, "b"));
      if (left && right) {
        var sim = new EntityBuilder("SimLine");
        sim.set("left", left);
        sim.set("right", right);
        finalEntities.push(sim);
      }
    });

    var anchorsByBeat = new Map();
    var anchorPositions = new Map();

    function getAnchor(beat, lane, size, tsg, position, segmentKind, segmentAlpha, connectorEase) {
      segmentKind = segmentKind === undefined ? -1 : segmentKind;
      segmentAlpha = segmentAlpha === undefined ? -1 : segmentAlpha;
      connectorEase = connectorEase === undefined ? -1 : connectorEase;

      var anchors = anchorsByBeat.get(beat) || [];
      for (var index = 0; index < anchors.length; index += 1) {
        var anchor = anchors[index];
        var positions = anchorPositions.get(anchor) || new Set();
        if (positions.has(position)) {
          continue;
        }
        if (
          anchor.values.get("lane") === lane &&
          anchor.values.get("size") === size &&
          anchor.refs.get("#TIMESCALE_GROUP") === tsg &&
          (segmentKind === -1 || anchor.values.get("segmentKind") === segmentKind || anchor.values.get("segmentKind") === -1) &&
          (segmentAlpha === -1 || anchor.values.get("segmentAlpha") === segmentAlpha || anchor.values.get("segmentAlpha") === -1) &&
          (connectorEase === -1 || anchor.values.get("connectorEase") === connectorEase || anchor.values.get("connectorEase") === -1)
        ) {
          if (segmentKind !== -1 && anchor.values.get("segmentKind") === -1) anchor.set("segmentKind", segmentKind);
          if (segmentAlpha !== -1 && anchor.values.get("segmentAlpha") === -1) anchor.set("segmentAlpha", segmentAlpha);
          if (connectorEase !== -1 && anchor.values.get("connectorEase") === -1) anchor.set("connectorEase", connectorEase);
          positions.add(position);
          anchorPositions.set(anchor, positions);
          return anchor;
        }
      }

      var newAnchor = new EntityBuilder("AnchorNote");
      newAnchor.set("#BEAT", beat);
      newAnchor.set("lane", lane);
      newAnchor.set("size", size);
      newAnchor.set("#TIMESCALE_GROUP", tsg);
      newAnchor.set("segmentKind", segmentKind);
      newAnchor.set("segmentAlpha", segmentAlpha);
      newAnchor.set("connectorEase", connectorEase);
      newAnchor.set("isAttached", 0);
      newAnchor.set("isSeparator", 0);
      finalEntities.push(newAnchor);
      if (!anchorsByBeat.has(beat)) anchorsByBeat.set(beat, []);
      anchorsByBeat.get(beat).push(newAnchor);
      anchorPositions.set(newAnchor, new Set([position]));
      return newAnchor;
    }

    function getAnchorFromSourceRef(ref, position, segmentKind, segmentAlpha, connectorEase) {
      var source = resolveSourceEntity(entities, byName, ref);
      if (!source) {
        return undefined;
      }
      return getAnchor(
        getNum(source, "#BEAT", 0),
        getNum(source, "lane", 0),
        getNum(source, "size", 0),
        getTsg(getField(source, "timeScaleGroup")),
        position,
        segmentKind,
        segmentAlpha,
        connectorEase
      );
    }

    function getSourceAlpha(ref) {
      var source = resolveSourceEntity(entities, byName, ref);
      if (!source) {
        return undefined;
      }
      var alpha = getOptionalNum(source, "segmentAlpha");
      if (alpha !== undefined) {
        return alpha;
      }
      return getOptionalNum(source, "alpha");
    }

    function getGuideConnectorAlphas(entity) {
      var fade = getOptionalNum(entity, "fade");
      if (fade !== undefined) {
        return EXTENDED_FADE_ALPHA_MAPPING[String(fade)] || [1, 1];
      }
      var startAlpha = getOptionalNum(entity, "startAlpha");
      if (startAlpha === undefined) startAlpha = getOptionalNum(entity, "segmentStartAlpha");
      if (startAlpha === undefined) startAlpha = getSourceAlpha(getField(entity, "start"));

      var endAlpha = getOptionalNum(entity, "endAlpha");
      if (endAlpha === undefined) endAlpha = getOptionalNum(entity, "segmentEndAlpha");
      if (endAlpha === undefined) endAlpha = getSourceAlpha(getField(entity, "end"));

      return [startAlpha === undefined ? 1 : startAlpha, endAlpha === undefined ? 1 : endAlpha];
    }

    guideConnectorSourceEntities.forEach(function (entry) {
      var entity = entry.entity;
      var ease = EXTENDED_EASE_TYPE_MAPPING[String(getNum(entity, "ease", 0))] || 1;
      var kind = 101;
      var alphas = getGuideConnectorAlphas(entity);
      var start = getAnchorFromSourceRef(getField(entity, "start"), "proseka_r_guide_segment_head:" + entry.index, kind, alphas[0]);
      var end = getAnchorFromSourceRef(getField(entity, "end"), "proseka_r_guide_segment_tail:" + entry.index, kind, alphas[1]);
      var head = getAnchorFromSourceRef(getField(entity, "head"), "proseka_r_guide_head", kind, -1, ease);
      var tail = getAnchorFromSourceRef(getField(entity, "tail"), "proseka_r_guide_tail", kind);
      if (!(start && end && head && tail)) {
        return;
      }
      var connector = new EntityBuilder("Connector");
      connector.set("head", head);
      connector.set("tail", tail);
      connector.set("segmentHead", start);
      connector.set("segmentTail", end);
      finalEntities.push(connector);
    });

    (byArchetype.get("Guide") || []).forEach(function (entry) {
      var entity = entry.entity;
      var fade = EXTENDED_FADE_ALPHA_MAPPING[String(getNum(entity, "fade", 1))] || [1, 1];
      var kind = EXTENDED_GUIDE_KIND_MAPPING[String(getNum(entity, "color", 0))] || 101;
      var ease = EXTENDED_EASE_TYPE_MAPPING[String(getNum(entity, "ease", 0))] || 1;

      var start = getAnchor(
        getNum(entity, "startBeat", 0),
        getNum(entity, "startLane", 0),
        getNum(entity, "startSize", 0),
        getTsg(getField(entity, "startTimeScaleGroup")),
        "segment_head",
        kind,
        fade[0]
      );
      var end = getAnchor(
        getNum(entity, "endBeat", 0),
        getNum(entity, "endLane", 0),
        getNum(entity, "endSize", 0),
        getTsg(getField(entity, "endTimeScaleGroup")),
        "segment_tail",
        kind,
        fade[1]
      );
      var head = getAnchor(
        getNum(entity, "headBeat", 0),
        getNum(entity, "headLane", 0),
        getNum(entity, "headSize", 0),
        getTsg(getField(entity, "headTimeScaleGroup")),
        "head",
        kind,
        -1,
        ease
      );
      var tail = getAnchor(
        getNum(entity, "tailBeat", 0),
        getNum(entity, "tailLane", 0),
        getNum(entity, "tailSize", 0),
        getTsg(getField(entity, "tailTimeScaleGroup")),
        "tail",
        kind
      );
      var connector = new EntityBuilder("Connector");
      connector.set("head", head);
      connector.set("tail", tail);
      connector.set("segmentHead", start);
      connector.set("segmentTail", end);
      finalEntities.push(connector);
    });

    anchorsByBeat.forEach(function (anchors) {
      anchors.forEach(function (anchor) {
        if (anchor.values.get("segmentKind") === -1) anchor.set("segmentKind", 101);
        if (anchor.values.get("segmentAlpha") === -1) anchor.set("segmentAlpha", 1);
        if (anchor.values.get("connectorEase") === -1) anchor.set("connectorEase", 1);
      });
    });

    finalEntities.sort(function (left, right) {
      var initDelta = (left.archetype === "Initialization" ? 0 : 1) - (right.archetype === "Initialization" ? 0 : 1);
      if (initDelta !== 0) return initDelta;
      return left.beat() - right.beat();
    });

    finalEntities.forEach(function (entity) {
      if (entity.archetype !== "Connector") {
        return;
      }
      var head = entity.refs.get("head");
      var tail = entity.refs.get("tail");
      if (head && tail) {
        head.set("next", tail);
      }
    });

    var entityToName = new Map();
    finalEntities.forEach(function (entity, index) {
      entityToName.set(entity, index.toString(16));
    });

    return {
      bgmOffset: levelData.bgmOffset || 0,
      entities: finalEntities.map(function (entity) {
        var data = [];
        entity.values.forEach(function (value, name) {
          data.push({ name: name, value: value });
        });
        entity.refs.forEach(function (refEntity, name) {
          data.push({ name: name, ref: entityToName.get(refEntity) || "" });
        });
        return {
          archetype: entity.archetype,
          name: entityToName.get(entity) || "",
          data: data,
        };
      }),
    };
  }

  function decodeLevelDataBlob(blob) {
    var raw;
    try {
      raw = gunzipSync(blob);
    } catch (error) {
      raw = blob;
    }
    var doc = JSON.parse(textDecoder.decode(raw));
    if (!doc || typeof doc !== "object" || Array.isArray(doc)) {
      throw new Error("LevelData is not a JSON object");
    }
    return doc;
  }

  function encodeLevelDataBlob(levelData) {
    return gzipSync(dumpJson(levelData), { level: 9, mtime: 0 });
  }

  function updateLevelDataHashesInDoc(doc, hashMap) {
    var changed = 0;
    if (Array.isArray(doc)) {
      var newItems = doc.map(function (item) {
        var result = updateLevelDataHashesInDoc(item, hashMap);
        changed += result.changed;
        return result.doc;
      });
      return { doc: changed ? newItems : doc, changed: changed };
    }

    if (!doc || typeof doc !== "object") {
      return { doc: doc, changed: 0 };
    }

    var newDoc = doc;
    if (doc.data && typeof doc.data === "object" && !Array.isArray(doc.data) && hashMap.has(doc.data.hash)) {
      newDoc = deepCopy(doc);
      var newHash = hashMap.get(doc.data.hash);
      newDoc.data.hash = newHash;
      if (typeof newDoc.data.url === "string" && newDoc.data.url.indexOf("/sonolus/repository/") === 0) {
        newDoc.data.url = "/sonolus/repository/" + newHash;
      }
      changed += 1;
    }

    Object.keys(newDoc).forEach(function (key) {
      if (key === "data" && newDoc[key] && typeof newDoc[key] === "object" && !Array.isArray(newDoc[key])) {
        return;
      }
      var result = updateLevelDataHashesInDoc(newDoc[key], hashMap);
      if (result.changed) {
        if (newDoc === doc) newDoc = deepCopy(doc);
        newDoc[key] = result.doc;
        changed += result.changed;
      }
    });

    return { doc: newDoc, changed: changed };
  }

  function convertLevelDataEntries(entries) {
    var hashes = new Map();
    iterLevelMetadataItems(entries, function (location, item) {
      if (item.data && typeof item.data === "object" && typeof item.data.hash === "string") {
        if (!hashes.has(item.data.hash)) hashes.set(item.data.hash, []);
        hashes.get(item.data.hash).push(location);
      }
    });

    var hashMap = new Map();
    var results = [];
    hashes.forEach(function (locations, oldHash) {
      var repositoryPath = "sonolus/repository/" + oldHash;
      var blob = entries.get(repositoryPath);
      if (!blob) {
        results.push({ hash: oldHash, action: "missing", locations: locations });
        return;
      }

      var levelData;
      try {
        levelData = decodeLevelDataBlob(blob);
      } catch (error) {
        results.push({ hash: oldHash, action: "decode-failed", error: error.message, locations: locations });
        return;
      }

      if (isNextRushLevelData(levelData)) {
        results.push({ hash: oldHash, action: "already-target-format", locations: locations });
        return;
      }
      if (!isConvertibleExtendedLevelData(levelData)) {
        results.push({ hash: oldHash, action: "unsupported-format", locations: locations });
        return;
      }

      var converted;
      var newBlob;
      try {
        converted = convertExtendedLevelData(levelData);
        newBlob = encodeLevelDataBlob(converted);
      } catch (error) {
        results.push({ hash: oldHash, action: "conversion-failed", error: error.message, locations: locations });
        return;
      }

      var newHash = sha1Hex(newBlob);
      entries.set("sonolus/repository/" + newHash, newBlob);
      hashMap.set(oldHash, newHash);
      results.push({
        hash: oldHash,
        newHash: newHash,
        action: "converted",
        entitiesBefore: Array.isArray(levelData.entities) ? levelData.entities.length : 0,
        entitiesAfter: converted.entities.length,
        locations: locations,
      });
    });

    if (hashMap.size) {
      categoryItemPaths(entries, LEVEL_CATEGORY)
        .concat(["sonolus/levels/list", "sonolus/levels/info"])
        .forEach(function (path) {
          var doc = loadJson(entries, path, null);
          if (doc === null) {
            return;
          }
          var result = updateLevelDataHashesInDoc(doc, hashMap);
          if (result.changed) {
            entries.set(path, dumpJson(result.doc));
          }
        });
    }

    return results;
  }

  return {
    convertExtendedLevelData: convertExtendedLevelData,
    convertLevelDataEntries: convertLevelDataEntries,
    isConvertibleExtendedLevelData: isConvertibleExtendedLevelData,
    isNextRushLevelData: isNextRushLevelData,
  };
});
