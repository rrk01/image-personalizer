import math
from typing import Literal


AspectRatio = Literal["1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"]

# Exact choices from ComfyUI's ResolutionSelector node.
ASPECT_RATIOS = {
    "1:1": "1:1 (Square)",
    "2:3": "2:3 (Portrait Photo)",
    "3:2": "3:2 (Photo)",
    "3:4": "3:4 (Portrait Standard)",
    "4:3": "4:3 (Standard)",
    "9:16": "9:16 (Portrait Widescreen)",
    "16:9": "16:9 (Widescreen)",
    "21:9": "21:9 (Ultrawide)",
}


def image_format(aspect_ratio="1:1"):
    label = ASPECT_RATIOS[aspect_ratio]
    w, h = map(int, aspect_ratio.split(":"))
    # Qwen Image 2.1's VAE downsamples by 16. Match ResolutionSelector to it
    # so ComfyUI's latent conversion does not silently round these sizes again.
    scale = math.sqrt(1024 * 1024 / (w * h))
    return {"aspect_ratio": aspect_ratio, "label": label,
            "width": round(w * scale / 16) * 16, "height": round(h * scale / 16) * 16}
