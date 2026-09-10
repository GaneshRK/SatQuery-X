# Stage 13 — Native Temporal + Multimodal Change VQA

SatQuery now has an optional **native two-image temporal model** for Change VQA.

## What changed

The new `ml/native_multimodal/NativeTemporalMultimodalVQA`:

1. Encodes T1 and T2 independently with shared image weights.
2. Adds explicit learned timestamp embeddings (`T1` and `T2`).
3. Encodes the question with a deterministic hashed token embedding.
4. Fuses T1 patches, T2 patches, and the question token with a Transformer encoder.
5. Predicts an answer from a supervised answer vocabulary learned from the training manifest.

This is materially different from the legacy BLIP implementation, which converts
T1/T2 into one labelled temporal canvas because BLIP is a single-image VQA model.

## Training

```bash
python -m ml.native_multimodal.train \
  --manifest data/change_vqa/train.jsonl \
  --output ml/checkpoints/native_temporal_vqa_v1.pt
```

The manifest must contain real:

- `image_t1`
- `image_t2`
- `question`
- `answer`

No answers are invented by the dataset loader.

## Evaluation

```bash
python -m ml.native_multimodal.evaluate \
  --manifest data/change_vqa/test.jsonl \
  --checkpoint ml/checkpoints/native_temporal_vqa_v1.pt \
  --output ml/evaluation/results/native_temporal_vqa.json
```

The evaluator reports closed-vocabulary accuracy, mean latency and per-sample
predictions/confidence.

## Runtime

Set:

```env
CHANGE_VQA_NATIVE_CHECKPOINT=ml/checkpoints/native_temporal_vqa_v1.pt
```

When configured and two images are available, this path is attempted first.
The existing BLIP+LoRA path remains available through `CHANGE_VQA_CHECKPOINT`.

## Scientific limitation

The native model is a **closed-vocabulary classifier**, not a general generative
VQA model. It should only be evaluated on answers represented in its training
vocabulary. Its softmax confidence is explicitly marked **uncalibrated** until a
held-out calibration procedure is fitted. It does not prove that a semantic
change is physically correct merely because it predicts an answer.
