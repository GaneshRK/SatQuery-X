# Stage 3 — Real Bi-temporal Change Detection

## What changed

- Added `SiameseChangeNet`, a real supervised binary change-segmentation model.
- Added manifest-backed T1/T2/mask dataset loading.
- Added training script with BCE + Dice loss and checkpoint export.
- Added evaluation script reporting pixel accuracy, precision, recall, F1 and IoU.
- Added runtime checkpoint loading through `CHANGE_DETECTION_CHECKPOINT`.
- Preserved the existing deterministic difference baseline as an explicitly labeled fallback.
- Updated the model registry metadata to distinguish supervised change detection from the baseline.
- Added tests for the model output shape and dataset contract.

## Scientific honesty

No benchmark score is added to the project. No checkpoint is included because no real labeled change-detection dataset was supplied in this stage. The system only reports learned-model inference after a real checkpoint is trained and configured.

## Important distinction

The published ChangeFormer architecture is not silently reimplemented or mislabeled as `SiameseChangeNet`. If the team later uses the official ChangeFormer implementation/checkpoint, it should be integrated as a separately named model slot.
