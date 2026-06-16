# Customize the folder, sub-folders, and filenames of your images! 
# Save data about the generated job (sampler, prompts, models) as entries in a `json` (text) file, in each folder.
# Use the values of ANY node's widget, by simply adding its badge number in the form _id.widget_name_: 
# Oh btw... also saves your output as **WebP** or **JPEG**... And yes the prompt is included :) ComfyUI can load it but a PR approval is needed.

"""
@author: AudioscavengeR
@title: Save Image Extended
@nickname: Save Image Extended
@description: 1 custom node to save your pictures in various folders and formats.
"""


from .save_image_extended import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

WEB_DIRECTORY = "./web"

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', "WEB_DIRECTORY"]

import math
import logging

from aiohttp import web
from server import PromptServer
from pathlib import Path

logger = logging.getLogger('save_image_extended')


def _clean(v):
    """Sanitize NaN/Inf floats for JSON serialization."""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if isinstance(v, dict):
        return {k: _clean(v2) for k, v2 in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(v2) for v2 in v]
    return v


if hasattr(PromptServer, "instance"):
    # Server route for JXL/AVIF metadata extraction (workflow recovery)
    @PromptServer.instance.routes.post('/api/jxl_metadata')
    async def jxl_metadata(request):
        try:
            body = await request.read()
            if len(body) < 12:
                return web.json_response({})
            from .jxl_io import extract_isobmff_metadata
            meta = extract_isobmff_metadata(body)
            return web.json_response(_clean(meta))
        except Exception:
            logger.warning('Failed to extract JXL/AVIF metadata', exc_info=True)
            return web.json_response({}, status=400)

    # NOTE: we add an extra static path to avoid comfy mechanism
    # that loads every script in web.
    PromptServer.instance.app.add_routes(
        [web.static("/save_image_extended", (Path(__file__).parent.absolute() / "assets").as_posix())]
    )

