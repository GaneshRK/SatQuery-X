"""RS-VQA Standalone Inference Script per §16."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = ROOT_DIR / "backend"
for d in (str(ROOT_DIR), str(BACKEND_DIR)):
    if d not in sys.path:
        sys.path.insert(0, d)

from PIL import Image

from apps.agent.contracts import ModelInput
from apps.models_ai.rs_vqa.wrapper import RSVQAModel


def run_inference(image_path: str, question: str) -> None:
    p = Path(image_path)
    if not p.exists():
        print(f"[-] Image not found: {image_path}")
        sys.exit(1)

    print(f"[+] Loading image: {p.name}")
    print(f"[+] Question: {question}")

    model = RSVQAModel()
    with open(p, "rb") as f:
        img_bytes = f.read()

    inputs = ModelInput(model_id="RS_VQA", image_bytes=[img_bytes], question=question)
    output = model.predict(inputs)

    print("\n--- Model Output ---")
    print(f"Answer:     {output.answer}")
    print(f"Confidence: {output.confidence}")
    print(f"Latency:    {output.latency_ms} ms")
    print(f"Model ID:   {output.model_id} (version: {output.version})")
    print(f"Status:     {output.status}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run standalone RS-VQA inference on an image")
    parser.add_argument("--image", required=True, help="Path to input raster or image")
    parser.add_argument("--question", default="What is visible in this remote sensing image?", help="VQA Question")
    args = parser.parse_args()

    run_inference(args.image, args.question)


if __name__ == "__main__":
    main()
