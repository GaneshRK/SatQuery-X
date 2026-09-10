# SatQuery-X Backend Architecture

## Stage 1: Canonical structure

The backend has one authoritative specialist-model registry and one authoritative
specialist-model wrapper location.

### Canonical model registry

- Registry configuration: `apps/agent/models.yaml`
- Registry implementation: `apps/agent/registry.py`
- The agent registry is the source of truth for specialist model IDs, tasks,
  input modes, dependencies, wrapper paths, and model metadata.

### Canonical specialist wrappers

All six SatQuery specialist wrappers live under `apps/models_ai/`:

- `rs_vqa/wrapper.py`
- `rs_caption/wrapper.py`
- `rs_grounding/wrapper.py`
- `change_detection/wrapper.py`
- `change_vqa/wrapper.py`
- `optical_sar_fusion/wrapper.py`

### Canonical runtime model manager

- `apps/models_ai/manager.py`
- `ModelManager` owns lazy model loading, caching, lifecycle, health and
  runtime statistics.

### Integration adapters

`ai/adapters/` is retained as an integration boundary for adapter-specific
model/tool integrations used by the agent tool registry. These adapters are
not a second specialist registry.

## Removed legacy stacks

The following obsolete duplicate stacks were removed from the cleaned backend:

- `registry/` — legacy model registry and contracts
- `models/` — legacy specialist wrappers
- `planner/` — legacy planner implementation
- `evidence/` — legacy non-Django evidence package
- `geospatial/` — legacy non-Django geospatial package
- `jobs/` — unused legacy job package
- `reports/` — legacy non-Django report package

The active implementations are under `apps/` and are referenced by the Django
settings, URLs, agent, tasks and tests.

## Source-of-truth rule

Do not add a second `models.yaml`, model wrapper tree, or model lifecycle
manager. New specialist models should be added to the canonical registry and
implemented under `apps/models_ai/`.

## RS-VQA runtime contract

`RS_VQA` now has a real Hugging Face runtime path. Set `VQA_CHECKPOINT` to a
trained BLIP/LoRA checkpoint produced by `ml.training.train_rsvqa`. The wrapper
loads it lazily through `apps/models_ai/manager.py`. If the checkpoint cannot
be loaded, the system records the failure rather than claiming a trained model
is active.

Benchmark metrics are never stored as constants. Evaluation must run the
checkpoint against an explicit manifest and write the resulting predictions
and metrics.

## Stage 3 — Bi-temporal change detection

Change detection now has an explicit supervised training/evaluation path in `ml/change_detection/`. `SiameseChangeNet` is a genuine trainable binary change-segmentation model with a shared encoder for T1/T2, feature-difference decoding, checkpoint export, and manifest-backed evaluation. Runtime loading is opt-in through `CHANGE_DETECTION_CHECKPOINT` and `CHANGE_DETECTION_MODEL_TYPE=siamese`.

The deterministic image-difference implementation remains as an explicitly labeled evidence baseline when no trained checkpoint is configured. It is not reported as a learned model. A future ChangeFormer checkpoint must be kept explicitly identified as ChangeFormer; it must not be mislabeled as the project Siamese model.
