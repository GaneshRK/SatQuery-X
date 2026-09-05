# SatQuery-X — Model and Dataset License Compliance
**SIH 2026 — Problem Statement 26167**

This document establishes the licensing status, provenance, and operational boundaries for all neural models, heuristic engines, and training datasets utilized within SatQuery-X.

---

## 1. AI Models & Checkpoint Licenses

| Component / Model ID | Developer / Organization | Stated License | Commercial Use Permitted? | Notes & Usage Constraints |
|---|---|---|:---:|---|
| **Qwen/Qwen2.5-1.5B-Instruct** | Alibaba Cloud | Apache-2.0 | ✅ Yes | Permissive open-weights license. Used as SLM query router. |
| **Qwen/Qwen3-1.7B** | Alibaba Cloud | Apache-2.0 | ✅ Yes | Recommended query router. |
| **MBZUAI/geochat-7B** | MBZUAI | CC-BY-NC-4.0 | ❌ No (Academic/Research Only) | Remote sensing conversational VLM. SIH academic presentation allowed; commercial deployment requires replacement with Apache-2.0 VLM. |
| **OneScience-Group/RemoteCLIP** | OneScience Group / Tsinghua | MIT | ✅ Yes | Fully permissive open-source license. Cross-modal embeddings. |
| **ChangeFormer** | Bandara & Patel (WACV 2022) | Apache-2.0 / MIT | ✅ Yes | Remote sensing transformer-based change detection. |
| **IDEA-Research/grounding-dino-tiny** | IDEA Research | Apache-2.0 | ✅ Yes | Open-set visual grounding. |
| **Salesforce/blip-vqa-base** | Salesforce Research | BSD-3-Clause | ✅ Yes | Permissive commercial license fallback. |
| **OpenCV / SciPy / Rasterio / GDAL** | Open Source Communities | BSD / MIT / Apache-2.0 | ✅ Yes | Foundation image processing and geospatial math libraries. |

---

## 2. Remote-Sensing Datasets & Adaptation Data

| Dataset Name | Source / Organization | License | Commercial Permitted? | Task / Modality in SatQuery-X |
|---|---|---|:---:|---|
| **BigEarthNet-S2 / BigEarthNet-MM** | TU Berlin & DLR | CDLA-Permissive-1.0 | ✅ Yes | Multi-spectral Sentinel-2 and Sentinel-1 multimodal land cover classification and LoRA domain adaptation. |
| **RSVQA (HR / LR)** | Sylvain Lobry et al. (IEEE TGRS) | CC-BY-NC-SA 4.0 | ❌ No (Academic Only) | Remote sensing visual question answering training benchmark. |
| **VRSBench** | CVPR 2024 Remote Sensing | CC-BY-NC 4.0 | ❌ No (Academic Only) | Visual reasoning, grounding, and captioning benchmark. |
| **CDVQA** | Remote Sensing Change VQA | CC-BY-NC-SA 4.0 | ❌ No (Academic Only) | Bi-temporal change question answering. |
| **LEVIR-CD / WHU-CD** | Beihang Univ / Wuhan Univ | CC-BY-SA 4.0 | ❌ No (Academic Only) | Bi-temporal building change detection benchmark. |

---

## 3. License Safety Guarantees
1. No dataset or model is labeled "commercial-ready" unless its license explicitly permits unrestricted commercial distribution.
2. Academic and research datasets (e.g., RSVQA, CDVQA, GeoChat) are strictly partitioned for hackathon evaluation and academic benchmarking.
3. Production / commercial builds of SatQuery-X isolate these models behind pluggable interfaces (`ModelManager`), allowing drop-in substitution with Apache-2.0 or commercial checkpoints.
