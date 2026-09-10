# Stage 5 — Real Evaluation

Stage 5 removes placeholder benchmark numbers and makes evaluation an actual inference-based process.

## What is evaluated

| Task | Real evaluator | Required ground truth |
|---|---|---|
| RS-VQA | `ml/evaluation/evaluate_rsvqa.py` | image + question + reference answer |
| Bi-temporal change detection | `ml/change_detection/evaluate.py` | T1 + T2 + binary change mask |
| Bi-temporal Change VQA | `ml/training_change_vqa/evaluate.py` | T1 + T2 + question + reference answer |

## Scientific rules

- No hardcoded accuracy/F1/IoU/latency values.
- No score is emitted from an empty or missing manifest.
- A checkpoint path must exist.
- Evaluation runs inference on every supplied held-out sample.
- Per-sample predictions and latency are retained in the report.
- Aggregate metrics are computed from those predictions.
- Test/held-out data must be separate from training data.

## Run individually

```bash
python -m ml.evaluation.evaluate_rsvqa \
  --checkpoint ml/checkpoints/rsvqa_lora_v1 \
  --manifest data/rsvqa/test.jsonl \
  --dataset RSVQA --split test \
  --output ml/evaluation/results/rsvqa_test.json
```

```bash
python -m ml.change_detection.evaluate \
  --checkpoint ml/checkpoints/satquery_siamese_cd_v1.pt \
  --manifest data/change_detection/test.jsonl \
  --output ml/evaluation/results/change_detection_test.json
```

```bash
python -m ml.training_change_vqa.evaluate \
  --checkpoint ml/checkpoints/change_vqa_lora_v1 \
  --manifest data/change_vqa/test.jsonl \
  --output ml/evaluation/results/change_vqa_test.json
```

## Run a suite

Copy `ml/configs/evaluation_suite.example.json`, replace paths with the real
held-out datasets/checkpoints, then run:

```bash
python -m ml.evaluation.run_suite --config ml/configs/evaluation_suite.json
```

The repository intentionally contains **no benchmark scores** until those commands are run with real data.
