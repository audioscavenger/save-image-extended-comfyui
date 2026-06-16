import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ── ISOBMFF Container Parser (JXL & AVIF) ───────────────────────────────

function bytesToString(bytes) {
  return new TextDecoder("iso-8859-1").decode(bytes);
}

function parseBoxes(data) {
  var boxes = [];
  var offset = 0;
  var view = new DataView(data);
  while (offset + 8 <= data.byteLength) {
    var size = view.getUint32(offset);
    if (size === 0) break;
    if (size < 8 || offset + size > data.byteLength) break;
    var type = bytesToString(new Uint8Array(data, offset + 4, 4));
    boxes.push({ type: type, data: new Uint8Array(data, offset + 8, size - 8), size: size });
    offset += size;
  }
  return boxes;
}

var MAGIC_JXL = [
  0x00, 0x00, 0x00, 0x0c,
  0x4a, 0x58, 0x4c, 0x20,
  0x0d, 0x0a, 0x87, 0x0a,
];

function isJxlContainer(buffer) {
  if (buffer.byteLength < 32) return false;
  var u8 = new Uint8Array(buffer);
  for (var i = 0; i < 12; i++) {
    if (u8[i] !== MAGIC_JXL[i]) return false;
  }
  return (
    u8[12] === 0x00 && u8[13] === 0x00 && u8[14] === 0x00 && u8[15] === 0x14 &&
    u8[16] === 0x66 && u8[17] === 0x74 && u8[18] === 0x79 && u8[19] === 0x70 &&
    u8[20] === 0x6a && u8[21] === 0x78 && u8[22] === 0x6c && u8[23] === 0x20
  );
}

// ── Brotli Decompression ────────────────────────────────────────────────
// NOTE: Brotli DecompressionStream is NOT available in Chromium/Chrome.
// It is supported in Firefox and Safari.
// The server-side fallback route (/api/jxl_metadata) handles cases where
// client-side brotli decompression is unavailable.
// Once Chromium ships native Brotli DecompressionStream support,
// the server fallback path can be removed.

var _brotliFormats = [];
function detectBrotliFormat() {
  if (_brotliFormats.length > 0) return _brotliFormats;
  if (typeof DecompressionStream === "undefined") return [];
  var candidates = ["brotli", "br"];
  for (var i = 0; i < candidates.length; i++) {
    try { new DecompressionStream(candidates[i]); _brotliFormats.push(candidates[i]); } catch (e) {}
  }
  return _brotliFormats;
}

async function decompressBrotli(compressed) {
  var formats = detectBrotliFormat();
  if (formats.length === 0) return null;
  for (var f = 0; f < formats.length; f++) {
    try {
      var cs = new DecompressionStream(formats[f]);
      var blob = new Blob([compressed]);
      var stream = blob.stream().pipeThrough(cs);
      var reader = stream.getReader();
      var chunks = [];
      while (true) {
        var r = await reader.read();
        if (r.done) break;
        chunks.push(r.value);
      }
      var total = chunks.reduce(function (s, c) { return s + c.byteLength; }, 0);
      var result = new Uint8Array(total);
      var off = 0;
      for (var i = 0; i < chunks.length; i++) {
        result.set(chunks[i], off);
        off += chunks[i].byteLength;
      }
      return result;
    } catch (e) {}
  }
  return null;
}

// ── Metadata Extraction ─────────────────────────────────────────────────

async function getWorkflowFromBuffer(buffer) {
  var boxes = parseBoxes(buffer);
  for (var i = 0; i < boxes.length; i++) {
    if (boxes[i].type === "brob") {
      var innerType = bytesToString(boxes[i].data.subarray(0, 4));
      if (innerType !== "comf") continue;
      var compressed = boxes[i].data.subarray(4);
      var decompressed = await decompressBrotli(compressed);
      if (decompressed) {
        try {
          return JSON.parse(new TextDecoder("utf-8").decode(decompressed));
        } catch (e) {}
      }
      try {
        return JSON.parse(new TextDecoder("utf-8").decode(compressed));
      } catch (e) {}
    }
  }
  return null;
}

async function getWorkflowFromFile(file) {
  try {
    var buffer = await file.arrayBuffer();
    return await getWorkflowFromBuffer(buffer);
  } catch (e) { return null; }
}

async function getWorkflowFromServer(file) {
  try {
    var resp = await api.fetchApi("/jxl_metadata", {
      method: "POST",
      body: file,
      headers: { "Content-Type": "application/octet-stream" }
    });
    if (!resp.ok) return null;
    return await resp.json();
  } catch (e) { return null; }
}

// ── Try to load workflow from .jxl / .avif metadata ─────────────────────
// Returns true if workflow was loaded, false to fall through to default.

async function tryLoadWorkflow(file) {
  var meta = await getWorkflowFromFile(file);
  if (!meta) { meta = await getWorkflowFromServer(file); }
  if (meta && meta.workflow) {
    var name = file.name.replace(/\.\w+$/, "");
    var wf = typeof meta.workflow === "string" ? JSON.parse(meta.workflow) : meta.workflow;
    if (wf && typeof wf === "object") {
      await app.loadGraphData(wf, true, true, name, {});
      return true;
    }
  }
  return false;
}

var _supportedExts = [".jxl", ".avif"];
var _unpatchedHandleFile = null;

// ── Register Extension ─────────────────────────────────────────────────

app.registerExtension({
  name: "save_image_extended.JxlAvifMetadata",

  async setup() {
    patchHandleFile();
  },
});

// ── Patch app.handleFile ────────────────────────────────────────────────
// Only loads workflow from embedded metadata.
// Falls through to default ComfyUI handler for all other cases (image load).

function patchHandleFile() {
  if (typeof app.handleFile !== "function") return;
  if (app._sieJxlAvifPatched) return;
  app._sieJxlAvifPatched = true;

  _unpatchedHandleFile = app.handleFile.bind(app);
  app.handleFile = async function (file, source, opts) {
    if (file && file.name && _matchesExt(file.name)) {
      if (await tryLoadWorkflow(file)) return;
    }
    return _unpatchedHandleFile(file, source, opts);
  };
}

function _matchesExt(name) {
  var lower = name.toLowerCase();
  for (var i = 0; i < _supportedExts.length; i++) {
    if (lower.endsWith(_supportedExts[i])) return true;
  }
  return false;
}

// ── Drag/drop interceptors ──────────────────────────────────────────────
// Allow .jxl/.avif files to be dropped (browser would otherwise reject them).

document.addEventListener("dragover", function (e) {
  try {
    var dt = e.dataTransfer;
    if (!dt || !dt.files) return;
    for (var i = 0; i < dt.files.length; i++) {
      if (dt.files[i].name && _matchesExt(dt.files[i].name)) {
        e.preventDefault();
        e.stopPropagation();
        return;
      }
    }
  } catch (ex) {}
}, true);

document.addEventListener("drop", function (e) {
  try {
    var dt = e.dataTransfer;
    if (!dt || !dt.files) return;
    for (var i = 0; i < dt.files.length; i++) {
      var f = dt.files[i];
      if (!f || !f.name || !_matchesExt(f.name)) continue;

      e.preventDefault();
      e.stopPropagation();
      (async function () {
        if (!(await tryLoadWorkflow(f)) && _unpatchedHandleFile) {
          _unpatchedHandleFile(f, 'client', {});
        }
      })();
      return;
    }
  } catch (ex) {}
}, true);
