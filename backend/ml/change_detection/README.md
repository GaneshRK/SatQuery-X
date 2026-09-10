# Real change-detection pipeline

Stage 3 adds a complete supervised training → checkpoint → inference → evaluation
path for bi-temporal change detection.

## Model

`SiameseChangeNet` is a compact shared-weight Siamese encoder with a difference
decoder. It is a genuine trainable neural model implemented in this project.
It is **not** called ChangeFormer, because ChangeFormer is a distinct published
architecture.

## Training

```powershell
python -m ml.change_detection.train `
  --train-manifest data/change_detection/train.json `
  --val-manifest data/change_detection/val.json `
  --output ml/checkpoints/satquery_siamese_cd_v1.pt `
  --epochs 20
```

## Evaluation

```powershell
python -m ml.change_detection.evaluate `
  --manifest data/change_detection/test.json `
  --checkpoint ml/checkpoints/satquery_siamese_cd_v1.pt
```

Metrics: pixel accuracy, precision, recall, F1 and IoU.

## Runtime

Set:

```text
CHANGE_DETECTION_CHECKPOINT=ml/checkpoints/satquery_siamese_cd_v1.pt
CHANGE_DETECTION_MODEL_TYPE=siamese
```

The wrapper uses the trained checkpoint when available. If no trained model is
configured, it keeps the existing deterministic image-difference evidence path
and labels it as a baseline rather than pretending it is a learned model.
