"""JPEG XL and AVIF ISOBMFF container utilities with Brotli-compressed metadata.

Provides encode/decode for both formats with prompt/workflow metadata stored
in a custom ISOBMFF 'brob' box (type tag 'comf') using Brotli compression.
"""

import json
import math
import struct

import numpy as np

try:
    import brotli
    _BROTLI_AVAILABLE = True
except ImportError:
    _BROTLI_AVAILABLE = False

try:
    import imagecodecs
    _JXL_AVAILABLE = hasattr(imagecodecs, 'jpegxl_encode')
    _AVIF_AVAILABLE = hasattr(imagecodecs, 'avif_encode')
except ImportError:
    imagecodecs = None
    _JXL_AVAILABLE = False
    _AVIF_AVAILABLE = False


# ── Constants ──────────────────────────────────────────────────────────────

_JXL_SIG = struct.pack('>I', 12) + b'JXL ' + bytes([0x0d, 0x0a, 0x87, 0x0a])

_JXL_FTYP = (
    struct.pack('>I', 20)
    + b'ftyp'
    + b'jxl '
    + struct.pack('>I', 0)
    + b'jxl '
)


# ── ISOBMFF Container Utilities ───────────────────────────────────────────

def _make_box(box_type: bytes, data: bytes) -> bytes:
    size = 8 + len(data)
    return struct.pack('>I', size) + box_type + data


def _parse_boxes(data: bytes, offset: int = 0) -> list[dict]:
    boxes = []
    while offset + 8 <= len(data):
        size = struct.unpack('>I', data[offset:offset + 4])[0]
        box_type = data[offset + 4:offset + 8]
        if size == 0:
            break
        if size < 8 or offset + size > len(data):
            break
        box_data = data[offset + 8:offset + size]
        boxes.append({
            'type': box_type,
            'data': box_data,
            'size': size,
            'offset': offset,
        })
        offset += size
    return boxes


def _find_box(boxes: list[dict], box_type: bytes):
    for box in boxes:
        if box['type'] == box_type:
            return box
    return None


# ── Brotli Compression ─────────────────────────────────────────────────────

def _compress_metadata(data: bytes) -> bytes | None:
    if not _BROTLI_AVAILABLE:
        return None
    return brotli.compress(data, mode=brotli.MODE_TEXT, quality=11)


def _decompress_metadata(data: bytes) -> bytes | None:
    if not _BROTLI_AVAILABLE:
        return None
    try:
        return brotli.decompress(data)
    except brotli.error:
        return None


# ── Metadata Serialization ─────────────────────────────────────────────────

def _clean_nan(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean_nan(v) for v in obj]
    return obj


def _build_metadata_blob(prompt: dict | None, extra_pnginfo: dict | None) -> bytes:
    metadata = {}
    if prompt is not None:
        metadata['prompt'] = _clean_nan(prompt)
    if extra_pnginfo is not None:
        for key, value in extra_pnginfo.items():
            metadata[key] = _clean_nan(value)
    return json.dumps(metadata, allow_nan=False).encode('utf-8')


