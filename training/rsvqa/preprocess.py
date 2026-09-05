"""RS-VQA Tokenizer and Vision Preprocessor per §16."""

from __future__ import annotations

from typing import Any
import numpy as np
from PIL import Image


class RSVQAPreprocessor:
    def __init__(self, image_size: int = 384, max_len: int = 64) -> None:
        self.image_size = image_size
        self.max_len = max_len

    def preprocess_image(self, img: Image.Image) -> np.ndarray:
        """Resizes and normalizes remote sensing image into standard float32 tensor array [3, H, W]."""
        resized = img.resize((self.image_size, self.image_size), Image.Resampling.BILINEAR)
        arr = np.array(resized, dtype=np.float32) / 255.0

        # Standard ImageNet / Remote Sensing normalization
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        norm = (arr - mean) / std

        # Transpose from [H, W, C] to [C, H, W]
        return np.transpose(norm, (2, 0, 1))

    def tokenize_text(self, text: str) -> list[str]:
        """Simple whitespace/punctuation tokenization fallback."""
        import re
        tokens = re.findall(r"\w+|[^\w\s]", text.lower())
        return tokens[: self.max_len]
