# SatQuery-X — Model Registry Specification
**SIH 2026 — Problem Statement 26167**

SatQuery-X implements a specialist model architecture where each AI component has an explicit contract, schema, licensing details, and transparent fallback behavior.

---

## Model Inventory & Contracts

### 1. Query Router & Task Planner (`router_slm`)
- **Model ID**: `Qwen/Qwen2.5-1.5B-Instruct` (or `Qwen/Qwen3-1.7B` where available)
- **Role**: Natural language query router to structured task plan (JSON Schema). **Does NOT analyze satellite pixels directly.**
- **Provider**: Local (PyTorch / Transformers / ONNX Runtime)
- **License**: Apache-2.0 (Open Weights, Commercial Use Permitted)
- **Input**: User query string + Session context (image count, modality, past conversation)
- **Output Schema**:
  ```json
  {
    "intent": "BI_TEMPORAL_CHANGE_VQA",
    "required_images": 2,
    "requires_change_detection": true,
    "requires_spatial_evidence": true,
    "requires_area_estimation": true,
    "target_features": ["built-up", "buildings"]
  }
  ```
- **Fallback Policy**: Deterministic regex/keyword-based Query Understander (`understander.py`).
- **Device Support**: CUDA (fp16/int4), CPU (int4).

---

### 2. Remote-Sensing Vision-Language Model (`rs_vlm`)
- **Model ID**: `MBZUAI/geochat-7B`
- **Alternative / Lightweight**: `Salesforce/blip-vqa-base` (385M) / `vikhyatk/moondream2`
- **Role**: Remote-sensing visual question answering, scene description, region captioning.
- **Provider**: Hugging Face / Local PyTorch
- **License**: CC-BY-NC-4.0 (GeoChat) / BSD-3-Clause (BLIP)
- **Input Requirements**: Single RGB optical image (scaled to 448x448 or 512x512) + text question
- **Output Schema**:
  ```json
  {
    "answer": "The image reveals dense commercial structures surrounded by paved road networks.",
    "confidence": 0.88,
    "status": "ok"
  }
  ```
- **Fallback Policy**: If heavy checkpoint is not loaded on local hardware, returns status `MODEL_NOT_AVAILABLE` with diagnostic guidance rather than fabricating answers.
- **Device Support**: CUDA recommended (VRAM >= 6GB), CPU fallback supported for lightweight models.

---

### 3. Remote-Sensing Image-Text Embeddings (`rs_embedding`)
- **Model ID**: `OneScience-Group/RemoteCLIP`
- **Role**: Multi-modal semantic search, zero-shot remote-sensing image classification, scene similarity.
- **Provider**: Hugging Face / Local PyTorch
- **License**: MIT
- **Input Requirements**: Single image (224x224) or text query
- **Output Schema**: 512-dimensional normalized float32 embedding vector
- **Fallback Policy**: Standard `openai/clip-vit-base-patch32` (MIT).

---

### 4. Remote-Sensing Change Detection (`change_detection`)
- **Model ID**: `ChangeFormer` (Transformer-based Bi-Temporal Change Detection)
- **Alternative**: `BIT` (Bitemporal Image Transformer) / `SNUNet-CD`
- **Role**: Pixel-level change probability map and binary change mask for registered bi-temporal pairs $(T_1, T_2)$.
- **Provider**: Local PyTorch Module
- **License**: Apache-2.0
- **Pipeline**:
  $$T_1 + T_2 \longrightarrow \text{Alignment} \longrightarrow \text{Normalization} \longrightarrow \text{ChangeFormer} \longrightarrow \text{Probability Map} \longrightarrow \text{Calibrated Otsu Threshold} \longrightarrow \text{Morphological Filter} \longrightarrow \text{Connected Components} \longrightarrow \text{WGS84 GeoJSON Polygons} \longrightarrow \text{Geodesic Area (m², ha, km²)}$$
- **Output Schema**:
  ```json
  {
    "change_detected": true,
    "change_probability": 0.91,
    "change_percent": 4.15,
    "area_m2": 415000.0,
    "area_ha": 41.5,
    "area_km2": 0.415,
    "regions_count": 12,
    "status": "ok"
  }
  ```
- **Fallback Policy**: Calibrated adaptive absolute difference with Otsu thresholding labeled as `[CV Fallback]`.

---

### 5. Text-Guided Visual Grounding (`rs_grounding`)
- **Model ID**: `IDEA-Research/grounding-dino-tiny`
- **Role**: Detect and localize objects/regions in remote sensing imagery based on natural language expressions ("water body", "runway", "storage tanks").
- **Provider**: Hugging Face / Local PyTorch
- **License**: Apache-2.0
- **Output Schema**:
  ```json
  {
    "boxes": [
      {"x1": 120.0, "y1": 85.0, "x2": 240.0, "y2": 190.0, "label": "water_body", "confidence": 0.89}
    ],
    "status": "ok"
  }
  ```
- **Fallback Policy**: Spectral Saliency Proposal Engine labeled `[Spectral Proposal]`.

---

### 6. Optical + SAR Cross-Modal Fusion (`optical_sar_fusion`)
- **Model ID**: `OpticalSARFusionModel` (Dual-Branch Feature Encoder)
- **Role**: Fuse co-registered Optical (multispectral) and SAR (backscatter/intensity) imagery for all-weather feature extraction.
- **Preprocessing**:
  - Optical: Band normalization $[0, 1]$, cloud/shadow filtering.
  - SAR: Speckle-aware filtering (Lee/median filter), logarithmic backscatter intensity transform $\sigma^0 = 10 \cdot \log_{10}(I + \epsilon)$.
- **Output Schema**:
  ```json
  {
    "answer": "Cross-modal fusion combines optical spectral absorption and SAR high backscatter to confirm 14 industrial structures and eliminate shadow false-positives.",
    "optical_confidence": 0.86,
    "sar_confidence": 0.89,
    "joint_confidence": 0.91,
    "status": "ok"
  }
  ```

---

## Model Resource Management (`ModelManager`)

All specialist models are governed by `apps.models_ai.manager.ModelManager`:
- **Auto-Detection**: Queries `torch.cuda.is_available()`. Defaults to `MODEL_DEVICE=cuda` if GPU is present; otherwise falls back gracefully to `CPU`.
- **Memory Check**: Monitors available VRAM (`torch.cuda.mem_get_info()`) before loading 1GB+ models.
- **Dynamic Offloading**: Models not accessed within the LRU eviction window are unloaded to preserve host memory.
- **Explicit Low-Hardware Mode**: Under `SATQUERY_MODE=development`, heavyweight 7B models are disabled, and lightweight CV models are prioritized.
