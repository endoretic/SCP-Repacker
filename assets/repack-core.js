(function (root, factory) {
  if (typeof module !== "undefined" && typeof module.exports === "object") {
    module.exports = factory(root, require("./vendor/fflate.js"));
    return;
  }
  root.SonolusRepackCore = factory(root, root.fflate);
})(typeof globalThis !== "undefined" ? globalThis : this, function (root, fflate) {
  "use strict";

  if (!fflate) {
    throw new Error("fflate is required before loading repack-core.js");
  }

  var unzipSync = fflate.unzipSync;
  var zipSync = fflate.zipSync;

  var RESOURCE_CATEGORIES = ["skins", "backgrounds", "effects", "particles"];
  var LEVEL_CATEGORY = "levels";
  var ENGINE_CATEGORY = "engines";
  var RESOURCE_OVERRIDE_FIELDS = [
    ["skin", "useSkin"],
    ["background", "useBackground"],
    ["effect", "useEffect"],
    ["particle", "useParticle"],
  ];

  var textDecoder = new TextDecoder("utf-8");
  var textEncoder = new TextEncoder();

  function toUint8Array(input) {
    if (input instanceof Uint8Array) {
      return input;
    }
    if (input instanceof ArrayBuffer) {
      return new Uint8Array(input);
    }
    if (ArrayBuffer.isView(input)) {
      return new Uint8Array(input.buffer, input.byteOffset, input.byteLength);
    }
    throw new TypeError("Expected ArrayBuffer or Uint8Array.");
  }

  function deepCopy(value) {
    if (value === null || value === undefined) {
      return value;
    }
    if (typeof structuredClone === "function") {
      return structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
  }

  function compareBytes(left, right) {
    if (!(left instanceof Uint8Array) || !(right instanceof Uint8Array)) {
      return false;
    }
    if (left.byteLength !== right.byteLength) {
      return false;
    }
    for (var index = 0; index < left.byteLength; index += 1) {
      if (left[index] !== right[index]) {
        return false;
      }
    }
    return true;
  }

  function isJsonLikePath(path) {
    var parts = String(path).split("/");
    return parts.length >= 2 && parts[0] === "sonolus" && parts[1] !== "repository";
  }

  function readZip(input) {
    var archive = unzipSync(toUint8Array(input));
    var entries = new Map();
    Object.keys(archive).forEach(function (path) {
      entries.set(path.replace(/\\/g, "/"), archive[path]);
    });
    return entries;
  }

  function writeZip(entries) {
    var files = {};
    entries.forEach(function (value, key) {
      files[key] = value;
    });
    return zipSync(files, { level: 9 });
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

  function listItems(entries, category) {
    var doc = loadJson(entries, "sonolus/" + category + "/list", { pageCount: 1, items: [] });
    if (!doc || typeof doc !== "object" || !Array.isArray(doc.items)) {
      return [];
    }
    return doc.items;
  }

  function itemKey(item) {
    return String(item && item.source ? item.source : "") + "\u0000" + String(item && item.name ? item.name : "");
  }

  function mergeKey(item) {
    var name = String(item && item.name ? item.name : "");
    if (name) {
      return "name\u0000" + name;
    }
    return "fallback\u0000" + String(item && item.source ? item.source : "") + "\u0000" + name;
  }

  function mergeItemLists() {
    var merged = new Map();
    for (var listIndex = 0; listIndex < arguments.length; listIndex += 1) {
      var items = arguments[listIndex];
      for (var itemIndex = 0; itemIndex < items.length; itemIndex += 1) {
        var item = items[itemIndex];
        if (!item || typeof item !== "object" || Array.isArray(item)) {
          continue;
        }
        var key = mergeKey(item);
        if (key === "fallback\u0000\u0000") {
          continue;
        }
        merged.set(key, item);
      }
    }
    return Array.from(merged.values());
  }

  function buildListDoc(items, originalDoc) {
    var doc = originalDoc && typeof originalDoc === "object" && !Array.isArray(originalDoc) ? deepCopy(originalDoc) : {};
    doc.pageCount = 1;
    doc.items = items;
    return doc;
  }

  function buildSectionsDoc(itemType, items, originalDoc) {
    if (originalDoc && typeof originalDoc === "object" && Array.isArray(originalDoc.sections)) {
      var doc = deepCopy(originalDoc);
      var sections = [];
      var inserted = false;
      for (var index = 0; index < originalDoc.sections.length; index += 1) {
        var section = originalDoc.sections[index];
        if (section && typeof section === "object" && section.itemType === itemType) {
          var newSection = deepCopy(section);
          newSection.items = inserted ? [] : items;
          inserted = true;
          sections.push(newSection);
          continue;
        }
        sections.push(section);
      }
      if (!inserted) {
        sections.push({ itemType: itemType, title: "#NEWEST", items: items });
      }
      doc.sections = sections;
      return doc;
    }

    return { sections: [{ itemType: itemType, title: "#NEWEST", items: items }] };
  }

  function extractEngineItem(resourceEntries, engineName) {
    var path = "sonolus/engines/" + engineName;
    var doc = loadJson(resourceEntries, path, null);
    if (doc === null) {
      var available = categoryItemPaths(resourceEntries, ENGINE_CATEGORY).map(function (entryPath) {
        return entryPath.split("/").pop();
      });
      throw new Error(
        "Engine '" + engineName + "' not found in resource package. Available: " + (available.join(", ") || "(none)")
      );
    }
    return itemFromDoc(doc);
  }

  function listAvailableEnginesFromEntries(resourceEntries) {
    return categoryItemPaths(resourceEntries, ENGINE_CATEGORY)
      .map(function (path) {
        try {
          return itemFromDoc(loadJson(resourceEntries, path, null));
        } catch (error) {
          return null;
        }
      })
      .filter(Boolean);
  }

  function listAvailableEngines(resourceInput) {
    return listAvailableEnginesFromEntries(readZip(resourceInput));
  }

  function patchLevelItem(item, targetEngine, replaceDefaults) {
    var patched = deepCopy(item);
    patched.engine = deepCopy(targetEngine);

    if (replaceDefaults) {
      for (var index = 0; index < RESOURCE_OVERRIDE_FIELDS.length; index += 1) {
        var resourceKey = RESOURCE_OVERRIDE_FIELDS[index][0];
        var usageKey = RESOURCE_OVERRIDE_FIELDS[index][1];
        var engineResource = targetEngine[resourceKey];
        if (engineResource && typeof engineResource === "object" && !Array.isArray(engineResource)) {
          patched[usageKey] = { useDefault: true };
          if (Object.prototype.hasOwnProperty.call(patched, resourceKey)) {
            patched[resourceKey] = deepCopy(engineResource);
          }
        }
      }
    }

    return patched;
  }

  function patchLevelSectionsDoc(doc, targetEngine, replaceDefaults) {
    if (!doc || typeof doc !== "object" || !Array.isArray(doc.sections)) {
      return { doc: doc, count: 0 };
    }

    var newDoc = deepCopy(doc);
    var patchedCount = 0;
    newDoc.sections = doc.sections.map(function (section) {
      if (section && typeof section === "object" && Array.isArray(section.items)) {
        var result = patchLevelDocs(section.items, targetEngine, replaceDefaults);
        var newSection = deepCopy(section);
        newSection.items = result.items;
        patchedCount += result.count;
        return newSection;
      }
      return section;
    });
    return { doc: newDoc, count: patchedCount };
  }

  function patchLevelDoc(doc, targetEngine, replaceDefaults) {
    var patchedDoc = doc;
    var patchedCount = 0;

    if (patchedDoc && typeof patchedDoc === "object" && patchedDoc.item && typeof patchedDoc.item === "object") {
      patchedDoc = deepCopy(patchedDoc);
      patchedDoc.item = patchLevelItem(doc.item, targetEngine, replaceDefaults);
      patchedCount += 1;
    } else if (patchedDoc && typeof patchedDoc === "object" && Object.prototype.hasOwnProperty.call(patchedDoc, "engine")) {
      patchedDoc = patchLevelItem(patchedDoc, targetEngine, replaceDefaults);
      patchedCount += 1;
    }

    var sectionResult = patchLevelSectionsDoc(patchedDoc, targetEngine, replaceDefaults);
    return { doc: sectionResult.doc, count: patchedCount + sectionResult.count };
  }

  function patchLevelDocs(items, targetEngine, replaceDefaults) {
    var patchedItems = [];
    var patchedCount = 0;
    for (var index = 0; index < items.length; index += 1) {
      var result = patchLevelDoc(items[index], targetEngine, replaceDefaults);
      patchedItems.push(result.doc);
      patchedCount += result.count;
    }
    return { items: patchedItems, count: patchedCount };
  }

  function patchLevels(entries, targetEngine, replaceDefaults) {
    var counts = { levelFiles: 0, embeddedLevelItems: 0, listItems: 0, infoItems: 0 };

    categoryItemPaths(entries, LEVEL_CATEGORY).forEach(function (path) {
      var doc = loadJson(entries, path, null);
      var result = patchLevelDoc(doc, targetEngine, replaceDefaults);
      if (result.count > 0) {
        entries.set(path, dumpJson(result.doc));
        counts.levelFiles += 1;
        counts.embeddedLevelItems += result.count;
      }
    });

    var listPath = "sonolus/levels/list";
    var listDoc = loadJson(entries, listPath, null);
    if (listDoc && typeof listDoc === "object" && Array.isArray(listDoc.items)) {
      var listResult = patchLevelDocs(listDoc.items, targetEngine, replaceDefaults);
      var newListDoc = deepCopy(listDoc);
      newListDoc.items = listResult.items;
      entries.set(listPath, dumpJson(newListDoc));
      counts.listItems = listResult.count;
    }

    var infoPath = "sonolus/levels/info";
    var infoDoc = loadJson(entries, infoPath, null);
    if (infoDoc && typeof infoDoc === "object" && Array.isArray(infoDoc.sections)) {
      var infoResult = patchLevelSectionsDoc(infoDoc, targetEngine, replaceDefaults);
      entries.set(infoPath, dumpJson(infoResult.doc));
      counts.infoItems = infoResult.count;
    }

    return counts;
  }

  function copyRepository(target, source) {
    var copied = 0;
    source.forEach(function (data, path) {
      if (path.indexOf("sonolus/repository/") === 0) {
        if (!compareBytes(target.get(path), data)) {
          copied += 1;
        }
        target.set(path, data);
      }
    });
    return copied;
  }

  function removeCategory(entries, category) {
    var prefix = "sonolus/" + category + "/";
    Array.from(entries.keys()).forEach(function (path) {
      if (path.indexOf(prefix) === 0) {
        entries.delete(path);
      }
    });
  }

  function mergeResourceCategory(output, originalTarget, resource, category) {
    [originalTarget, resource].forEach(function (sourceEntries) {
      sourceEntries.forEach(function (data, path) {
        if (path.indexOf("sonolus/" + category + "/") === 0 && !path.endsWith("/list")) {
          output.set(path, data);
        }
      });
    });

    var listPath = "sonolus/" + category + "/list";
    var targetListDoc = loadJson(originalTarget, listPath, null);
    var resourceListDoc = loadJson(resource, listPath, null);
    var merged = mergeItemLists(listItems(originalTarget, category), listItems(resource, category));
    output.set(listPath, dumpJson(buildListDoc(merged, targetListDoc || resourceListDoc)));

    var infoPath = "sonolus/" + category + "/info";
    if (resource.has(infoPath)) {
      output.set(infoPath, resource.get(infoPath));
    } else if (originalTarget.has(infoPath)) {
      output.set(infoPath, originalTarget.get(infoPath));
    }

    return merged.length;
  }

  function installEngines(output, resource, selectedEngineName, onlySelected, keepOldEngines, originalTarget) {
    if (!keepOldEngines) {
      removeCategory(output, ENGINE_CATEGORY);
    }

    if (keepOldEngines) {
      originalTarget.forEach(function (data, path) {
        if (path.indexOf("sonolus/" + ENGINE_CATEGORY + "/") === 0) {
          output.set(path, data);
        }
      });
    }

    var selectedPath = "sonolus/" + ENGINE_CATEGORY + "/" + selectedEngineName;
    var targetListDoc = loadJson(originalTarget, "sonolus/" + ENGINE_CATEGORY + "/list", null);
    var resourceListDoc = loadJson(resource, "sonolus/" + ENGINE_CATEGORY + "/list", null);
    var mergedEngineItems = keepOldEngines ? listItems(originalTarget, ENGINE_CATEGORY) : [];

    if (onlySelected) {
      if (!resource.has(selectedPath)) {
        throw new Error("Selected engine item file missing: " + selectedPath);
      }
      output.set(selectedPath, resource.get(selectedPath));
      mergedEngineItems = mergeItemLists(mergedEngineItems, [itemFromDoc(loadJson(resource, selectedPath, null))]);
    } else {
      var resourceEngineItems = [];
      categoryItemPaths(resource, ENGINE_CATEGORY).forEach(function (path) {
        output.set(path, resource.get(path));
        try {
          resourceEngineItems.push(itemFromDoc(loadJson(resource, path, null)));
        } catch (error) {
          return;
        }
      });
      mergedEngineItems = mergeItemLists(mergedEngineItems, resourceEngineItems);
    }

    output.set(
      "sonolus/" + ENGINE_CATEGORY + "/list",
      dumpJson(buildListDoc(mergedEngineItems, resourceListDoc || targetListDoc))
    );

    var infoPath = "sonolus/" + ENGINE_CATEGORY + "/info";
    var infoTemplate = loadJson(resource, infoPath, null);
    if (infoTemplate === null) {
      infoTemplate = loadJson(originalTarget, infoPath, null);
    }
    output.set(infoPath, dumpJson(buildSectionsDoc("engine", mergedEngineItems, infoTemplate)));

    return mergedEngineItems.length;
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

  function summarizeLevelEngines(entries) {
    var seen = new Map();
    iterLevelMetadataItems(entries, function (_, item) {
      var engine = item.engine;
      if (engine && typeof engine === "object") {
        seen.set(itemKey(engine), engine);
      }
    });
    return Array.from(seen.values());
  }

  function validateLevelEngineConsistency(entries, targetEngine, replaceDefaults) {
    var expectedEngineKey = itemKey(targetEngine);
    var mismatches = [];
    var defaultUsageWarnings = [];

    iterLevelMetadataItems(entries, function (location, item) {
      var engine = item.engine;
      if (!engine || typeof engine !== "object" || itemKey(engine) !== expectedEngineKey) {
        mismatches.push(location);
      }

      if (replaceDefaults) {
        RESOURCE_OVERRIDE_FIELDS.forEach(function (entry) {
          var resourceKey = entry[0];
          var usageKey = entry[1];
          var engineResource = targetEngine[resourceKey];
          if (engineResource && typeof engineResource === "object") {
            var usage = item[usageKey];
            if (!usage || typeof usage !== "object" || usage.useDefault !== true) {
              defaultUsageWarnings.push(location + " -> " + usageKey);
            }
          }
        });
      }
    });

    return { mismatches: mismatches, defaultUsageWarnings: defaultUsageWarnings };
  }

  function iterRepositoryPaths(value, callback) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      var url = value.url;
      if (typeof url === "string" && url.indexOf("/sonolus/repository/") === 0) {
        callback(url.replace(/^\//, ""));
      }
      Object.keys(value).forEach(function (key) {
        iterRepositoryPaths(value[key], callback);
      });
      return;
    }

    if (Array.isArray(value)) {
      value.forEach(function (entry) {
        iterRepositoryPaths(entry, callback);
      });
    }
  }

  function validateRepositoryReferences(entries) {
    var missing = [];
    var seenMissing = new Set();
    var repositoryEntries = new Set(
      Array.from(entries.keys()).filter(function (path) {
        return path.indexOf("sonolus/repository/") === 0;
      })
    );

    Array.from(entries.keys()).forEach(function (path) {
      if (!isJsonLikePath(path)) {
        return;
      }
      var doc;
      try {
        doc = loadJson(entries, path, null);
      } catch (error) {
        return;
      }
      if (doc === null) {
        return;
      }
      iterRepositoryPaths(doc, function (repositoryPath) {
        if (!repositoryEntries.has(repositoryPath) && !seenMissing.has(repositoryPath)) {
          seenMissing.add(repositoryPath);
          missing.push(repositoryPath);
        }
      });
    });

    return missing;
  }

  function formatEngineSummary(label, engines) {
    if (!engines.length) {
      return label + "\n  (none)";
    }
    return (
      label +
      "\n" +
      engines
        .map(function (engine) {
          return "  " + engine.name + " | " + engine.title + " | source=" + engine.source;
        })
        .join("\n")
    );
  }

  function formatValidationSummary(label, items) {
    if (!items.length) {
      return label + "\n  none";
    }
    var lines = items.slice(0, 10).map(function (item) {
      return "  " + item;
    });
    if (items.length > 10) {
      lines.push("  ... and " + (items.length - 10) + " more");
    }
    return label + "\n" + lines.join("\n");
  }

  function makeSummaryText(summary) {
    var lines = [
      "Done: generated " + summary.outputName,
      "Bundled resource pack: " + summary.resourcePackName,
      "Selected engine: " + summary.targetEngine.name + " (" + summary.targetEngine.title + ")",
      formatEngineSummary("Detected level engines before patch:", summary.sourceEngines),
      "Rewrote level detail files: " + summary.patchCounts.levelFiles,
      "Rewrote levels/list items: " + summary.patchCounts.listItems,
      "Rewrote levels/info items: " + summary.patchCounts.infoItems,
      "Merged engines list items: " + summary.mergedEngineCount,
    ];

    RESOURCE_CATEGORIES.forEach(function (category) {
      lines.push("Merged " + category + " list items: " + summary.mergedCategoryCounts[category]);
    });
    lines.push("Copied repository files from target package: " + summary.copiedTargetRepository);
    lines.push("Copied repository files from resource package: " + summary.copiedResourceRepository);
    lines.push(formatValidationSummary("Validation engine mismatches:", summary.engineMismatches));
    lines.push(formatValidationSummary("Validation default-resource warnings:", summary.defaultUsageWarnings));
    lines.push(formatValidationSummary("Validation missing repository files:", summary.missingRepositoryFiles));
    lines.push("Warning: this tool rewrites engine references and merges resources. It does not convert Sonolus LevelData.");
    lines.push("Tip: delete the old imported collection in Sonolus before importing the new .scp, to avoid cache/name collisions.");
    return lines.join("\n");
  }

  function repackPackages(options) {
    var targetEntries = readZip(options.levelsInput);
    var resourceEntries = readZip(options.resourceInput);
    var replaceDefaults = options.replaceDefaults !== false;
    var sourceEngines = summarizeLevelEngines(targetEntries);
    var targetEngine = extractEngineItem(resourceEntries, options.engineName);
    var output = new Map(targetEntries);
    var patchCounts = patchLevels(output, targetEngine, replaceDefaults);
    var copiedTargetRepository = copyRepository(output, targetEntries);
    var copiedResourceRepository = copyRepository(output, resourceEntries);
    var mergedEngineCount = installEngines(
      output,
      resourceEntries,
      options.engineName,
      Boolean(options.onlySelectedEngine),
      Boolean(options.keepOldEngines),
      targetEntries
    );
    var mergedCategoryCounts = {};
    RESOURCE_CATEGORIES.forEach(function (category) {
      mergedCategoryCounts[category] = mergeResourceCategory(output, targetEntries, resourceEntries, category);
    });

    ["sonolus/package", "sonolus/info"].forEach(function (path) {
      if (!output.has(path) && resourceEntries.has(path)) {
        output.set(path, resourceEntries.get(path));
      }
    });

    var consistency = validateLevelEngineConsistency(output, targetEngine, replaceDefaults);
    var missingRepositoryFiles = validateRepositoryReferences(output);
    var outputBytes = writeZip(output);
    var summary = {
      outputName: options.outputName || "repacked.scp",
      resourcePackName: options.resourcePackName || "engine.scp",
      targetEngine: targetEngine,
      sourceEngines: sourceEngines,
      patchCounts: patchCounts,
      mergedEngineCount: mergedEngineCount,
      mergedCategoryCounts: mergedCategoryCounts,
      copiedTargetRepository: copiedTargetRepository,
      copiedResourceRepository: copiedResourceRepository,
      engineMismatches: consistency.mismatches,
      defaultUsageWarnings: consistency.defaultUsageWarnings,
      missingRepositoryFiles: missingRepositoryFiles,
    };

    return {
      outputEntries: output,
      outputBytes: outputBytes,
      summary: summary,
      summaryText: makeSummaryText(summary),
    };
  }

  return {
    readZip: readZip,
    writeZip: writeZip,
    listAvailableEngines: listAvailableEngines,
    listAvailableEnginesFromEntries: listAvailableEnginesFromEntries,
    repackPackages: repackPackages,
    makeSummaryText: makeSummaryText,
  };
});
