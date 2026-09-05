# SatQuery-X — Model Training & Domain Adaptation Guide
**SIH 2026 — Problem Statement 26167**

This directory contains datasets, configuration files, and scripts for domain adaptation and fine-tuning on remote sensing benchmarks (BigEarthNet, VRSBench, RSVQA, CDVQA).

---

## Directory Structure

```
training/
├── configs/             # YAML configurations for LoRA, fusion classifiers, and change detection
├── datasets/            # Dataset loaders for BigEarthNet, VRSBench, CDVQA, and ISRO rehearsal
├── scripts/             # Training and evaluation orchestration
├── rsvqa/               # Dedicated RS-VQA LoRA pipeline (§16)
│   ├── config.yaml
│   ├── dataset.py
│   ├── preprocess.py
│   ├── train.py
│   ├── evaluate.py
│   └── inference.py
├── checkpoints/         # Target directory for exported adapter checkpoints
├── evaluation/          # Benchmark results and metrics logs
└── README.md
```

---

## Quickstart Commands

### 1. Dry-Run Validation (CPU / Automated CI)
```powershell
python training/rsvqa/train.py --dry-run
```

### 2. Full GPU Training with LoRA
```powershell
python training/rsvqa/train.py --config training/rsvqa/config.yaml
```

### 3. Evaluate Checkpoint on Benchmark Split
```powershell
python training/rsvqa/evaluate.py --config training/rsvqa/config.yaml
```

### 4. Run Standalone Inference
```powershell
python training/rsvqa/inference.py --image path/to/scene.tif --question "Is there water in this scene?"
```

### 5. Multi-Benchmark Evaluation Suite
```powershell
python training/scripts/evaluate_benchmarks.py
```
