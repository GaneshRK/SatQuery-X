# Stage 15 — Native Four-Stream Temporal Optical/SAR

## Purpose

Stage 14 could identify `BI_TEMPORAL_OPTICAL_SAR` correctly but intentionally did not feed four observations into a two-image model. Stage 15 adds a native four-stream supervised model.

The model consumes:

- Optical T1
- SAR T1
- Optical T2
- SAR T2
- user question

Optical and SAR use separate encoders. Time and modality embeddings are explicit before Transformer fusion.

## Training

```bash
python -m ml.temporal_optical_sar.train \
  --manifest data/optical_sar/temporal_vqa_train.jsonl \
  --output ml/checkpoints/temporal_optical_sar_v1.pt
```

Each JSONL row must contain `optical_t1`, `sar_t1`, `optical_t2`, `sar_t2`, `question`, and `answer`. The implementation refuses missing fields and does not invent labels.

## Runtime

Set `TEMPORAL_OPTICAL_SAR_CHECKPOINT` to a real trained checkpoint. The agent route is `TEMPORAL_CROSS_MODAL` and requires explicit modality metadata for two optical and two SAR observations.

If the checkpoint is absent or the four-stream requirements are not met, the specialist returns an explicit error. It does not silently substitute the two-image model.

## Evaluation

```bash
python -m ml.temporal_optical_sar.evaluate \
  --manifest data/optical_sar/temporal_vqa_test.jsonl \
  --checkpoint ml/checkpoints/temporal_optical_sar_v1.pt \
  --output ml/evaluation/results/temporal_optical_sar.json
```

Reported confidence is raw softmax confidence and is explicitly marked uncalibrated until a held-out calibration step is performed.

## Scientific guardrails

The model does not infer optical/SAR identity from list position. Raster SAR is normalized as a one-channel input; this is a model input representation, not a claim that SAR has optical reflectance semantics. Geospatial coregistration remains a prerequisite for spatially meaningful fusion.
