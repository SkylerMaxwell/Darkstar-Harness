# SPDX-License-Identifier: Apache-2.0
"""Darkstar Tool: generate an image with the diffusion pipeline connected to Orchestrator."""

from tools.registry import registry

MAX_PROMPT_CHARS = 12_000
MIN_DIMENSION = 64
MAX_DIMENSION = 4096
DIMENSION_MULTIPLE = 8
MIN_STEPS = 1
MAX_STEPS = 150
MIN_CFG_SCALE = 0.1
MAX_CFG_SCALE = 30.0
MIN_IMAGE_COUNT = 1
MAX_IMAGE_COUNT = 50
SAMPLER_VALUES = [
    "euler",
    "euler_a",
    "heun",
    "dpm2",
    "dpmpp_2s_a",
    "dpmpp_2m",
    "dpmpp_2m_v2",
    "dpmpp_2m_sde",
    "dpmpp_2m_sde_bt",
    "ipndm",
    "ipndm_v",
    "lcm",
    "ddim_trailing",
    "tcd",
    "res_multistep",
    "res_2s",
    "er_sde",
    "euler_cfgpp",
    "euler_a_cfgpp",
    "euler_ge",
]

SCHEMA = {
    "name": "generate_image",
    "description": (
        "Generate one or more images sequentially with the Diffusion Backend GGUF and DM Sampler connected to the active Orchestrator. "
        "Darkstar streams denoising previews in chat while each image is generated, then shows every finished PNG. "
        f"You must choose how many images to generate through image_count ({MIN_IMAGE_COUNT}-{MAX_IMAGE_COUNT}) unless Darkstar hides that field because Settings forces a fixed image count. Images are generated one after another, not as a native batch. "
        "When DM Sampler Steps is set to Auto, you must choose an appropriate step count for every request through the steps field. "
        f"The allowed range is {MIN_STEPS}-{MAX_STEPS}. More complex prompts or higher-fidelity requests generally benefit from more steps, while simpler prompts can use fewer steps to finish faster. "
        "When DM Sampler CFG is set to Auto, you must choose an appropriate cfg_scale for the request. Higher CFG generally follows the prompt more strongly, while lower CFG can be looser or more natural. "
        "When DM Sampler Sampler is set to Auto, you must choose an appropriate sampler for the request. "
        "If the user has armed an image edit in Darkstar's image editor, this same tool automatically becomes a masked inpainting operation: describe only the desired replacement inside the approved region; Darkstar owns the source image, mask, crop geometry, and preservation boundary. "
        "If the loaded language model is multimodal, the finished pixels are also attached to the next model round."
    ),
    "parameters": {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "minLength": 1,
                "maxLength": MAX_PROMPT_CHARS,
                "description": "Positive image-generation prompt.",
            },
            "negative_prompt": {
                "type": "string",
                "maxLength": MAX_PROMPT_CHARS,
                "description": "Optional negative prompt. Defaults to an empty string.",
            },
            "width": {
                "type": "integer",
                "minimum": MIN_DIMENSION,
                "maximum": MAX_DIMENSION,
                "multipleOf": DIMENSION_MULTIPLE,
                "description": "Output width in pixels. Defaults to 1024 and must be divisible by 8.",
            },
            "height": {
                "type": "integer",
                "minimum": MIN_DIMENSION,
                "maximum": MAX_DIMENSION,
                "multipleOf": DIMENSION_MULTIPLE,
                "description": "Output height in pixels. Defaults to 1024 and must be divisible by 8.",
            },
            "image_count": {
                "type": "integer",
                "minimum": MIN_IMAGE_COUNT,
                "maximum": MAX_IMAGE_COUNT,
                "description": "Choose how many images to generate sequentially for this request. Required when Settings image count is 0 (model-controlled); hidden when Settings forces a fixed count.",
            },
            "steps": {
                "type": "integer",
                "minimum": MIN_STEPS,
                "maximum": MAX_STEPS,
                "description": "Choose the generation step count for this request when DM Sampler Steps is Auto. This field is required by the runtime tool schema in Auto mode. More complex prompts or higher-fidelity requests generally benefit from more steps, while simpler prompts can use fewer steps to finish faster. The field is hidden when DM Sampler has a fixed non-zero Steps value.",
            },
            "cfg_scale": {
                "type": "number",
                "minimum": MIN_CFG_SCALE,
                "maximum": MAX_CFG_SCALE,
                "description": "Choose the CFG / guidance scale for this request when DM Sampler CFG is Auto. This field is required by the runtime tool schema in Auto mode. Higher CFG generally follows the prompt more strongly, while lower CFG can be looser or more natural. The field is hidden when DM Sampler has a fixed non-zero CFG value.",
            },
            "sampler": {
                "type": "string",
                "enum": SAMPLER_VALUES,
                "description": "Choose the diffusion sampler for this request when DM Sampler Sampler is Auto. This field is required by the runtime tool schema in Auto mode. The field is hidden when DM Sampler already has a fixed sampler value.",
            },
        },
        "required": ["prompt"],
        "additionalProperties": False,
    },
}


