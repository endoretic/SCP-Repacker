(function () {
  "use strict";

  var RESOURCE_PACK_URL = "./engine.scp";
  var RESOURCE_PACK_NAME = "engine.scp";

  var core = window.SonolusRepackCore;
  if (!core) {
    throw new Error("SonolusRepackCore is not available.");
  }

  var state = {
    resourceBuffer: null,
    resourceEngines: [],
    resourceError: null,
    downloadUrl: null,
  };

  var levelsFileInput = document.getElementById("levels-file");
  var engineSelect = document.getElementById("engine-select");
  var outputNameInput = document.getElementById("output-name");
  var replaceDefaultsInput = document.getElementById("replace-defaults");
  var convertLevelDataInput = document.getElementById("convert-level-data");
  var onlySelectedEngineInput = document.getElementById("only-selected-engine");
  var keepOldEnginesInput = document.getElementById("keep-old-engines");
  var repackButton = document.getElementById("repack-button");
  var downloadLink = document.getElementById("download-link");
  var runStatus = document.getElementById("run-status");
  var summaryOutput = document.getElementById("summary-output");
  var engineList = document.getElementById("engine-list");

  function setRunStatus(text) {
    runStatus.textContent = text;
  }

  function setSummary(text) {
    summaryOutput.textContent = text;
  }

  function revokeDownloadUrl() {
    if (state.downloadUrl) {
      URL.revokeObjectURL(state.downloadUrl);
      state.downloadUrl = null;
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function renderEngineList(engines) {
    if (!engines.length) {
      engineList.innerHTML = '<li class="placeholder">No engines were found in engine.scp.</li>';
      return;
    }
    engineList.innerHTML = engines
      .map(function (engine) {
        return (
          '<li class="engine-card">' +
          "<strong>" + escapeHtml(engine.title || "(no title)") + "</strong>" +
          "<span>" + escapeHtml(engine.name || "(unnamed)") + "</span>" +
          "<span>" + escapeHtml(engine.source || "(no source)") + "</span>" +
          "</li>"
        );
      })
      .join("");
  }

  function stripPackageExtension(filename) {
    return String(filename || "")
      .replace(/\.scp\.zip$/i, "")
      .replace(/\.scp$/i, "")
      .replace(/\.zip$/i, "");
  }

  function normalizeOutputName(filename) {
    var normalized = String(filename || "").trim().replace(/[\\/:*?"<>|]+/g, "-");
    normalized = normalized.replace(/\.scp\.zip$/i, ".scp").replace(/\.zip$/i, ".scp");
    if (!normalized) {
      normalized = deriveOutputName();
    }
    if (!/\.scp$/i.test(normalized)) {
      normalized += ".scp";
    }
    return normalized;
  }

  function rebuildEngineSelect(engines) {
    engineSelect.innerHTML = "";
    if (!engines.length) {
      var emptyOption = document.createElement("option");
      emptyOption.textContent = "No engine found in engine.scp";
      engineSelect.appendChild(emptyOption);
      engineSelect.disabled = true;
      return;
    }
    engines.forEach(function (engine) {
      var option = document.createElement("option");
      option.value = engine.name || "";
      option.textContent = (engine.title || "(no title)") + " | " + (engine.name || "(unnamed)");
      engineSelect.appendChild(option);
    });
    if (engines.some(function (engine) { return engine.name === "rush"; })) {
      engineSelect.value = "rush";
    }
    engineSelect.disabled = false;
  }

  function deriveOutputName() {
    var file = levelsFileInput.files && levelsFileInput.files[0];
    var engineName = engineSelect.value || "engine";
    if (!file) {
      return "repacked-" + engineName + ".scp";
    }
    var baseName = stripPackageExtension(file.name);
    return baseName + "-" + engineName + "-repacked.scp";
  }

  function updateOutputNameIfAuto() {
    var derived = deriveOutputName();
    if (!outputNameInput.dataset.userEdited || outputNameInput.value.trim() === "" || outputNameInput.value === outputNameInput.dataset.lastAutoValue) {
      outputNameInput.value = derived;
      outputNameInput.dataset.lastAutoValue = derived;
    }
  }

  function updateActionState() {
    var hasLevelsFile = Boolean(levelsFileInput.files && levelsFileInput.files[0]);
    var hasResourcePack = Boolean(state.resourceBuffer && !state.resourceError);
    var hasEngine = !engineSelect.disabled && engineSelect.value;
    repackButton.disabled = !(hasLevelsFile && hasResourcePack && hasEngine);
  }

  async function loadBundledResourcePack() {
    setRunStatus("Select a levels package to start.");
    setSummary("Not started yet.");

    try {
      var response = await fetch(RESOURCE_PACK_URL, { cache: "no-store" });
      if (!response.ok) {
        throw new Error("HTTP " + response.status + " " + response.statusText);
      }
      var buffer = await response.arrayBuffer();
      var engines = core.listAvailableEngines(buffer);
      state.resourceBuffer = buffer;
      state.resourceEngines = engines;
      state.resourceError = null;
      rebuildEngineSelect(engines);
      renderEngineList(engines);
      if (levelsFileInput.files && levelsFileInput.files[0]) {
        setRunStatus("Levels package selected.");
      }
      updateOutputNameIfAuto();
      updateActionState();
      return;
    } catch (error) {
      state.resourceBuffer = null;
      state.resourceEngines = [];
      state.resourceError = error;
      rebuildEngineSelect([]);
      renderEngineList([]);
      setRunStatus("Could not load engine.scp. Possibly caused by file:// access or a missing local file.");
      setSummary(
        "Bundled resource load failed.\n" +
          error.message +
          "\n\nPlease check:\n" +
          "1. index.html and engine.scp are in the same directory.\n" +
          "2. Open the page through a local static server or normal hosting instead of file://."
      );
      updateActionState();
    }
  }

  async function repack() {
    var levelsFile = levelsFileInput.files && levelsFileInput.files[0];
    if (!levelsFile) {
      setRunStatus("Select a levels package first.");
      return;
    }
    if (!state.resourceBuffer) {
      setRunStatus("engine.scp has not loaded successfully yet.");
      return;
    }

    repackButton.disabled = true;
    revokeDownloadUrl();
    downloadLink.classList.add("is-hidden");
    setRunStatus("Repacking. Please wait...");
    setSummary("Working...");

    try {
      var levelsBuffer = await levelsFile.arrayBuffer();
      var outputName = normalizeOutputName(outputNameInput.value);
      outputNameInput.value = outputName;
      var result = core.repackPackages({
        levelsInput: levelsBuffer,
        resourceInput: state.resourceBuffer,
        engineName: engineSelect.value,
        replaceDefaults: replaceDefaultsInput.checked,
        convertLevelData: convertLevelDataInput.checked,
        onlySelectedEngine: onlySelectedEngineInput.checked,
        keepOldEngines: keepOldEnginesInput.checked,
        outputName: outputName,
        resourcePackName: RESOURCE_PACK_NAME,
      });

      var blob = new Blob([result.outputBytes], { type: "application/octet-stream" });
      state.downloadUrl = URL.createObjectURL(blob);
      downloadLink.href = state.downloadUrl;
      downloadLink.download = outputName;
      downloadLink.textContent = "Download " + outputName;
      downloadLink.classList.remove("is-hidden");
      setSummary(result.summaryText);
      setRunStatus("Repack completed. Ready to download.");
    } catch (error) {
      setSummary("Repack failed.\n" + error.message);
      setRunStatus("Repack failed. Check summary below for more details.");
    } finally {
      updateActionState();
    }
  }

  levelsFileInput.addEventListener("change", function () {
    updateOutputNameIfAuto();
    updateActionState();
    if (levelsFileInput.files && levelsFileInput.files[0] && !state.resourceError) {
      setRunStatus("Levels package selected.");
    }
  });

  engineSelect.addEventListener("change", function () {
    updateOutputNameIfAuto();
    updateActionState();
  });

  outputNameInput.addEventListener("input", function () {
    outputNameInput.dataset.userEdited = "true";
  });

  repackButton.addEventListener("click", function () {
    repack();
  });

  window.addEventListener("beforeunload", function () {
    revokeDownloadUrl();
  });

  updateActionState();
  loadBundledResourcePack();
})();
