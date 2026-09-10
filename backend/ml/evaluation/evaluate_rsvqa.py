"""Real RS-VQA evaluation: checkpoint inference + reproducible metrics.

The evaluator refuses to produce a score without a real manifest and a real
checkpoint. It supports either a full Hugging Face BLIP checkpoint or a PEFT
LoRA adapter directory produced by SatQuery training.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from ml.evaluation.metrics import normalize_answer, token_f1, mean


def _load_records(path: Path) -> list[dict]:
    if path.suffix.lower() == ".jsonl":
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data.get("samples", data.get("records", data)) if isinstance(data, dict) else data
    if not isinstance(records, list) or not records:
        raise ValueError("Evaluation manifest must contain at least one real sample.")
    return records


def _load_model(checkpoint: str, device: str):
    try:
        import torch
        from transformers import BlipForQuestionAnswering, BlipProcessor
    except ImportError as exc:
        raise RuntimeError("Install torch and transformers for RS-VQA evaluation.") from exc

    checkpoint_path = Path(checkpoint)
    is_lora = (checkpoint_path / "adapter_config.json").exists()
    if is_lora:
        try:
            from peft import PeftModel
        except ImportError as exc:
            raise RuntimeError("PEFT is required to evaluate a LoRA RS-VQA checkpoint.") from exc
        adapter_cfg = json.loads((checkpoint_path / "adapter_config.json").read_text(encoding="utf-8"))
        base_model = adapter_cfg.get("base_model_name_or_path")
        if not base_model:
            raise ValueError("adapter_config.json does not contain base_model_name_or_path.")
        processor = BlipProcessor.from_pretrained(str(checkpoint_path))
        base = BlipForQuestionAnswering.from_pretrained(base_model).to(device)
        model = PeftModel.from_pretrained(base, str(checkpoint_path)).to(device).eval()
    else:
        processor = BlipProcessor.from_pretrained(str(checkpoint_path))
        model = BlipForQuestionAnswering.from_pretrained(str(checkpoint_path)).to(device).eval()
    return processor, model


def evaluate(checkpoint: str, manifest: str, output: str, dataset: str = "RSVQA", split: str = "test", image_root: str | None = None) -> dict:
    import torch
    from PIL import Image

    manifest_path = Path(manifest)
    records = _load_records(manifest_path)
    root = Path(image_root) if image_root else manifest_path.parent
    device = "cuda" if torch.cuda.is_available() else "cpu"
    processor, model = _load_model(checkpoint, device)

    rows = []
    exact = []
    f1s = []
    latencies = []
    for i, record in enumerate(records):
        if not all(k in record for k in ("image", "question", "answer")):
            raise ValueError(f"Record {i} must contain image, question and answer.")
        image_path = Path(record["image"])
        image_path = image_path if image_path.is_absolute() else root / image_path
        with Image.open(image_path) as img:
            image = img.convert("RGB")
            encoded = processor(images=image, text=str(record["question"]), return_tensors="pt")
        encoded = {k: v.to(device) for k, v in encoded.items()}
        start = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(**encoded, max_new_tokens=32)
        latency_ms = (time.perf_counter() - start) * 1000.0
        prediction = processor.tokenizer.decode(generated[0], skip_special_tokens=True).strip()
        reference = str(record["answer"])
        em = int(normalize_answer(prediction) == normalize_answer(reference))
        f1 = token_f1(prediction, reference)
        exact.append(em); f1s.append(f1); latencies.append(latency_ms)
        rows.append({"id": record.get("id", i), "question": record["question"], "prediction": prediction, "reference": reference, "exact_match": em, "token_f1": f1, "latency_ms": latency_ms})

    report = {
        "task": "image_vqa",
        "model_id": "RS_VQA",
        "checkpoint": str(Path(checkpoint).resolve()),
        "checkpoint_type": "lora_adapter" if (Path(checkpoint) / "adapter_config.json").exists() else "full_hf_checkpoint",
        "dataset": dataset,
        "split": split,
        "manifest": str(manifest_path.resolve()),
        "sample_count": len(rows),
        "metrics": {"exact_match": mean(exact), "token_f1": mean(f1s), "mean_latency_ms": mean(latencies)},
        "predictions": rows,
    }
    out = Path(output); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    p = argparse.ArgumentParser(description="Run real RS-VQA evaluation")
    p.add_argument("--checkpoint", required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--dataset", default="RSVQA")
    p.add_argument("--split", default="test")
    p.add_argument("--image-root")
    args = p.parse_args()
    report = evaluate(**vars(args))
    print(json.dumps(report["metrics"], indent=2))


if __name__ == "__main__":
    main()