def _parse_metadata_blob(raw: bytes) -> dict:
    try:
        return json.loads(raw.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


# ── Container Detection ────────────────────────────────────────────────────

def is_jxl_container(data: bytes) -> bool:
    """Check if bytes are a JXL ISOBMFF container (not raw codestream)."""
    if len(data) < 32:
        return False
    return (
        struct.unpack('>I', data[:4])[0] == 12
        and data[4:8] == b'JXL '
        and data[8:12] == bytes([0x0d, 0x0a, 0x87, 0x0a])
        and struct.unpack('>I', data[12:16])[0] == 20
        and data[16:20] == b'ftyp'
        and data[20:24] == b'jxl '
    )


def is_avif_container(data: bytes) -> bool:
    """Check if bytes are an AVIF file (ftyp box with 'avif' brand)."""
    if len(data) < 16:
        return False
    boxes = _parse_boxes(data)
    ftyp = _find_box(boxes, b'ftyp')
    if ftyp is None:
        return False
    return b'avif' in ftyp['data']


# ── Brob Box Metadata Extraction ──────────────────────────────────────────

def _extract_from_brob_box(brob_box: dict) -> dict:
    """Extract and decompress metadata from a brob box payload."""
    if brob_box['data'][:4] != b'comf':
        return {}
    payload = brob_box['data'][4:]
    decompressed = _decompress_metadata(payload)
    if decompressed is not None:
        return _parse_metadata_blob(decompressed)
    return _parse_metadata_blob(payload)


def extract_isobmff_metadata(data: bytes) -> dict:
    """Extract metadata from any ISOBMFF file (JXL or AVIF) with a brob box."""
    if is_jxl_container(data):
        boxes = _parse_boxes(data, offset=12)
    elif is_avif_container(data):
        boxes = _parse_boxes(data, offset=0)
    else:
        return {}
    brob = _find_box(boxes, b'brob')
    if brob is not None:
        return _extract_from_brob_box(brob)
    return {}


# ── Generic brob injector (for AVIF post-processing) ─────────────────────

def _append_brob_box(data: bytes, metadata_blob: bytes) -> bytes:
    """Append a brob box at the end of an ISOBMFF file (safe for AVIF offsets)."""
    compressed = _compress_metadata(metadata_blob)
    brob_content = b'comf' + (compressed if compressed is not None else metadata_blob)
    return data + _make_box(b'brob', brob_content)


# ── JXL Encode ─────────────────────────────────────────────────────────────

def encode_jxl_with_metadata(
    image: np.ndarray,
    quality: int = 100,
    prompt: dict | None = None,
    extra_pnginfo: dict | None = None,
) -> bytes:
    """Encode a numpy image (HxWxC, uint8) to a JXL container with compressed metadata.

    Metadata is always compressed with Brotli when available (no opt-out).
    Quality 100 = lossless. Lower values = more compression.
    """
    if not _JXL_AVAILABLE:
        raise RuntimeError(
            'imagecodecs JXL support not available. Install with: pip install imagecodecs'
        )

    if quality >= 100:
        codestream = imagecodecs.jpegxl_encode(image, lossless=True)
    else:
        distance = (100 - quality) * 0.15
        codestream = imagecodecs.jpegxl_encode(image, lossless=False, distance=distance)

    container = _JXL_SIG + _JXL_FTYP
    container += _make_box(b'jxlc', codestream)

    if prompt is not None or extra_pnginfo is not None:
        raw_meta = _build_metadata_blob(prompt, extra_pnginfo)
        compressed = _compress_metadata(raw_meta)
        brob_content = b'comf' + (compressed if compressed is not None else raw_meta)
        container += _make_box(b'brob', brob_content)

    return container


# ── JXL Decode ─────────────────────────────────────────────────────────────

def decode_jxl_to_numpy(data: bytes):
    """Decode a JXL file to (numpy_array, metadata_dict).

    Handles both ISOBMFF container and raw codestream input.
    """
    if not _JXL_AVAILABLE:
        raise RuntimeError('imagecodecs JXL support not available')

    metadata = {}

    if is_jxl_container(data):
        boxes = _parse_boxes(data, offset=12)
        brob = _find_box(boxes, b'brob')
        if brob is not None:
            metadata = _extract_from_brob_box(brob)

        codestream = None
        jxlc = _find_box(boxes, b'jxlc')
        if jxlc is not None:
            codestream = jxlc['data']
        else:
            for b in boxes:
                if b['type'] == b'jxlp' and len(b['data']) > 1:
                    codestream = b['data'][1:]
                    break
        if codestream is None:
            raise ValueError('No JXL codestream found in container')
    else:
        codestream = data

    image = imagecodecs.jpegxl_decode(codestream)
    return image, metadata


# ── AVIF Encode ────────────────────────────────────────────────────────────

def encode_avif_with_metadata(
    image: np.ndarray,
    quality: int = 90,
    prompt: dict | None = None,
    extra_pnginfo: dict | None = None,
    speed: int = 6,
    numthreads: int = 4,
) -> bytes:
    """Encode a numpy image (HxWxC, uint8) to an AVIF file with compressed metadata.

    Metadata is appended as a top-level 'brob' box (safe — does not shift iloc offsets).
    """
    if not _AVIF_AVAILABLE:
        raise RuntimeError(
            'imagecodecs AVIF support not available. Install with: pip install imagecodecs'
        )

    if quality >= 100:
        data = imagecodecs.avif_encode(image, level=100, speed=speed, numthreads=numthreads)
    else:
        data = imagecodecs.avif_encode(image, level=quality, speed=speed, numthreads=numthreads)

    if prompt is not None or extra_pnginfo is not None:
        raw_meta = _build_metadata_blob(prompt, extra_pnginfo)
        data = _append_brob_box(data, raw_meta)

    return data


# ── AVIF Decode ────────────────────────────────────────────────────────────

def decode_avif_to_numpy(data: bytes):
    """Decode an AVIF file to (numpy_array, metadata_dict)."""
    if not _AVIF_AVAILABLE:
        raise RuntimeError('imagecodecs AVIF support not available')

    metadata = extract_isobmff_metadata(data)
    image = imagecodecs.avif_decode(data)
    return image, metadata


# ── Public API ─────────────────────────────────────────────────────────────

BROTLI_AVAILABLE = _BROTLI_AVAILABLE
JXL_AVAILABLE = _JXL_AVAILABLE
AVIF_AVAILABLE = _AVIF_AVAILABLE

__all__ = [
    'encode_jxl_with_metadata',
    'decode_jxl_to_numpy',
    'encode_avif_with_metadata',
    'decode_avif_to_numpy',
    'extract_isobmff_metadata',
    'is_jxl_container',
    'is_avif_container',
    'BROTLI_AVAILABLE',
    'JXL_AVAILABLE',
    'AVIF_AVAILABLE',
]
