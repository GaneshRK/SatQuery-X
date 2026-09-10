# Real Optical-SAR Fusion

Stage 6 replaces heuristic-only fusion with a supervised dual-encoder network. Optical RGB and SAR branches are encoded separately, learned features are fused, and a pixel classifier predicts the supplied land-cover/change class mask.

Train:
`python -m ml.optical_sar_fusion.train --manifest data/optical_sar/train.json --output ml/checkpoints/optical_sar_v1.pt`

Evaluate:
`python -m ml.optical_sar_fusion.evaluate --manifest data/optical_sar/test.json --checkpoint ml/checkpoints/optical_sar_v1.pt`

No checkpoint or metric is fabricated when real labeled data is absent.
