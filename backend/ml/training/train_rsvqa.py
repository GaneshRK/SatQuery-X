"""Real RS-VQA training pipeline using BLIP + LoRA.

Two explicit stages are supported:
  1. --stage domain_adapt: adapt image/text representations using supplied
     BigEarthNet text annotations (no fabricated labels).
  2. --stage vqa: fine-tune the adapted/base BLIP VQA model on an RSVQA-style
     manifest containing image/question/answer records.

Example:
  python -m ml.training.train_rsvqa --stage domain_adapt \
      --manifest data/bigearthnet/train.jsonl \
      --output ml/checkpoints/rsvqa_domain_lora

  python -m ml.training.train_rsvqa --stage vqa \
      --manifest data/rsvqa/train.jsonl \
      --eval-manifest data/rsvqa/val.jsonl \
      --base-model ml/checkpoints/rsvqa_domain_lora \
      --output ml/checkpoints/rsvqa_lora_v1
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def require_ml_deps():
    try:
        import torch
        from transformers import BlipForQuestionAnswering, BlipProcessor, Trainer, TrainingArguments
        from peft import LoraConfig, TaskType, get_peft_model
    except ImportError as exc:
        raise RuntimeError(
            "RS-VQA training requires torch, transformers, peft and accelerate. "
            "Install the ML requirements before training."
        ) from exc
    return torch, BlipForQuestionAnswering, BlipProcessor, Trainer, TrainingArguments, LoraConfig, TaskType, get_peft_model


def build_collator(processor, stage: str, max_question_tokens: int, max_answer_tokens: int):
    import torch

    def collate(batch: list[dict[str, Any]]) -> dict[str, Any]:
        images = [x["image"] for x in batch]
        if stage == "domain_adapt":
            prompts = ["Describe this remote-sensing image."] * len(batch)
            targets = [x["text"] for x in batch]
        else:
            prompts = [x["question"] for x in batch]
            targets = [x["answer"] for x in batch]

        enc = processor(
            images=images,
            text=prompts,
            padding=True,
            truncation=True,
            max_length=max_question_tokens,
            return_tensors="pt",
        )
        labels = processor.tokenizer(
            targets,
            padding=True,
            truncation=True,
            max_length=max_answer_tokens,
            return_tensors="pt",
        ).input_ids
        labels[labels == processor.tokenizer.pad_token_id] = -100
        enc["labels"] = labels
        return enc

    return collate


def attach_lora(model, rank: int, alpha: int, dropout: float):
    _, _, _, _, _, LoraConfig, TaskType, get_peft_model = require_ml_deps()
    config = LoraConfig(
        r=rank,
        lora_alpha=alpha,
        lora_dropout=dropout,
        target_modules=["q_proj", "v_proj"],
        bias="none",
        task_type=TaskType.SEQ_2_SEQ_LM,
    )
    model = get_peft_model(model, config)
    model.print_trainable_parameters()
    return model


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=["domain_adapt", "vqa"], required=True)
    p.add_argument("--manifest", required=True)
    p.add_argument("--eval-manifest")
    p.add_argument("--image-root")
    p.add_argument("--eval-image-root")
    p.add_argument("--base-model", default="Salesforce/blip-vqa-base")
    p.add_argument("--output", required=True)
    p.add_argument("--epochs", type=float, default=3)
    p.add_argument("--learning-rate", type=float, default=2e-4)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--gradient-accumulation", type=int, default=4)
    p.add_argument("--rank", type=int, default=16)
    p.add_argument("--alpha", type=int, default=32)
    p.add_argument("--dropout", type=float, default=0.05)
    p.add_argument("--max-question-tokens", type=int, default=64)
    p.add_argument("--max-answer-tokens", type=int, default=64)
    p.add_argument("--save-steps", type=int, default=500)
    p.add_argument("--logging-steps", type=int, default=10)
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main():
    args = parse_args()
    torch, BlipForQuestionAnswering, BlipProcessor, Trainer, TrainingArguments, *_ = require_ml_deps()
    from ml.training.dataset import BigEarthNetTextDataset, RSVQAManifestDataset

    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    processor = BlipProcessor.from_pretrained(args.base_model)
    model = BlipForQuestionAnswering.from_pretrained(args.base_model)
    model = attach_lora(model, args.rank, args.alpha, args.dropout)

    DatasetClass = BigEarthNetTextDataset if args.stage == "domain_adapt" else RSVQAManifestDataset
    train_ds = DatasetClass(args.manifest, args.image_root)
    eval_ds = None
    if args.eval_manifest:
        eval_ds = DatasetClass(args.eval_manifest, args.eval_image_root or args.image_root)

    collator = build_collator(processor, args.stage, args.max_question_tokens, args.max_answer_tokens)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    use_fp16 = bool(torch.cuda.is_available() and os.getenv("RSVQA_FP16", "1").lower() not in {"0", "false", "no"})
    training_args = TrainingArguments(
        output_dir=str(out),
        num_train_epochs=args.epochs,
        learning_rate=args.learning_rate,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation,
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        save_total_limit=2,
        evaluation_strategy="steps" if eval_ds else "no",
        eval_steps=args.save_steps if eval_ds else None,
        fp16=use_fp16,
        remove_unused_columns=False,
        report_to="none",
        seed=args.seed,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        data_collator=collator,
    )
    trainer.train()
    trainer.save_model(str(out))
    processor.save_pretrained(str(out))

    metadata = {
        "stage": args.stage,
        "base_model": args.base_model,
        "manifest": str(Path(args.manifest).resolve()),
        "eval_manifest": str(Path(args.eval_manifest).resolve()) if args.eval_manifest else None,
        "epochs": args.epochs,
        "learning_rate": args.learning_rate,
        "batch_size": args.batch_size,
        "gradient_accumulation": args.gradient_accumulation,
        "lora": {"rank": args.rank, "alpha": args.alpha, "dropout": args.dropout, "target_modules": ["q_proj", "v_proj"]},
    }
    (out / "satquery_training_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Saved real RS-VQA checkpoint to {out}")


if __name__ == "__main__":
    main()
