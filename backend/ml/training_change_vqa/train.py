"""Supervised Change VQA fine-tuning using BLIP VQA + LoRA.

T1 and T2 are concatenated into a single temporal canvas with explicit
DATE_1/DATE_2 visual ordering. This makes the temporal relation learnable
without pretending BLIP is a native two-image architecture.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import torch
from PIL import Image, ImageDraw
from transformers import BlipForQuestionAnswering, BlipProcessor, Trainer, TrainingArguments
from peft import LoraConfig, get_peft_model
from ml.training_change_vqa.dataset import ChangeVQAManifestDataset

def temporal_canvas(t1: Image.Image, t2: Image.Image, size: int = 384) -> Image.Image:
    t1, t2 = t1.copy(), t2.copy()
    t1.thumbnail((size, size)); t2.thumbnail((size, size))
    h = max(t1.height, t2.height)
    canvas = Image.new("RGB", (size * 2, h + 28), "white")
    canvas.paste(t1, ((size-t1.width)//2, 28)); canvas.paste(t2, (size+(size-t2.width)//2, 28))
    d = ImageDraw.Draw(canvas); d.text((10, 7), "T1 / BEFORE", fill="black"); d.text((size+10, 7), "T2 / AFTER", fill="black")
    return canvas

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True); p.add_argument("--eval-manifest")
    p.add_argument("--base-model", default="Salesforce/blip-vqa-base")
    p.add_argument("--output", default="ml/checkpoints/change_vqa_lora_v1")
    p.add_argument("--epochs", type=float, default=3); p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--learning-rate", type=float, default=2e-4); p.add_argument("--rank", type=int, default=16)
    p.add_argument("--alpha", type=int, default=32); p.add_argument("--dropout", type=float, default=.05)
    p.add_argument("--max-question-tokens", type=int, default=64); p.add_argument("--max-answer-tokens", type=int, default=64)
    args = p.parse_args()
    processor = BlipProcessor.from_pretrained(args.base_model)
    model = BlipForQuestionAnswering.from_pretrained(args.base_model)
    model = get_peft_model(model, LoraConfig(r=args.rank, lora_alpha=args.alpha, lora_dropout=args.dropout,
        target_modules=["q_proj", "v_proj"], task_type="SEQ_2_SEQ_LM"))
    train = ChangeVQAManifestDataset(args.manifest)
    ev = ChangeVQAManifestDataset(args.eval_manifest) if args.eval_manifest else None
    def collate(batch):
        images = [temporal_canvas(x["t1"], x["t2"]) for x in batch]
        questions = ["Compare the before and after satellite observations. " + x["question"] for x in batch]
        answers = [x["answer"] for x in batch]
        enc = processor(images=images, text=questions, padding=True, truncation=True, max_length=args.max_question_tokens, return_tensors="pt")
        labels = processor.tokenizer(answers, padding=True, truncation=True, max_length=args.max_answer_tokens, return_tensors="pt").input_ids
        labels[labels == processor.tokenizer.pad_token_id] = -100
        enc["labels"] = labels
        return enc
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    ta = TrainingArguments(output_dir=str(out), num_train_epochs=args.epochs, learning_rate=args.learning_rate,
        per_device_train_batch_size=args.batch_size, per_device_eval_batch_size=args.batch_size,
        evaluation_strategy="steps" if ev else "no", eval_steps=100 if ev else None, save_steps=100,
        save_total_limit=2, remove_unused_columns=False, report_to="none", fp16=torch.cuda.is_available())
    Trainer(model=model, args=ta, train_dataset=train, eval_dataset=ev, data_collator=collate).train()
    model.save_pretrained(out); processor.save_pretrained(out)
    (out/"satquery_change_vqa_training_metadata.json").write_text(json.dumps({"task":"bi_temporal_change_vqa","base_model":args.base_model,"manifest":str(Path(args.manifest).resolve()),"eval_manifest":str(Path(args.eval_manifest).resolve()) if args.eval_manifest else None,"method":"BLIP VQA + LoRA on T1/T2 temporal canvas"}, indent=2), encoding="utf-8")
    print(f"Saved real Change VQA checkpoint to {out}")
if __name__ == "__main__": main()
