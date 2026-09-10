# SatQuery RS-VQA ML pipeline

This directory now contains a real, executable RS-VQA pipeline. It does **not** claim benchmark performance until a checkpoint has actually been trained and evaluated.

## Manifest formats

RSVQA JSONL/JSON records:

```json
{"id":"1","image":"images/scene_001.jpg","question":"What type of land cover is visible?","answer":"agriculture"}
```

BigEarthNet domain-adaptation records:

```json
{"id":"1","image":"images/scene_001.jpg","text":"remote sensing text annotation"}
```

The BigEarthNet stage requires a real text/caption annotation. It does not turn class labels into invented VQA answers.

## 1. Install

```bash
pip install -r requirements.txt
```

## 2. Domain adaptation

```bash
python -m ml.training.train_rsvqa \
  --stage domain_adapt \
  --manifest data/bigearthnet/train.jsonl \
  --output ml/checkpoints/rsvqa_domain_lora
```

## 3. RSVQA fine-tuning

```bash
python -m ml.training.train_rsvqa \
  --stage vqa \
  --manifest data/rsvqa/train.jsonl \
  --eval-manifest data/rsvqa/val.jsonl \
  --base-model ml/checkpoints/rsvqa_domain_lora \
  --output ml/checkpoints/rsvqa_lora_v1
```

## 4. Evaluate for real

```bash
python -m ml.evaluation.evaluate_rsvqa \
  --checkpoint ml/checkpoints/rsvqa_lora_v1 \
  --manifest data/rsvqa/test.jsonl \
  --output ml/evaluation/results/RS_VQA_RSVQA_test_real.json
```

## 5. Connect the Django agent

Set:

```text
VQA_CHECKPOINT=ml/checkpoints/rsvqa_lora_v1
```

The RS_VQA wrapper will then lazily load the checkpoint through the canonical model manager. If the checkpoint is absent or cannot be loaded, the wrapper does **not** pretend that a trained model is running; it follows the existing explicit fallback behavior.

## Stage 4 — Bi-temporal Change VQA

Change VQA is now a real supervised training path in `ml/training_change_vqa/`.
It expects genuine T1/T2/question/answer records and fine-tunes BLIP VQA with LoRA.
The runtime is enabled with `CHANGE_VQA_CHECKPOINT`; when no checkpoint is configured,
the existing grounded evidence reasoner remains available and does not claim a neural model is active.

Example:

```powershell
python -m ml.training_change_vqa.train --manifest data/change_vqa/train.jsonl --eval-manifest data/change_vqa/val.jsonl --output ml/checkpoints/change_vqa_lora_v1
python -m ml.training_change_vqa.evaluate --checkpoint ml/checkpoints/change_vqa_lora_v1 --manifest data/change_vqa/test.jsonl --output ml/evaluation/results/change_vqa.json
```

The training implementation uses a temporal canvas (`T1 / BEFORE` + `T2 / AFTER`) because the selected BLIP VQA architecture accepts one visual input. This is explicitly documented rather than mislabeling BLIP as a native two-image Change VQA architecture.

## Stage 8
Real satellite asset ingestion is implemented in `apps/satellite/services/asset_ingestion.py` with `download_satellite_asset_task`.

### Stage 11 confidence calibration

See `docs/STAGE_11_CONFIDENCE_CALIBRATION.md`. Calibration is optional and is
fit only from held-out validation predictions; no calibrated confidence is
claimed when such an artifact is absent.