def _dimension(args, key):
    value = args.get(key, 1024)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer.")
    if not MIN_DIMENSION <= value <= MAX_DIMENSION or value % DIMENSION_MULTIPLE:
        raise ValueError(
            f"{key} must be between {MIN_DIMENSION} and {MAX_DIMENSION} and divisible by {DIMENSION_MULTIPLE}."
        )
    return value


def _image_count(args):
    if "image_count" not in args or args.get("image_count") is None:
        return None
    value = args.get("image_count")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("image_count must be an integer.")
    if not MIN_IMAGE_COUNT <= value <= MAX_IMAGE_COUNT:
        raise ValueError(f"image_count must be between {MIN_IMAGE_COUNT} and {MAX_IMAGE_COUNT}.")
    return value


def _steps(args):
    if "steps" not in args or args.get("steps") is None:
        return None
    value = args.get("steps")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("steps must be an integer.")
    if not MIN_STEPS <= value <= MAX_STEPS:
        raise ValueError(f"steps must be between {MIN_STEPS} and {MAX_STEPS}.")
    return value




def _cfg_scale(args):
    if "cfg_scale" not in args or args.get("cfg_scale") is None:
        return None
    value = args.get("cfg_scale")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("cfg_scale must be a number.")
    value = float(value)
    if not MIN_CFG_SCALE <= value <= MAX_CFG_SCALE:
        raise ValueError(f"cfg_scale must be between {MIN_CFG_SCALE} and {MAX_CFG_SCALE}.")
    return value


def _sampler(args):
    if "sampler" not in args or args.get("sampler") is None:
        return None
    value = str(args.get("sampler") or "").strip().lower()
    if value not in SAMPLER_VALUES:
        raise ValueError(f"sampler must be one of: {', '.join(SAMPLER_VALUES)}.")
    return value


def handler(args, **_context):
    prompt = str(args.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("prompt is required.")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"prompt must be at most {MAX_PROMPT_CHARS} characters.")
    negative_prompt = str(args.get("negative_prompt") or "").strip()
    if len(negative_prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"negative_prompt must be at most {MAX_PROMPT_CHARS} characters.")
    result = {
        "__darkstarAction": "generate_image",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": _dimension(args, "width"),
        "height": _dimension(args, "height"),
    }
    image_count = _image_count(args)
    if image_count is not None:
        result["image_count"] = image_count
    steps = _steps(args)
    if steps is not None:
        result["steps"] = steps
    cfg_scale = _cfg_scale(args)
    if cfg_scale is not None:
        result["cfg_scale"] = cfg_scale
    sampler = _sampler(args)
    if sampler is not None:
        result["sampler"] = sampler
    return result


registry.register(
    name=SCHEMA["name"],
    toolset="media",
    schema=SCHEMA,
    handler=handler,
    description=SCHEMA["description"],
)
